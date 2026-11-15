"""Attrappe fuer pulseio: PulseIn/PulseOut ohne Hardware.

Pins sind Strings ("TX", "RX", "A3"). Was PulseOut sendet, landet bei den PulseIn
auf TX (TSMP: Traegerpulse) und RX (TSOP: Huellkurve), mit kleinen Verzerrungen.
"""

import random
import threading

ECHO = True
_lock = threading.Lock()
_inputs = {}


class PulseIn:
    def __init__(self, pin, maxlen=2, idle_state=False):
        self.pin, self.maxlen = pin, maxlen
        self._d = []
        self._paused = False
        _inputs[pin] = self

    def _feed(self, data):
        with _lock:
            if not self._paused:
                room = self.maxlen - len(self._d)
                self._d.extend(data[:max(0, room)])

    def __len__(self):
        with _lock:
            return len(self._d)

    def __getitem__(self, i):
        with _lock:
            return self._d[i]

    def pause(self):
        self._paused = True

    def resume(self, trigger_duration=0):
        self._paused = False

    def clear(self):
        with _lock:
            self._d = []

    def deinit(self):
        _inputs.pop(self.pin, None)


def tsmp_from(pulses, khz):
    """TSMP98000: pro Traegerperiode ein kurzer LOW-Puls, gerundet auf ganze us."""
    period = 1000.0 / khz
    starts = []
    t = 0.0
    for i, d in enumerate(pulses):
        if i % 2 == 0:
            n = max(1, int(d / period))
            starts.extend(t + k * period for k in range(n))
        t += d
    out = []
    for i, s in enumerate(starts):
        out.append(9)
        if i + 1 < len(starts):
            out.append(round(starts[i + 1]) - round(s) - 9)
    return out


def tsop_from(pulses):
    """TSOP: 'an' etwas laenger, 'aus' etwas kuerzer, plus Rauschen."""
    out = []
    for i, d in enumerate(pulses):
        shift = 60 if i % 2 == 0 else -60
        out.append(max(1, int(d + shift + random.randint(-25, 25))))
    return out


def inject(pulses, khz):
    if "TX" in _inputs:
        _inputs["TX"]._feed(tsmp_from(pulses, khz))
    if "RX" in _inputs:
        _inputs["RX"]._feed(tsop_from(pulses))


def rc5_like(toggle, address, command):
    """Manchester-codiertes Telegramm aehnlich RC5 (14 Bit, 889 us je Halbbit)."""
    bits = [1, 1, toggle] + [(address >> i) & 1 for i in range(4, -1, -1)] \
        + [(command >> i) & 1 for i in range(5, -1, -1)]
    half = []
    for b in bits:
        half += [0, 1] if b else [1, 0]   # 1 = aus->an, 0 = an->aus
    # in Pulsdauern umrechnen, beginnend beim ersten "an"
    while half and half[0] == 0:
        half.pop(0)
    out = []
    level, count = half[0], 0
    for h in half:
        if h == level:
            count += 1
        else:
            out.append(count * 889)
            level, count = h, 1
    if level == 1:
        out.append(count * 889)
    return out


class PulseOut:
    def __init__(self, pin, *, frequency=38000, duty_cycle=1 << 15):
        self.pin, self.frequency = pin, frequency

    def send(self, data):
        pulses = list(data)
        if ECHO:
            threading.Timer(0.02, inject, args=(pulses, self.frequency / 1000)).start()

    def deinit(self):
        pass
