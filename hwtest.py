#!/usr/bin/env python3
# Hardware-Test fuer das IR-Labor – laeuft auf dem Mac, nicht auf dem Board.
#
#   .venv/bin/python hwtest.py            (Board per USB anschliessen)
#
# Teil 1 haelt code.py an und prueft ueber die REPL jedes Bauteil einzeln:
#   Ruhepegel der Empfaenger an TX/RX, Stoerlicht, Taster A2, LED A0 (blinkt 3x),
#   SD-Karte (schreiben + lesen), IR-LED ueber A3 -> Empfang an TSMP und TSOP.
# Teil 2 startet code.py neu und laesst es selbst senden ("t", "t 38"),
#   damit auch der echte Programmablauf mit Eigentest geprueft ist.

import ast
import glob
import re
import sys
import time

import serial

BOARD_CODE = r'''
import array, board, digitalio, pulseio, time
from ir_lab import carrier_khz, compare_echo, strip_idle

def out(k, v):
    print("@@" + k, repr(v))

def level(pin, pull=None):
    d = digitalio.DigitalInOut(pin)
    d.switch_to_input(pull=pull)
    hi = 0
    for _ in range(200):
        hi += d.value
        time.sleep(0.0025)
    d.deinit()
    return hi, 200 - hi

out("tx_level", level(board.TX))
out("rx_level", level(board.RX))
out("a2_level", level(board.A2, digitalio.Pull.UP))

def listen(sec, send=None, khz=36):
    a = pulseio.PulseIn(board.TX, maxlen=3000, idle_state=True)
    b = pulseio.PulseIn(board.RX, maxlen=1000, idle_state=True)
    time.sleep(0.05)
    a.clear(); b.clear()
    if send:
        o = pulseio.PulseOut(board.A3, frequency=int(khz * 1000), duty_cycle=0x5555)
        o.send(array.array("H", send))
        o.deinit()
    time.sleep(sec)
    a.pause(); b.pause()
    ta = strip_idle([a[i] for i in range(len(a))])
    tb = strip_idle([b[i] for i in range(len(b))])
    a.deinit(); b.deinit()
    return ta, tb

ta, tb = listen(2.0)
out("noise", (len(ta), len(tb)))

PATTERN = [3000, 1500] + [500, 500, 500, 1500] * 4 + [500]
for khz in (36, 38):
    ta, tb = listen(0.3, PATTERN, khz)
    f = carrier_khz(ta)[0] if ta else None
    res = compare_echo(PATTERN, tb, khz, f)
    out("send%d" % khz, (len(ta), f, len(tb), res["ok"], res["text"], tb[:20]))

led = digitalio.DigitalInOut(board.A0)
led.switch_to_output(False)
for _ in range(3):
    led.value = True; time.sleep(0.25)
    led.value = False; time.sleep(0.25)
led.deinit()
out("led", "geblinkt")

try:
    import adafruit_sdcard, os, storage
    try:
        storage.umount("/sd")
    except Exception:
        pass
    cs = digitalio.DigitalInOut(board.A1)
    sd = adafruit_sdcard.SDCard(board.SPI(), cs)
    storage.mount(storage.VfsFat(sd), "/sd")
    with open("/sd/hwtest.tmp", "w") as f:
        f.write("irlab")
    with open("/sd/hwtest.tmp") as f:
        ok = f.read() == "irlab"
    os.remove("/sd/hwtest.tmp")
    storage.umount("/sd")
    cs.deinit()
    out("sd", (ok, "%d MB" % (sd.count() // 2048)))
except Exception as e:
    out("sd", (False, repr(e)))
'''


def find_port():
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not ports:
        sys.exit("Kein Board gefunden (/dev/cu.usbmodem*). QT Py per USB anschliessen.")
    return ports[0]


