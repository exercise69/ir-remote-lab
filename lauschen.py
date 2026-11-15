#!/usr/bin/env python3
# Lauscht mit TSMP und TSOP, ob die Haube selbst IR aussendet – laeuft auf dem Mac.
#
#   .venv/bin/python lauschen.py [Sekunden] [Taste@Sekunde ...]
#   .venv/bin/python lauschen.py 60 9@15 9@35     (Standard: Raum Licht an/aus)
#
# Haelt code.py an, hoert die ganze Zeit zu (ohne Stoerfilter) und sendet zu den
# angegebenen Zeiten gelernte Codes aus captures/codes.json. Danach startet
# code.py wieder. Jedes Signal wird mit Zeit, Pulszahl und Traeger aufgelistet.

import ast
import json
import re
import sys
import time

from ir_lab import code_pulses, majority
from hwtest import Board, find_port

BOARD_CODE = r'''
import array, board, pulseio, time
from ir_lab import carrier_khz, strip_idle

DUR = %(dur)r
SENDS = %(sends)r          # [(sekunde, name, khz, pulse), ...]
tsmp = pulseio.PulseIn(board.TX, maxlen=3000, idle_state=True)
tsop = pulseio.PulseIn(board.RX, maxlen=1000, idle_state=True)
tx = None
t0 = time.monotonic()
last_n, last_change, first = 0, t0, t0
i = 0
while True:
    now = time.monotonic()
    t = now - t0
    if t > DUR:
        break
    if i < len(SENDS) and t >= SENDS[i][0]:
        _, name, khz, pulses = SENDS[i]
        if tx is None:
            tx = pulseio.PulseOut(board.A3, frequency=int(khz * 1000), duty_cycle=0x5555)
        tx.send(array.array("H", pulses))
        print("@@ev", repr(("send", round(time.monotonic() - t0, 3), name, len(pulses))))
        i += 1
    n = len(tsmp) + len(tsop)
    if n != last_n:
        if last_n == 0:
            first = now
        last_n, last_change = n, now
    elif n and now - last_change > 0.15:
        tsmp.pause(); tsop.pause()
        a = [tsmp[k] for k in range(len(tsmp))]
        b = [tsop[k] for k in range(len(tsop))]
        tsmp.clear(); tsop.clear(); tsmp.resume(); tsop.resume()
        a, b = strip_idle(a), strip_idle(b)
        khz = carrier_khz(a)[0] if a else None
        start = round(first - t0, 3)
        print("@@ev", repr(("rx", start, len(a), round(khz, 2) if khz else None, len(b), b[:40])))
        last_n = 0
    time.sleep(0.002)
print("@@done")
'''


def main():
    args = sys.argv[1:]
    dur = float(args[0]) if args else 60
    plan = args[1:] or ["9@15", "9@35"]
    codes = json.load(open("captures/codes.json"))
    sends = []
    for p in plan:
        k, at = p.split("@")
        e = codes[k]
        frame = e["frames"][majority(e["frames"])[0]]
        sends.append((float(at), e["name"], e["khz"] or 38.7, code_pulses(frame)))
    sends.sort()

    b = Board(find_port())
    print("Lausche %d s, sende: %s" % (dur, ", ".join("%s bei %ds" % (s[1], s[0]) for s in sends)))
    for attempt in range(4):              # direkt nach Start/WLAN-Suche reagiert die REPL manchmal nicht
        try:
            b.enter_raw_repl()
            break
        except SystemExit:
            if attempt == 3:
                raise
            time.sleep(2)
    out, err = b.exec_raw(BOARD_CODE % {"dur": dur, "sends": sends}, timeout=dur + 30)
    b.write(b"\x02")
    b.read_for(0.5, echo=False)
    b.write(b"\x04")                       # code.py neu starten
    if err.strip():
        sys.exit("Fehler auf dem Board:\n" + err)

    evs = [ast.literal_eval(m.group(1)) for m in re.finditer(r"^@@ev (.*)$", out, re.M)]
    last_send = None
    print("\n  Zeit     Ereignis")
    for ev in evs:
        if ev[0] == "send":
            last_send = ev[1]
            print("%7.2f s  >>> gesendet: %s (%d Pulse)" % (ev[1], ev[2], ev[3]))
            continue
        _, t, n_tsmp, khz, n_tsop, head = ev
        after = "" if last_send is None else "  (+%.2f s nach Senden)" % (t - last_send)
        print("%7.2f s  TSMP %4d Flanken %-11s TSOP %3d Pulse%s" % (
            t, n_tsmp, "(%s kHz)" % khz if khz else "", n_tsop, after))
        if n_tsop:
            print("            TSOP: %s%s" % (" ".join(map(str, head)), " ..." if n_tsop > len(head) else ""))
    if not any(ev[0] == "rx" for ev in evs):
        print("  (nichts empfangen)")


if __name__ == "__main__":
    main()
