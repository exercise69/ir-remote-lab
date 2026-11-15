# IR-Labor – Auswertung ohne Hardware-Zugriff.
#
# Reine Funktionen: laufen auf dem Board (CircuitPython) und auf dem Mac (CPython),
# damit sie sich dort testen lassen: python3 test_ir_lab.py

BURST_GAP_US = 100       # laengere Pause im TSMP-Signal = neuer Burst (Traeger >= 20 kHz)
STD_KHZ = (30, 33, 36, 38, 40, 56)
MAX_PULSES = 1000
ECHO_TOL_US = 200        # so weit darf ein empfangener Puls vom gesendeten abweichen
ECHO_TOL_KHZ = 1.0       # so weit darf die gemessene Frequenz von der gesendeten abweichen


def carrier_khz(pulses, gap_us=BURST_GAP_US):
    """Traegerfrequenz aus TSMP-Pulsen. Gibt (kHz oder None, [kHz je Burst]) zurueck.

    pulses wechselt LOW, HIGH, LOW, ... (beginnt mit LOW). Innerhalb eines Bursts ist
    die Zeit vom ersten bis zum letzten LOW-Beginn = (Anzahl LOWs - 1) Perioden.
    Mitteln ueber ganze Bursts umgeht die 1-us-Aufloesung.
    """
    # Ende sauber abschliessen: auf LOW enden lassen und eine lange Pause anhaengen,
    # damit auch der letzte Burst ausgewertet wird
    pulses = list(pulses)
    if len(pulses) % 2 == 0 and pulses:
        pulses.pop()
    pulses.append(gap_us + 1)

    sum_us = 0
    sum_periods = 0
    bursts = []
    burst_us = 0
    burst_lows = 0
    for i, d in enumerate(pulses):
        if i % 2 == 0:
            burst_lows += 1
            burst_us += d
        elif d > gap_us:
            # Burst zu Ende; die letzte LOW-Dauer gehoert nicht zur Periodensumme
            if burst_lows >= 8:
                us = burst_us - pulses[i - 1]
                if us > 0:
                    sum_us += us
                    sum_periods += burst_lows - 1
                    bursts.append((burst_lows - 1) * 1000 / us)
            burst_us = 0
            burst_lows = 0
        else:
            burst_us += d
    if not bursts:
        return None, bursts
    return sum_periods * 1000 / sum_us, bursts


def strip_idle(pulses):
    """Entfernt das Endzeichen 65535, das PulseIn auf dem ESP32 nach der letzten
    Flanke anhaengt (Pause laenger als der Zaehler reicht). Es ist kein Teil des Codes."""
    pulses = list(pulses)
    while pulses and pulses[-1] >= 65535:
        pulses.pop()
    return pulses


def nearest_std(khz):
    return min(STD_KHZ, key=lambda s: abs(s - khz))


def compare_echo(sent, got, sent_khz, got_khz):
    """Vergleicht eine eigene Sendung mit dem, was die Empfaenger davon gesehen haben.

    Gibt ein dict zurueck: ok, text, sent_n, got_n, sent_khz, got_khz, max_dev.
    """
    res = {"ok": False, "sent_n": len(sent), "got_n": len(got),
           "sent_khz": sent_khz, "got_khz": got_khz, "max_dev": None}
    problems = []
    if got_khz is None:
        problems.append("TSMP hat keine Frequenz gemessen")
    elif abs(got_khz - sent_khz) > ECHO_TOL_KHZ:
        problems.append("Frequenz %.2f statt %.1f kHz" % (got_khz, sent_khz))
    if not got:
        problems.append("TSOP hat nichts empfangen")
    elif len(got) != len(sent):
        problems.append("TSOP: %d statt %d Pulse" % (len(got), len(sent)))
    else:
        max_dev = max(abs(g - s) for g, s in zip(got, sent))
        res["max_dev"] = max_dev
        if max_dev > ECHO_TOL_US:
            problems.append("Pulse weichen bis %d us ab" % max_dev)
    res["ok"] = not problems
    if problems:
        res["text"] = "; ".join(problems)
    else:
        res["text"] = "alle %d Pulse erkannt, %.2f kHz, max. %d us Abweichung" % (
            len(got), got_khz, res["max_dev"])
    return res


