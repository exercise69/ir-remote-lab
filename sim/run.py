"""Simulator: laesst code.py auf dem Mac laufen, ohne Board.

    .venv/bin/python sim/run.py            -> http://localhost:8080/
    .venv/bin/python sim/run.py --remote 0 -> ohne simulierte Fernbedienung

Die Module board, pulseio, keypad usw. in diesem Ordner sind Attrappen. Gesendete
Pulse kommen (leicht verzerrt) bei den Empfaengern an, wie auf dem Breadboard.
Eine simulierte Fernbedienung drueckt regelmaessig eine Taste (RC5-artig, mit
Toggle-Bit), damit die Webseite etwas zu zeigen hat. Kommt nicht aufs Board.
"""

import argparse
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8080)
ap.add_argument("--remote", type=float, default=8.0, help="Sekunden zwischen Tastendruecken, 0 = aus")
ap.add_argument("--no-echo", action="store_true", help="IR-LED 'kaputt': Sendungen kommen nicht an")
ap.add_argument("--web", default=os.path.join(PROJECT, "web"), help="Ordner mit index.html")
args = ap.parse_args()

sys.path.insert(0, HERE)
sys.path.insert(1, PROJECT)
os.environ["IRLAB_WEB_PORT"] = str(args.port)
os.environ["IRLAB_WEB_ROOT"] = os.path.abspath(args.web)
os.environ["IRLAB_CODES_BACKUP"] = os.path.join(PROJECT, "captures", "codes.json")  # gelernte Codes

import pulseio  # noqa: E402  (Attrappe aus sim/)

pulseio.ECHO = not args.no_echo


def remote_loop(period):
    # zwei "Tasten" im Wechsel, jede dreimal, bei jedem Druck kippt das Toggle-Bit
    presses = 0
    while True:
        time.sleep(period)
        cmd = (presses // 3) % 2 + 12
        pulseio.inject(pulseio.rc5_like(toggle=presses % 2, address=5, command=cmd), khz=36.0)
        presses += 1


if args.remote > 0:
    threading.Thread(target=remote_loop, args=(args.remote,), daemon=True).start()

print("Simulator: http://localhost:%d/" % args.port)
code = open(os.path.join(PROJECT, "code.py"), encoding="utf-8").read()
exec(compile(code, "code.py", "exec"), {"__name__": "__main__"})
