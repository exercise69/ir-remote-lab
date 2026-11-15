# IR-Labor – CircuitPython auf Adafruit QT Py ESP32-S3
#
# Empfangen:
#   TSMP98000 misst die Traegerfrequenz (gibt pro Traegerschwingung einen Puls aus)
#   TSOP (TSOP34836 = 36 kHz, TSOP38238 = 38 kHz) zeichnet den demodulierten Code auf
# Senden:
#   IR-LED (TSAL6200) ueber 2N2222A an A3: Testmuster, aufgenommene oder beliebige Codes.
#   Weil die Empfaenger daneben stehen, wird jede Sendung gleich wieder empfangen
#   und mit dem Gesendeten verglichen (Eigentest).
# Bedienung:
#   Webseite http://<IP des Boards>/ (Datei web/index.html), serielle Konsole oder Taster.
#
# Hardware (die Grundausstattung des Boards bleibt unveraendert):
#   TSMP98000 OUT -> TX       TSOP OUT -> RX       (VS ueber 100 Ohm an 3V, 100 nF nach GND)
#   A3 -> 220 Ohm -> Basis 2N2222A (10 kOhm Basis nach GND), Emitter an GND,
#   Kollektor -> IR-LED -> 33 Ohm -> 5V
#   LED an A0 (mit Vorwiderstand nach GND): blitzt bei jeder Aufnahme
#   SD-Karte an SPI (SCK/MO/MI), CS an A1: /sd/aufnahmen.csv, /sd/codes.json
#     (Mount-Punkt: leerer Ordner "sd" auf CIRCUITPY; adafruit_sdcard statt
#      sdcardio, weil sdcardio frueher Schreibfehler gemacht hat)
#   Taster von A2 nach GND: kurz = naechste Fernbedienungs-Taste (LED blinkt die
#     Nummer), lang (1 s) = zurueck auf Taste 1
#
# Befehle ueber die serielle Konsole (Eingabe + Enter):
#   t [kHz]   Testmuster senden (Standard 36 kHz)
#   r [n]     Aufnahme n erneut senden (ohne n: die letzte)
#   l         gespeicherte Aufnahmen auflisten
#   h         Hilfe
#
# Bibliotheken in lib/: adafruit_httpserver, adafruit_sdcard, adafruit_ntp
# Ausserdem auf CIRCUITPY: ir_lab.py, web/index.html, leerer Ordner sd

import array
import json
import os
import random
import sys
import time

import board
import digitalio
import keypad
import pulseio
import pwmio
import supervisor

from ir_lab import (MAX_PULSES, best_frame, carrier_khz, code_pulses,
                       compare_echo, majority, nearest_std, parse_khz,
                       parse_pulses, pick_networks, strip_idle)

PIN_TSMP = board.TX
PIN_TSOP = board.RX
PIN_IR_TX = board.A3
PIN_LED = board.A0
PIN_SD_CS = board.A1
PIN_BUTTON = board.A2

SD_ROOT = "/sd"
LOG_FILE = SD_ROOT + "/aufnahmen.csv"   # mit Spalte name
CODES_FILE = SD_ROOT + "/codes.json"   # gelernte Codes je Taste
CODE_KEEP = 5            # so viele Druecke je Taste werden verglichen
LOG_HEADER = "zeit,aufnahme,taste,name,traeger_khz,tsop_pulse,pulse_us\n"
# beides kann in settings.toml ueberschrieben werden (der Simulator auf dem Mac tut das)
WEB_ROOT = os.getenv("IRLAB_WEB_ROOT") or "/web"
WEB_PORT = int(os.getenv("IRLAB_WEB_PORT") or 80)
MDNS_NAME = "irlab"     # -> http://irlab.local/
_pin = os.getenv("IRLAB_PIN")                 # optional in settings.toml, z.B. IRLAB_PIN = "4711"
WEB_PIN = str(_pin).strip() if _pin not in (None, "") else ""
PIN_MAX_FAILS = 5        # danach ...
PIN_LOCK_S = 60          # ... so lange keine PIN-Versuche
pin_fails = 0
pin_locked_until = 0.0
TZ_OFFSET = 1            # Stunden zu UTC (MEZ; im Sommer 2)

