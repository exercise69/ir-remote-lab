# Lötplan IR-Modul: Daten, Prüfung, SVG-Erzeugung
import sys

W, H = 17, 13  # Löcher

def hline(y, x0, x1): return [(x, y) for x in range(x0, x1 + 1)]
def vline(x, y0, y1): return [(x, y) for y in range(y0, y1 + 1)]

# Leiterbahnen auf der Lötseite: Liste von Pfaden (benachbarte Löcher)
TRACES = {
    "VSF": [hline(0, 1, 9), vline(1, 0, 1), vline(6, 0, 2), hline(2, 4, 6)],
    "GND": [vline(2, 1, 12), hline(3, 2, 7), vline(7, 1, 3), hline(12, 2, 16),
            vline(6, 10, 12), vline(15, 9, 12), vline(5, 2, 3)],
    "RX":  [vline(3, 1, 2), vline(3, 4, 11)],
    "3V":  [vline(4, 6, 11)],
    "TX":  [vline(8, 1, 4), hline(4, 5, 9), vline(5, 4, 11)],
    "5V":  [vline(7, 10, 11), hline(10, 7, 9)],
    "A3":  [hline(11, 8, 10)],
    "AN":  [vline(10, 1, 2)],
    "MID": [hline(6, 9, 10)],
    "COL": [vline(11, 1, 8), hline(8, 11, 13), vline(13, 8, 9)],
    "BASE": [vline(14, 8, 11), hline(8, 14, 16)],
}
# GND col 5 rows 2..3 is C1's minus? no: C1 sits (5,2)=VSF,(5,3)=GND -> fix below
TRACES["GND"].remove(vline(5, 2, 3))

# Bauteile: name -> (typ, {pin: (hole, net)}, label, value)
PARTS = [
    ("U2", "rx",  {"VS": ((1, 1), "VSF"), "GND": ((2, 1), "GND"), "OUT": ((3, 1), "RX")}, "TSOP34836"),
    ("U1", "rx",  {"VS": ((6, 1), "VSF"), "GND": ((7, 1), "GND"), "OUT": ((8, 1), "TX")}, "TSMP98000"),
    ("D1", "led", {"A": ((10, 1), "AN"), "K": ((11, 1), "COL")}, "TSAL6200"),
    ("C1", "cap", {"1": ((5, 2), "VSF"), "2": ((5, 3), "GND")}, "100 nF"),
    ("R1", "res", {"1": ((4, 2), "VSF"), "2": ((4, 6), "3V")}, "100 Ω"),
    ("R2", "res", {"1": ((9, 0), "VSF"), "2": ((9, 4), "TX")}, "4,7 kΩ"),
    ("R3b", "res", {"1": ((10, 2), "AN"), "2": ((10, 6), "MID")}, "10 Ω"),
    ("R3a", "res", {"1": ((9, 6), "MID"), "2": ((9, 10), "5V")}, "20 Ω"),
    ("C2", "elko", {"-": ((6, 10), "GND"), "+": ((7, 10), "5V")}, "100 µF"),
    ("R4", "res", {"1": ((10, 11), "A3"), "2": ((14, 11), "BASE")}, "220 Ω"),
    ("R5", "res", {"1": ((16, 8), "BASE"), "2": ((16, 12), "GND")}, "10 kΩ"),
    ("Q1", "tr",  {"C": ((13, 9), "COL"), "B": ((14, 9), "BASE"), "E": ((15, 9), "GND")}, "2N2222A"),
    ("J1", "hdr", {"RX": ((3, 11), "RX"), "3V": ((4, 11), "3V"), "TX": ((5, 11), "TX"),
                   "GND": ((6, 11), "GND"), "5V": ((7, 11), "5V"), "A3": ((8, 11), "A3")}, "Stiftleiste"),
]
JUMPERS = [("RX", (3, 2), (3, 4))]   # Drahtbrücke auf der Bauteilseite

# Soll-Netzliste aus dem Schaltplan
EXPECT = {
    "VSF": {"U2.VS", "U1.VS", "C1.1", "R1.1", "R2.1"},
    "GND": {"U2.GND", "U1.GND", "C1.2", "C2.-", "R5.2", "Q1.E", "J1.GND"},
    "RX": {"U2.OUT", "J1.RX"},
    "TX": {"U1.OUT", "R2.2", "J1.TX"},
    "3V": {"R1.2", "J1.3V"},
    "5V": {"C2.+", "R3a.2", "J1.5V"},
    "A3": {"R4.1", "J1.A3"},
    "AN": {"D1.A", "R3b.1"},
    "MID": {"R3b.2", "R3a.1"},
    "COL": {"D1.K", "Q1.C"},
    "BASE": {"Q1.B", "R4.2", "R5.1"},
}


def check():
    owner = {}
    err = []
    def claim(h, net, what):
        if not (0 <= h[0] < W and 0 <= h[1] < H):
            err.append("%s ausserhalb: %s" % (what, h))
        if owner.get(h, net) != net:
            err.append("Loch %s: %s und %s" % (h, owner[h], net))
        owner[h] = net
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a:
            a = parent[a]
        return a
    def union(a, b): parent[find(a)] = find(b)
    legs = set()
    for name, typ, pins, val in PARTS:
        for p, (h, net) in pins.items():
            if h in legs:
                err.append("zwei Beine in %s" % (h,))
            legs.add(h)
            claim(h, net, name)
    for net, paths in TRACES.items():
        for path in paths:
            for i, h in enumerate(path):
                claim(h, net, "Bahn " + net)
                if i:
                    union(path[i - 1], h)
    for net, a, b in JUMPERS:
        claim(a, net, "Brücke"); claim(b, net, "Brücke"); union(a, b)
    # Prüfen: jedes Netz verbindet genau seine Pins
    groups = {}
    for name, typ, pins, val in PARTS:
        for p, (h, net) in pins.items():
            groups.setdefault(find(h), set()).add("%s.%s" % (name, p))
    got = sorted(map(frozenset, groups.values()), key=sorted)
    want = sorted(map(frozenset, EXPECT.values()), key=sorted)
    if got != want:
        for g in got:
            if g not in want:
                err.append("Ist-Netz falsch: %s" % sorted(g))
    # Traces nur zwischen Nachbarn
    for net, paths in TRACES.items():
        for path in paths:
            for a, b in zip(path, path[1:]):
                if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
                    err.append("Sprung in %s" % net)
    return err, owner

if __name__ == "__main__":
    err, owner = check()
    print("\n".join(err) or "Netzliste stimmt, keine Kurzschlüsse")