class Board:
    def __init__(self, port):
        self.s = serial.Serial(port, 115200, timeout=0.1)

    def read_for(self, sec, until=None, echo=True):
        buf = b""
        end = time.monotonic() + sec
        while time.monotonic() < end:
            chunk = self.s.read(4096)
            if chunk:
                buf += chunk
                if echo:
                    sys.stdout.write(chunk.decode("utf-8", "replace"))
                    sys.stdout.flush()
                if until and until.encode() in buf:
                    break
        return buf.decode("utf-8", "replace")

    def write(self, data, chunk=64):
        if isinstance(data, str):
            data = data.encode()
        for i in range(0, len(data), chunk):
            self.s.write(data[i:i + chunk])
            time.sleep(0.01)

    def enter_raw_repl(self):
        self.write(b"\r\x03\x03")
        self.read_for(1.5, echo=False)
        self.write(b"\r")
        self.read_for(1.0, until=">>> ", echo=False)
        self.write(b"\x01")
        got = self.read_for(2.0, until="raw REPL; CTRL-B to exit\r\n>", echo=False)
        if "raw REPL" not in got:
            sys.exit("REPL antwortet nicht. Laeuft eine andere serielle Konsole? Bitte schliessen.")

    def exec_raw(self, code, timeout=30):
        self.write(code)
        self.write(b"\x04")
        got = self.read_for(timeout, until="\x04>", echo=False)
        if not got.startswith("OK"):
            sys.exit("Board hat den Testcode nicht angenommen:\n" + got)
        stdout, _, rest = got[2:].partition("\x04")
        stderr = rest.partition("\x04")[0]
        return stdout, stderr


def verdict(ok, text):
    print("  %s  %s" % ("OK    " if ok else "FEHLER", text))
    return ok


def receiver_level(name, hi_lo):
    hi, lo = hi_lo
    if lo == 0:
        return verdict(True, "%s: Ruhepegel HIGH" % name)
    if hi == 0:
        return verdict(False, "%s: Ausgang dauerhaft LOW -> keine Versorgung (VS/GND) oder "
                       "OUT-Bein vertauscht" % name)
    return verdict(False, "%s: Ausgang flackert (%d von 200 Messungen LOW) -> Stoerlicht "
                   "oder wackliger Kontakt" % (name, lo))


def main():
    port = find_port()
    print("Board an", port)
    b = Board(port)

    print("\n=== Teil 1: Bauteile einzeln (code.py angehalten) ===")
    print("Fernbedienung bitte nicht benutzen. LED an A0 sollte gleich 3x blinken.\n")
    b.enter_raw_repl()
    stdout, stderr = b.exec_raw(BOARD_CODE)
    if stderr.strip():
        print(stdout)
        sys.exit("Fehler auf dem Board:\n" + stderr)
    r = {}
    for m in re.finditer(r"^@@(\w+) (.*)$", stdout, re.M):
        r[m.group(1)] = ast.literal_eval(m.group(2))

    results = []
    results.append(receiver_level("TSMP98000 an TX", r["tx_level"]))
    results.append(receiver_level("TSOP an RX", r["rx_level"]))
    a2_hi, a2_lo = r["a2_level"]
    results.append(verdict(a2_lo == 0, "Taster A2: %s" % (
        "nicht gedrueckt (HIGH)" if a2_lo == 0 else "liest LOW -> gedrueckt oder Kurzschluss nach GND")))
    nt, nr = r["noise"]
    results.append(verdict(nt == 0 and nr == 0,
                           "Stoerlicht in 2 s ohne Senden: TSMP %d, TSOP %d Pulse" % (nt, nr)))
    for khz in (36, 38):
        n_t, f, n_r, ok, text, head = r["send%d" % khz]
        ftxt = "%.2f kHz" % f if f else "keine Frequenz"
        if n_t == 0 and n_r == 0:
            results.append(verdict(False, "Senden %d kHz: nichts empfangen -> IR-LED-Polung, "
                                   "Transistor (E-B-C), R3/R4 und 5V pruefen" % khz))
        else:
            results.append(verdict(ok, "Senden %d kHz: TSMP %d Pulse (%s), TSOP %d Pulse – %s"
                                   % (khz, n_t, ftxt, n_r, text)))
            if not ok:
                print("          TSOP-Pulse (Anfang):", head)
    sd_ok, sd_info = r["sd"]
    print("  %s  SD-Karte: %s" % ("OK    " if sd_ok else "Hinweis", sd_info))
    print("  ?       LED an A0: hat sie 3x geblinkt? (kann ich nicht messen)")

    print("\n=== Teil 2: code.py neu starten und Eigentest ===\n")
    b.write(b"\x02")
    b.read_for(0.5, echo=False)
    b.write(b"\x04")
    b.read_for(30, until="Jetzt Taste 1")
    log = ""
    for cmd in ("t", "t 38"):
        b.write(cmd + "\r")
        log += b.read_for(4, until="[ECHO]")
        log += b.read_for(0.5)
    echo_ok = log.count("[ECHO] OK")
    results.append(verdict(echo_ok == 2, "code.py Eigentest: %d von 2 Sendungen OK" % echo_ok))

    print("\n=== Ergebnis: %d von %d Pruefungen bestanden ===" % (sum(results), len(results)))
    b.s.close()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