QUIET_S = 0.15           # so lange keine neuen Pulse = Tastendruck vorbei
LONG_PRESS_S = 1.0
TSMP_MAX = 3000
TSOP_MAX = MAX_PULSES
LED_ON = 20000           # PWM-Helligkeit beim Blitzen (0..65535)
KEEP_RECORDS = 40        # so viele Aufnahmen bleiben mit Pulsen im Speicher
KEEP_LOG = 120           # so viele Protokollzeilen kann die Webseite nachladen

TX_DUTY = 0x5555         # 1/3 Tastverhaeltnis, wie bei den meisten Fernbedienungen
TX_DEFAULT_KHZ = 36
ECHO_WINDOW_S = 1.0      # Aufnahmen so kurz nach dem Senden sind das eigene Echo
# Testmuster: Startimpuls, dann 8 Bits (kurz/lang), in Mikrosekunden, beginnt mit "an"
TEST_PATTERN = [3000, 1500] + [500, 500, 500, 1500] * 4 + [500]


# ---------------------------------------------------------------- Protokoll

log_lines = []           # (Nummer, Text), die Webseite holt nur neue
log_seq = 0


def log(*parts):
    global log_seq
    text = " ".join(str(p) for p in parts)
    print(text)
    for line in text.split("\n"):
        if line.strip():
            log_seq += 1
            log_lines.append((log_seq, line))
    while len(log_lines) > KEEP_LOG:
        log_lines.pop(0)


# ---------------------------------------------------------------- LED (blinkt ohne zu blockieren)

try:
    led = pwmio.PWMOut(PIN_LED, frequency=1000, duty_cycle=0)
except Exception as e:
    led = None
    print("Keine LED:", e)
led_plan = []            # (Zeitpunkt, Helligkeit)


def blink(times=1, on=0.05, off=0.15):
    t = max([time.monotonic()] + [p[0] for p in led_plan])
    for _ in range(times):
        led_plan.append((t, LED_ON))
        led_plan.append((t + on, 0))
        t += on + off


def led_tick(now):
    while led_plan and led_plan[0][0] <= now:
        _, duty = led_plan.pop(0)
        if led is not None:
            led.duty_cycle = duty


# ---------------------------------------------------------------- WLAN, Uhrzeit (NTP)

# Mehrere WLANs in settings.toml, z.B. Buero und Zuhause:
#   CIRCUITPY_WIFI_SSID / CIRCUITPY_WIFI_PASSWORD   (verbindet CircuitPython selbst)
#   WIFI_SSID_2 / WIFI_PASSWORD_2, WIFI_SSID_3 / WIFI_PASSWORD_3, ... bis _9
# Ist das Board beim Start nicht verbunden, sucht es die WLANs in der Naehe ab
# und verbindet sich mit dem staerksten bekannten.

def known_networks():
    nets = []
    first = os.getenv("CIRCUITPY_WIFI_SSID")
    if first:
        nets.append((first, os.getenv("CIRCUITPY_WIFI_PASSWORD") or ""))
    for i in range(2, 10):
        ssid = os.getenv("WIFI_SSID_%d" % i)
        if ssid:
            nets.append((ssid, os.getenv("WIFI_PASSWORD_%d" % i) or ""))
    return nets


def wifi_connect():
    if wifi.radio.connected:
        return True
    known = known_networks()
    if not known:
        print("Kein WLAN in settings.toml eingetragen")
        return False
    wifi.radio.enabled = True
    seen = []
    try:
        for n in wifi.radio.start_scanning_networks():
            seen.append((n.ssid, n.rssi))
    finally:
        wifi.radio.stop_scanning_networks()
    order = pick_networks(known, seen)
    if not order:
        print("Keines der %d bekannten WLANs in Reichweite (%s)"
              % (len(known), ", ".join(s for s, _ in known)))
        return False
    for ssid, pw in order:
        print("WLAN: verbinde mit", ssid, "...")
        try:
            wifi.radio.connect(ssid, pw, timeout=15)
            return True
        except Exception as e:
            print("WLAN", ssid, "fehlgeschlagen:", e)
    return False


pool = None
try:
    import socketpool
    import wifi
    if wifi_connect():
        pool = socketpool.SocketPool(wifi.radio)
        print("WLAN verbunden:", wifi.radio.ap_info.ssid)
except Exception as e:
    print("Kein WLAN:", e)