def parse_pulses(text):
    """Pulse aus Text: Zahlen getrennt durch Leerzeichen, Komma oder Zeilenumbruch,
    eckige Klammern erlaubt (so wie die Konsole sie ausgibt). Wirft ValueError."""
    for ch in "[](),;\n\r\t":
        text = text.replace(ch, " ")
    parts = text.split()
    if not parts:
        raise ValueError("keine Pulse angegeben")
    if len(parts) > MAX_PULSES:
        raise ValueError("hoechstens %d Pulse" % MAX_PULSES)
    pulses = []
    for p in parts:
        try:
            v = int(p)
        except ValueError:
            raise ValueError("'%s' ist keine ganze Zahl" % p)
        if not 1 <= v <= 65535:
            raise ValueError("%d liegt nicht zwischen 1 und 65535 us" % v)
        pulses.append(v)
    return pulses


def parse_khz(text, default):
    if text is None or text == "":
        return default
    khz = float(text)
    if not 20 <= khz <= 60:
        raise ValueError("Frequenz muss zwischen 20 und 60 kHz liegen")
    return khz


def pick_networks(known, seen):
    """Reihenfolge der Verbindungsversuche.

    known: Liste (ssid, passwort) aus settings.toml, in Prioritaetsreihenfolge.
    seen:  Liste (ssid, rssi) aus dem WLAN-Scan (Duplikate erlaubt, mehrere APs).
    Ergebnis: bekannte Netze, die gerade sichtbar sind, staerkstes zuerst.
    """
    best = {}
    for ssid, rssi in seen:
        if ssid not in best or rssi > best[ssid]:
            best[ssid] = rssi
    order = []
    for prio, (ssid, pw) in enumerate(known):
        if ssid in best and all(ssid != o[0] for o in order):
            order.append((ssid, pw, best[ssid], prio))
    order.sort(key=lambda o: (-o[2], o[3]))
    return [(ssid, pw) for ssid, pw, _, _ in order]


# ---------------------------------------------------------------- Codes lernen

FRAME_GAP_US = 20000     # laengere Pause = neues Paket (Wiederholung beim Gedrueckthalten)
SEND_REPEATS = 3         # so oft wird ein gelerntes Paket gesendet (wie die Fernbedienung)


def split_frames(pulses, gap_us=FRAME_GAP_US):
    """Teilt eine Aufnahme an langen Pausen in Pakete (Pausen selbst fallen weg)."""
    frames, cur = [], []
    for i, p in enumerate(pulses):
        if p >= gap_us and i % 2 == 1:      # nur Pausen (ungerade Stellen) trennen
            if cur:
                frames.append(cur)
            cur = []
        elif p >= gap_us:
            continue                        # ueberlaufendes "an" am Anfang: ignorieren
        else:
            cur.append(p)
    if cur:
        frames.append(cur)
    return frames


def best_frame(pulses):
    """Ein vollstaendiges Paket: das zweite, falls vorhanden (beim ersten fehlt
    oft der Anfang, weil die Empfaenger erst einschwingen), sonst das erste."""
    frames = split_frames(pulses)
    if not frames:
        return []
    return frames[1] if len(frames) >= 2 else frames[0]


def same_frame(a, b, tol=ECHO_TOL_US):
    return bool(a) and len(a) == len(b) and max(abs(x - y) for x, y in zip(a, b)) <= tol


def majority(frames):
    """(Index des Pakets, mit dem die meisten uebereinstimmen; Anzahl Uebereinstimmungen)."""
    best, best_n = -1, 0
    for i, f in enumerate(frames):
        n = sum(1 for g in frames if same_frame(f, g))
        if n > best_n:
            best, best_n = i, n
    return best, best_n


SEND_GAP_US = 60000      # Pause zwischen den Paketen. Die echte ist laenger als 65,5 ms
                         # (PulseIn zeigt 65535 = Ueberlauf); 65535 selbst bringt beim
                         # Eigentest das Paket danach durcheinander, 60 ms klappen sauber.


def code_pulses(frame, repeats=SEND_REPEATS, gap_us=SEND_GAP_US):
    """Sendefolge: Paket, Pause, Paket, ... (beginnt und endet mit 'an')."""
    out = []
    for r in range(repeats):
        if r:
            out.append(gap_us)
        out.extend(frame)
    return out
