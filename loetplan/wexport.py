import json
from wsearch import *
d = json.load(open("res_41.json")); s = d["state"]
sc, (owner, traces, jumps, un, length, legs, bodies, pinnet, order) = score(s)
assert un == 0
out = {"pins": dict(zip(["OUTM", "OUTP", "DRV"], s["pins"])),
       "legs": [[c[0], c[1], p, pn, n] for c, (p, pn, n) in legs.items()],
       "traces": [[n, a, b] for n, a, b in traces],
       "jumps": [[n, a, b] for n, a, b in jumps],
       "rxdir": s["rxdir"], "led": LEDC[s["led"]][0]}
json.dump(out, open("wing_layout.json", "w"))
# unabhaengige Pruefung
parent = {}
def f(a):
    while parent.setdefault(a, a) != a: a = parent[a]
    return a
def u(a, b): parent[f(tuple(a))] = f(tuple(b))
for r in range(0, 7): u((4, r), (4, 0)); u((5, r), (5, 0))
u((5, 7), (5, 0)); u((3, 7), (4, 0))
for n, a, b in out["traces"] + out["jumps"]:
    u(a, b)
# Netzbelegung je Loch darf nicht kollidieren
hole = {}
def claim(c, n):
    c = tuple(c)
    if hole.get(c, n) != n: raise SystemExit("Kollision %s %s %s" % (c, hole[c], n))
    hole[c] = n
for x, y, p, pn, n in out["legs"]: claim((x, y), n)
for n, a, b in out["traces"] + out["jumps"]: claim(a, n); claim(b, n)
for r in range(7): claim((4, r), "3V"); claim((5, r), "GND")
pinpos = dict(PINCELL)
fixed = {"USB": "5V", "GND": "GND", "3V3": "3V", out["pins"]["OUTM"]: "OUTM", out["pins"]["OUTP"]: "OUTP", out["pins"]["DRV"]: "DRV"}
for name, c in pinpos.items():
    claim(c, fixed.get(name, "PIN_" + name))
EXPECT = {
 "GND": {"TSOP.G", "TSMP.G", "C1.2", "C2.2", "Q1.E", "R5.2", "strip"},
 "3V": {"R1.1", "strip3"},
 "VSF": {"R1.2", "TSOP.V", "TSMP.V", "C1.1", "R2.2"},
 "OUTM": {"TSMP.O", "R2.1", "pinM"}, "OUTP": {"TSOP.O", "pinP"},
 "5V": {"USB", "R3.1", "C2.1"}, "AN": {"R3.2", "D1.A"}, "COL": {"D1.K", "Q1.C"},
 "BASE": {"Q1.B", "R4.2", "R5.1"}, "DRV": {"R4.1", "pinD"}}
groups = {}
def add(c, label): groups.setdefault(f(tuple(c)), set()).add(label)
for x, y, p, pn, n in out["legs"]:
    lab = "%s.%s" % (p, {"O": "O", "G": "G", "V": "V"}.get(pn, pn))
    add((x, y), lab)
add((5, 0), "strip"); add((4, 0), "strip3"); add(PINCELL["USB"], "USB")
add(PINCELL[out["pins"]["OUTM"]], "pinM"); add(PINCELL[out["pins"]["OUTP"]], "pinP"); add(PINCELL[out["pins"]["DRV"]], "pinD")
got = sorted(sorted(g) for g in groups.values())
want = sorted(sorted(g) for g in EXPECT.values())
print("OK" if got == want else ("FEHLER", got, want))
print(out["pins"], len(out["traces"]), "Bahnen", out["jumps"])