def sync_clock():
    if pool is None:
        return False
    try:
        import adafruit_ntp
        import rtc
        rtc.RTC().datetime = adafruit_ntp.NTP(pool, tz_offset=TZ_OFFSET).datetime
        return True
    except Exception as e:
        log("Keine Uhrzeit (NTP):", e)
        return False


clock_ok = sync_clock()


def stamp():
    if not clock_ok:
        return "t+%.1fs" % time.monotonic()
    t = time.localtime()
    return "%04d-%02d-%02d %02d:%02d:%02d" % t[:6]


# ---------------------------------------------------------------- SD-Karte

def mount_sd():
    try:
        import adafruit_sdcard
        import storage
        cs = digitalio.DigitalInOut(PIN_SD_CS)
        try:
            storage.mount(storage.VfsFat(adafruit_sdcard.SDCard(board.SPI(), cs)), SD_ROOT)
        except Exception:
            cs.deinit()
            raise
        log("SD-Karte eingehaengt")
        return True
    except Exception as e:
        log("Keine SD-Karte:", e)
        return False


sd_ok = mount_sd()


def log_capture(no, key, name, khz, pulses):
    """key 0 = Eigentest (Echo der eigenen Sendung)."""
    global sd_ok
    if not sd_ok:
        return
    try:
        try:
            new = os.stat(LOG_FILE)[6] == 0
        except OSError:
            new = True
        with open(LOG_FILE, "a") as f:
            if new:
                f.write(LOG_HEADER)
            f.write('%s,%d,%d,"%s",%s,%d,"%s"\n' % (
                stamp(), no, key, name.replace('"', "'"), "" if khz is None else "%.2f" % khz,
                len(pulses), " ".join(str(p) for p in pulses)))
    except OSError as e:
        log("SD-Schreibfehler:", e)
        sd_ok = False


# ---------------------------------------------------------------- Tastennummer

key_no = 1
key_names = {}           # "Tastennummer" (als Text, wegen JSON) -> Name, von der Webseite


def set_name(n, name):
    name = name.strip()[:40]
    if name:
        key_names[str(n)] = name
    else:
        key_names.pop(str(n), None)
    for r in records:
        if r["kind"] == "ir" and r["key"] == n:
            r["name"] = name
    log("Taste %d heisst jetzt: %s" % (n, name or "(ohne Namen)"))


def key_label(n):
    name = key_names.get(str(n))
    return "Taste %d" % n + (" (%s)" % name if name else "")


def set_key(n, source):
    global key_no
    key_no = max(1, min(99, n))
    log(">>> Jetzt %s der Fernbedienung (%s)" % (key_label(key_no), source))
    blink(key_no, on=0.15, off=0.25)


try:
    keys = keypad.Keys((PIN_BUTTON,), value_when_pressed=False, pull=True)
except Exception as e:
    keys = None
    log("Kein Taster:", e)
key_event = keypad.Event()
pressed_at = None


def poll_button():
    """Kurz = naechste Taste, lang = zurueck auf 1."""
    global pressed_at
    if keys is None:
        return
    while keys.events.get_into(key_event):
        if key_event.pressed:
            pressed_at = time.monotonic()
        elif pressed_at is not None:
            if time.monotonic() - pressed_at >= LONG_PRESS_S:
                set_key(1, "Taster lang")
            else:
                set_key(key_no + 1, "Taster")
            pressed_at = None


# ---------------------------------------------------------------- Aufnahmen

# Jede Aufnahme: dict mit no, t, key, khz, n, kind ("ir" = Fernbedienung,
# "echo" = eigene Sendung) und bei echo: src, ok, text. Pulse liegen getrennt in
# pulse_store, damit /api/state klein bleibt.
records = []
pulse_store = {}         # no -> {"p": empfangene Pulse, "s": gesendete Pulse oder None}
capture_no = 0
session = "%08x" % random.getrandbits(32)   # aendert sich bei Neustart und "Liste leeren"


def add_record(rec, got, sent=None):
    records.append(rec)
    pulse_store[rec["no"]] = {"p": got, "s": sent}
    while len(records) > KEEP_RECORDS:
        old = records.pop(0)
        pulse_store.pop(old["no"], None)


def find_record(no):
    for r in records:
        if r["no"] == no:
            return r
    return None


def clear_records():
    global session
    records.clear()
    pulse_store.clear()
    session = "%08x" % random.getrandbits(32)
    log("Aufnahmeliste geleert")


def restart_session():
    clear_records()
    key_names.clear()
    set_key(1, "Neu anfangen")


# ---------------------------------------------------------------- IR empfangen

# idle_state=True: beide Empfaenger sind in Ruhe HIGH und ziehen bei IR auf LOW
tsmp = pulseio.PulseIn(PIN_TSMP, maxlen=TSMP_MAX, idle_state=True)
tsop = pulseio.PulseIn(PIN_TSOP, maxlen=TSOP_MAX, idle_state=True)


def drain(p):
    """Puffer auslesen, leeren und weiter aufzeichnen."""
    p.pause()
    data = [p[i] for i in range(len(p))]
    p.clear()
    p.resume()
    return data


def report_carrier(pulses):
    f, bursts = carrier_khz(pulses)
    if f is None:
        log("[TSMP] %d Pulse, aber kein auswertbarer Burst" % len(pulses))
        return None
    log("[TSMP] Traeger: %.2f kHz (%d Bursts, min %.2f / max %.2f kHz%s)"
        % (f, len(bursts), min(bursts), max(bursts),
           ", Puffer voll" if len(pulses) >= TSMP_MAX else ""))
    best = nearest_std(f)
    hint = {36: "TSOP34836 verwenden", 38: "TSOP38238 verwenden"}.get(
        best, "36/38-kHz-TSOP passt nur eingeschraenkt")
    log("[TSMP] Naechste Standardfrequenz: %d kHz -> %s" % (best, hint))
    return f


# ---------------------------------------------------------------- IR senden

tx = None
tx_hz = 0
pending = None           # erwartetes Echo: {"sent", "khz", "t", "src"}


def ir_send(pulses, khz, src):
    """Sendet Pulse (us, beginnt mit 'an') auf der Traegerfrequenz khz."""
    global tx, tx_hz, pending
    hz = int(round(khz * 10)) * 100
    if tx is None or tx_hz != hz:
        if tx is not None:
            tx.deinit()
        tx = pulseio.PulseOut(PIN_IR_TX, frequency=hz, duty_cycle=TX_DUTY)
        tx_hz = hz
    data = array.array("H", [min(max(int(p), 1), 65535) for p in pulses])
    log("[SEND] %s: %d Pulse mit %.1f kHz" % (src, len(data), hz / 1000))
    tx.send(data)
    pending = {"sent": list(data), "khz": hz / 1000, "t": time.monotonic(), "src": src}


def send_test(khz):
    ir_send(TEST_PATTERN, khz, "Testmuster")


def send_replay(no):
    rec = find_record(no)
    if rec is None or no not in pulse_store:
        raise ValueError("Aufnahme #%d ist nicht (mehr) im Speicher" % no)
    ir_send(pulse_store[no]["p"], rec["khz"] or TX_DEFAULT_KHZ, "Aufnahme #%d" % no)


# ---------------------------------------------------------------- gelernte Codes
# codes["8"] = {"name": "OP Licht", "khz": 38.7, "frames": [[...], ...]}
# Ein Paket je Druck (die letzten CODE_KEEP). Gesendet wird das Paket, mit dem die
# meisten Druecke uebereinstimmen. Liegt auf der SD-Karte, uebersteht Neustarts.

codes = {}
learn_key = 0            # 0 = nicht lernen; sonst landen Aufnahmen dieser Taste in codes


CODES_BACKUP = os.getenv("IRLAB_CODES_BACKUP") or "/codes.json"   # Kopie im Board-Speicher (deploy.sh), falls die SD-Karte fehlt


def load_codes():
    global codes
    for path, where in ((CODES_FILE, "SD-Karte"), (CODES_BACKUP, "Board-Speicher (Sicherung)")):
        if path == CODES_FILE and not sd_ok:
            continue
        try:
            with open(path) as f:
                codes = json.load(f)
            log("Gelernte Codes: %d Tasten von %s" % (len(codes), where))
            return
        except OSError:
            pass
        except ValueError as e:
            log("%s kaputt, ignoriert: %s" % (path, e))


def save_codes():
    if not sd_ok:
        log("Keine SD-Karte: Codes nur bis zum Neustart")
        return
    try:
        with open(CODES_FILE, "w") as f:
            json.dump(codes, f)
    except OSError as e:
        log("SD-Schreibfehler codes.json:", e)


def code_summary():
    out = {}
    for k, e in codes.items():
        _, agree = majority(e["frames"])
        out[k] = {"name": e.get("name", ""), "n": len(e["frames"]), "agree": agree,
                  "len": len(e["frames"][0]) if e["frames"] else 0}
    return out


def learn(key, name, khz, pulses):
    frame = best_frame(pulses)
    if len(frame) < 8:
        log("[LERNEN] %s: nur %d Pulse, nicht uebernommen – nochmal druecken" % (key_label(key), len(frame)))
        return
    e = codes.setdefault(str(key), {"name": name, "khz": None, "frames": []})
    e["name"] = name or e.get("name", "")
    if khz:
        e["khz"] = round(khz, 2)
    e["frames"].append(frame)
    del e["frames"][:-CODE_KEEP]
    _, agree = majority(e["frames"])
    log("[LERNEN] %s: %d von %d Druecken gleich" % (key_label(key), agree, len(e["frames"])))
    save_codes()


def send_code(key):
    e = codes.get(str(key))
    if not e or not e["frames"]:
        raise ValueError("Taste %d ist noch nicht gelernt" % key)
    i, _ = majority(e["frames"])
    ir_send(code_pulses(e["frames"][i]), e.get("khz") or 38.7, e.get("name") or "Taste %d" % key)


def forget_code(key):
    codes.pop(str(key), None)
    save_codes()
    log("Code von %s geloescht" % key_label(key))


NOISE_MAX_PULSES = 7     # so kurze Aufnahmen ohne eigene Sendung sind Stoerungen, kein Tastendruck
NOISE_REPORT_S = 60
noise_count = 0
noise_reported = 0.0


def handle_capture(now):
    global capture_no, pending, noise_count, noise_reported
    is_echo = pending is not None and now - pending["t"] < ECHO_WINDOW_S + QUIET_S
    t = strip_idle(drain(tsmp))
    c = strip_idle(drain(tsop))
    if not is_echo and len(c) <= NOISE_MAX_PULSES:
        noise_count += 1
        if now - noise_reported > NOISE_REPORT_S:
            log("(%d kurze Stoerpulse ignoriert)" % noise_count)
            noise_count = 0
            noise_reported = now
        return
    capture_no += 1
    key = 0 if is_echo else key_no
    log("===== Aufnahme #%d, %s =====" % (
        capture_no, "Eigentest " + pending["src"] if is_echo else key_label(key_no)))
    khz = report_carrier(t) if t else None
    if not t:
        log("[TSMP] nichts empfangen")
    if c:
        log("[TSOP] %d Pulse%s" % (len(c), " (Puffer voll!)" if len(c) >= TSOP_MAX else ""))
        print(c)
    else:
        log("[TSOP] nichts empfangen")
    name = "" if is_echo else key_names.get(str(key), "")
    rec = {"no": capture_no, "t": stamp(), "key": key, "khz": khz, "n": len(c),
           "kind": "echo" if is_echo else "ir", "name": name}
    if is_echo:
        res = compare_echo(pending["sent"], c, pending["khz"], khz)
        rec.update({"src": pending["src"], "ok": res["ok"], "text": res["text"]})
        log("[ECHO] %s: %s" % ("OK" if res["ok"] else "FEHLER", res["text"]))
        add_record(rec, c, pending["sent"])
        pending = None
    elif c:
        add_record(rec, c)
        if learn_key and key == learn_key:
            learn(key, name, khz, c)
    log_capture(capture_no, key, name, khz, c)
    blink(1)


def check_missing_echo(now):
    """Kam nach dem Senden gar nichts an, wird das als Fehlschlag festgehalten."""
    global capture_no, pending
    if pending is None or now - pending["t"] <= ECHO_WINDOW_S + QUIET_S:
        return
    capture_no += 1
    text = "nichts empfangen -> IR-LED, Transistor und Verdrahtung pruefen"
    log("[ECHO] FEHLER %s: %s" % (pending["src"], text))
    add_record({"no": capture_no, "t": stamp(), "key": 0, "khz": None, "n": 0,
                "kind": "echo", "src": pending["src"], "ok": False, "text": text},
               [], pending["sent"])
    pending = None


# ---------------------------------------------------------------- serielle Befehle

HELP = """Befehle:
  t [kHz]   Testmuster senden (Standard %d kHz)
  r [n]     Aufnahme n erneut senden (ohne n: die letzte)
  l         gespeicherte Aufnahmen auflisten
  h         diese Hilfe""" % TX_DEFAULT_KHZ

cmd_buf = ""


def handle_command(line):
    parts = line.split()
    cmd, args = parts[0].lower(), parts[1:]
    try:
        if cmd == "t":
            send_test(parse_khz(args[0] if args else None, TX_DEFAULT_KHZ))
        elif cmd == "r":
            ir_recs = [r["no"] for r in records if r["kind"] == "ir"]
            if not ir_recs:
                print("Noch keine Aufnahme zum Senden")
                return
            send_replay(int(args[0]) if args else ir_recs[-1])
        elif cmd == "l":
            if not records:
                print("Keine Aufnahmen im Speicher")
            for r in records:
                print("  #%d  %s  %s  %d Pulse  %s" % (
                    r["no"], "Taste %d" % r["key"] if r["kind"] == "ir" else "Eigentest",
                    "?" if r["khz"] is None else "%.2f kHz" % r["khz"], r["n"],
                    r.get("text", "")))
        else:
            print(HELP)
    except Exception as e:
        print("Fehler bei '%s': %s" % (line, e))


def poll_serial():
    global cmd_buf
    while supervisor.runtime.serial_bytes_available:
        ch = sys.stdin.read(1)
        if ch in "\r\n":
            line, cmd_buf = cmd_buf.strip(), ""
            if line:
                handle_command(line)
        else:
            cmd_buf += ch


# ---------------------------------------------------------------- Webserver

mdns_server = None   # global halten, sonst raeumt der GC es weg und irlab.local verschwindet


def start_web():
    global mdns_server
    if pool is None:
        log("Kein WLAN -> keine Webseite, nur Konsole und Taster")
        return None
    try:
        from adafruit_httpserver import (BAD_REQUEST_400, FORBIDDEN_403, GET, NOT_FOUND_404,
                                         POST, TOO_MANY_REQUESTS_429, UNAUTHORIZED_401,
                                         FileResponse, JSONResponse, Server)
    except ImportError as e:
        log("adafruit_httpserver fehlt in lib/ -> keine Webseite:", e)
        return None

    server = Server(pool, WEB_ROOT, debug=False)
    # Kein "Access-Control-Allow-Origin": fremde Webseiten sollen das Board weder
    # steuern noch auslesen koennen (siehe guard unten).

    def ok(request, msg, **extra):
        data = {"ok": True, "msg": msg}
        data.update(extra)
        return JSONResponse(request, data)

    def fail(request, msg, status=BAD_REQUEST_400):
        return JSONResponse(request, {"ok": False, "msg": msg}, status=status)

    def qint(request, name, default=None):
        v = request.query_params.get(name)
        return default if v in (None, "") else int(v)

    def host_ok(request):
        """Schutz gegen DNS-Rebinding: nur unter eigener IP, irlab.local, localhost."""
        host = (request.headers.get("Host") or "").split(":")[0].lower()
        allowed = ("localhost", "127.0.0.1", MDNS_NAME + ".local")
        try:
            allowed += (str(wifi.radio.ipv4_address),)
        except Exception:
            pass
        return host in allowed

    def pin_check(request):
        """None = in Ordnung, sonst die Fehlerantwort."""
        global pin_fails, pin_locked_until
        if not WEB_PIN:
            return None
        now = time.monotonic()
        if now < pin_locked_until:
            return fail(request, "Zu viele falsche PINs - bitte %d s warten"
                        % (pin_locked_until - now + 1), TOO_MANY_REQUESTS_429)
        if request.headers.get("X-IR-Lab-Pin") == WEB_PIN:
            pin_fails = 0
            return None
        if request.headers.get("X-IR-Lab-Pin"):
            pin_fails += 1
            log("Falsche PIN (%d. Versuch)" % pin_fails)
            if pin_fails >= PIN_MAX_FAILS:
                pin_locked_until = now + PIN_LOCK_S
                pin_fails = 0
                log("PIN gesperrt fuer %d s" % PIN_LOCK_S)
        return fail(request, "PIN noetig", UNAUTHORIZED_401)

    def guard(post=False, pin=True):
        """Schutz fuer jede Route:
        - Host-Pruefung (DNS-Rebinding)
        - POST nur mit Kopfzeile X-IR-Lab: 1. Fremde Webseiten koennen sie nicht
          setzen, ohne dass der Browser vorher fragt (CORS) - und das Board erlaubt es nie.
        - PIN aus settings.toml (IRLAB_PIN), falls gesetzt."""
        def deco(fn):
            def wrapped(request):
                if not host_ok(request):
                    return fail(request, "Unbekannter Host", FORBIDDEN_403)
                if post and request.headers.get("X-IR-Lab") != "1":
                    return fail(request, "Anfrage ohne X-IR-Lab-Kennung abgelehnt", FORBIDDEN_403)
                if pin:
                    bad = pin_check(request)
                    if bad is not None:
                        return bad
                return fn(request)
            return wrapped
        return deco

    @server.route("/", GET)
    @guard(pin=False)
    def index(request):
        return FileResponse(request, "index.html", WEB_ROOT)

    @server.route("/api/state", GET)
    @guard()
    def state(request):
        since = qint(request, "since", 0)
        log_after = qint(request, "log_after", 0)
        return JSONResponse(request, {
            "session": session, "key": key_no, "names": key_names, "sd": sd_ok, "clock": clock_ok,
            "learn": learn_key, "codes": code_summary(),
            "time": stamp(), "busy": pending is not None,
            "records": [r for r in records if r["no"] > since],
            "first": records[0]["no"] if records else 0,
            "log": [l for l in log_lines if l[0] > log_after],
            "log_seq": log_seq,
        })

    @server.route("/api/capture", GET)
    @guard()
    def capture(request):
        no = qint(request, "no")
        if no not in pulse_store:
            return fail(request, "Aufnahme #%s nicht im Speicher" % no, NOT_FOUND_404)
        return JSONResponse(request, {"no": no, "pulses": pulse_store[no]["p"],
                                      "sent": pulse_store[no]["s"]})

    @server.route("/api/key", POST)
    @guard(post=True)
    def key(request):
        op = request.query_params.get("op")
        try:
            if op == "next":
                set_key(key_no + 1, "Webseite")
            elif op == "prev":
                set_key(key_no - 1, "Webseite")
            elif op == "reset":
                set_key(1, "Webseite")
            elif op == "set":
                set_key(qint(request, "n"), "Webseite")
            elif op == "name":
                set_name(qint(request, "n", key_no), request.body.decode("utf-8"))
                return ok(request, "Name gespeichert", key=key_no, names=key_names)
            elif op == "restart":
                restart_session()
            else:
                return fail(request, "unbekannte Aktion %s" % op)
        except (TypeError, ValueError):
            return fail(request, "ungueltige Tastennummer")
        return ok(request, "Jetzt Taste %d" % key_no, key=key_no)

    @server.route("/api/send/test", POST)
    @guard(post=True)
    def api_test(request):
        try:
            khz = parse_khz(request.query_params.get("khz"), TX_DEFAULT_KHZ)
            send_test(khz)
        except Exception as e:
            return fail(request, str(e))
        return ok(request, "Testmuster mit %.1f kHz gesendet" % khz)

    @server.route("/api/send/replay", POST)
    @guard(post=True)
    def api_replay(request):
        try:
            no = qint(request, "no")
            send_replay(no)
        except Exception as e:
            return fail(request, str(e))
        return ok(request, "Aufnahme #%d gesendet" % no)

    @server.route("/api/send/raw", POST)
    @guard(post=True)
    def api_raw(request):
        try:
            khz = parse_khz(request.query_params.get("khz"), TX_DEFAULT_KHZ)
            pulses = parse_pulses(request.body.decode("utf-8"))
            ir_send(pulses, khz, "Eigener Code")
        except Exception as e:
            return fail(request, str(e))
        return ok(request, "%d Pulse mit %.1f kHz gesendet" % (len(pulses), khz))

    @server.route("/api/learn", POST)
    @guard(post=True)
    def api_learn(request):
        """n=Taste, Name im Body: ab jetzt diese Taste lernen. n=0: Lernen aus."""
        global learn_key
        try:
            n = qint(request, "n", 0)
        except ValueError:
            return fail(request, "ungueltige Tastennummer")
        if n <= 0:
            learn_key = 0
            log("Lernen aus")
            return ok(request, "Lernen aus")
        name = request.body.decode("utf-8").strip()
        if name and key_names.get(str(n)) != name:
            set_name(n, name)
        learn_key = n
        set_key(n, "Fernbedienung")
        return ok(request, "%s: jetzt 2-3x auf der echten Fernbedienung druecken" % (name or "Taste %d" % n))

    @server.route("/api/code/send", POST)
    @guard(post=True)
    def api_code_send(request):
        try:
            send_code(qint(request, "n", 0))
        except Exception as e:
            return fail(request, str(e))
        return ok(request, "gesendet")

    @server.route("/api/code/forget", POST)
    @guard(post=True)
    def api_code_forget(request):
        n = qint(request, "n", 0)
        forget_code(n)
        return ok(request, "Code geloescht")

    @server.route("/api/clear", POST)
    @guard(post=True)
    def api_clear(request):
        clear_records()
        return ok(request, "Liste geleert")

    try:
        ip = str(wifi.radio.ipv4_address)
        server.start(ip, port=WEB_PORT)
    except Exception as e:
        log("Webserver startet nicht:", e)
        return None
    url = "http://%s/" % ip
    try:
        import mdns
        mdns_server = mdns.Server(wifi.radio)
        mdns_server.hostname = MDNS_NAME
        mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=WEB_PORT)
        url += "  oder  http://%s.local/" % MDNS_NAME
    except Exception as e:
        print("mDNS-Name nicht gesetzt:", e)
    log("Webseite: " + url)
    log("PIN-Schutz: %s" % ("an" if WEB_PIN else "aus (IRLAB_PIN in settings.toml setzen)"))
    return server


# ---------------------------------------------------------------- Start

print()
log("IR-Labor bereit. TSMP98000 an TX, TSOP an RX, IR-LED an A3.")
log("SD: %s   Uhrzeit: %s" % ("ja" if sd_ok else "nein", stamp() if clock_ok else "nein"))
load_codes()
web = start_web()
print(HELP)
log(">>> Jetzt Taste 1 der Fernbedienung")
blink(1)

# ---------------------------------------------------------------- WLAN-Waechter
# Faellt das WLAN weg (Router-Neustart, DHCP), verbindet sich das Board selbst
# neu und startet den Webserver wieder.

WIFI_CHECK_S = 15
wifi_checked = time.monotonic()


def wifi_ok():
    return wifi.radio.connected and wifi.radio.ipv4_address is not None


def wifi_watch(now):
    global wifi_checked, pool, web, mdns_server
    if now - wifi_checked < WIFI_CHECK_S:
        return
    wifi_checked = now
    try:
        if wifi_ok():
            return
    except NameError:
        return                      # kein wifi-Modul (Simulator ohne WLAN)
    log("WLAN weg - verbinde neu ...")
    try:
        wifi.radio.enabled = False
        time.sleep(0.5)
        wifi.radio.enabled = True
        if not wifi_connect() or not wifi_ok():
            log("WLAN noch nicht wieder da, neuer Versuch in %d s" % WIFI_CHECK_S)
            return
        if web is not None:
            try:
                web.stop()
            except Exception:
                pass
        if mdns_server is not None:
            try:
                mdns_server.deinit()
            except Exception:
                pass
            mdns_server = None
        pool = socketpool.SocketPool(wifi.radio)
        web = start_web()
    except Exception as e:
        log("WLAN-Neuverbindung fehlgeschlagen:", e)
    wifi_checked = time.monotonic()


# ---------------------------------------------------------------- Hauptschleife

last_len = 0
last_change = time.monotonic()

while True:
    now = time.monotonic()
    led_tick(now)
    poll_button()
    poll_serial()
    wifi_watch(now)
    if web is not None:
        try:
            web.poll()
        except Exception as e:
            log("Webserver-Fehler:", e)
    n = len(tsmp) + len(tsop)
    now = time.monotonic()
    if n != last_len:
        last_len = n
        last_change = now
    elif n > 0 and now - last_change > QUIET_S:
        handle_capture(now)
        last_len = 0
    elif n == 0:
        check_missing_echo(now)
    time.sleep(0.005)
