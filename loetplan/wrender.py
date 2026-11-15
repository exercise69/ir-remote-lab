# Zeichnet den Lötplan für die FeatherWing Proto aus wing_layout.json (Ober- und Unterseite)
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
L = json.load(open(os.path.join(HERE, "wing_layout.json")))
from wsearch import CELLS, HDR, PINCELL, TOP_PINS, BOT_PINS

P = 34
ML, MT, MR, MB = 30, 70, 30, 70
COLS, ROWS = 20, 9
USED = {"USB": "5V", "GND": "GND"}
for k, v in L["pins"].items():
    USED[v] = {"OUTM": "TSMP", "OUTP": "TSOP", "DRV": "IR-LED"}[k]

def xy(c, r, m=False):
    if m: c = COLS - 1 - c
    return ML + (c + 0.5) * P, MT + (r + 0.5) * P

def size():
    return ML + COLS * P + MR, MT + ROWS * P + MB

def lbl(o, x, y, t, an="start", cls="lbs"):
    o.append('<text x="%.1f" y="%.1f" text-anchor="%s" class="%s">%s</text>' % (x, y, an, cls, t))

legs = {(x, y): (p, pn, n) for x, y, p, pn, n in L["legs"]}

def base(o, m):
    w, h = size()
    o.append('<rect x="%d" y="%d" width="%d" height="%d" rx="8" class="wingpcb"/>' % (ML, MT, COLS * P, ROWS * P))
    for (mx, my) in ((0.5, 0.5), (0.5, 7.5), (18.5, 0.5), (18.5, 7.5)):
        o.append('<circle cx="%.1f" cy="%.1f" r="13" class="mhole"/>' % xy(mx, my, m))
    # Streifen
    for c, name in ((4, "3V"), (5, "GND")):
        x0, y0 = xy(c, 0, m); x1, y1 = xy(c, 6, m)
        o.append('<rect x="%.1f" y="%.1f" width="16" height="%.1f" rx="8" class="strip"/>' % (x0 - 8, y0 - 8, y1 - y0 + 16))
        x, y = xy(c, 0, m)
        lbl(o, x, MT - 10, name, "middle", "lbu")
    # Löcher
    for (c, r) in CELLS:
        x, y = xy(c, r, m)
        o.append('<circle cx="%.1f" cy="%.1f" r="3.4" class="hole"/>' % (x, y))
    # Stiftleisten
    for c in range(6, 18):
        x, y = xy(c, 0, m); o.append('<rect x="%.1f" y="%.1f" width="10" height="10" class="hdrp"/>' % (x - 5, y - 5))
    for c in range(2, 18):
        x, y = xy(c, 8, m); o.append('<rect x="%.1f" y="%.1f" width="10" height="10" class="hdrp"/>' % (x - 5, y - 5))
    # Pin-Namen
    for i, n in enumerate(TOP_PINS):
        x, y = xy(6 + i, 0, m)
        lbl(o, x, MT - 10, n, "middle", "lbu" if n in USED else "lbq")
    for i, n in enumerate(BOT_PINS):
        x, y = xy(2 + i, 8, m)
        lbl(o, x, MT + ROWS * P + 18, n if n != "3V3" else "3V", "middle", "lbu" if n in USED else "lbq")
    for n, role in USED.items():
        if n in ("USB", "GND"): continue
        c, r = PINCELL[n]; x, y = xy(c, 8 if r == 7 else 0, m)
        lbl(o, x, MT + ROWS * P + 34 if r == 7 else MT - 26, role, "middle", "lbv")
    x, y = xy(8, 0, m); lbl(o, x, MT - 26, "5V", "middle", "lbv")

def traces(o, m, cls):
    for n, a, b in L["traces"]:
        (x1, y1), (x2, y2) = xy(*a, m), xy(*b, m)
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="%s"/>' % (x1, y1, x2, y2, cls))
    # Verbindung Bein ↔ Pin-Loch direkt daneben (Lötbrücke) ist schon als Bahn enthalten, falls vorhanden

def part_pins(name):
    return {pn: (x, y) for (x, y), (p, pn, n) in legs.items() if p == name}

VAL = {"R1": "100 Ω", "R2": "4,7 kΩ", "R3": "33 Ω", "R4": "220 Ω", "R5": "10 kΩ", "C1": "100 nF", "C2": "100 µF"}

def top():
    o = []; base(o, False); traces(o, False, "tru")
    for n, a, b in L["jumps"]:
        (x1, y1), (x2, y2) = xy(*a), xy(*b)
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="jmp"/>' % (x1, y1, x2, y2))
        for x, y in ((x1, y1), (x2, y2)): o.append('<circle cx="%.1f" cy="%.1f" r="4.5" class="jmpd"/>' % (x, y))
    for name in ("R1", "R2", "R3", "R4", "R5"):
        pp = part_pins(name); a, b = xy(*pp["1"]), xy(*pp["2"])
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="leg"/>' % (a + b))
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2; Lb = 4 * P - 34
        if abs(a[0] - b[0]) < 1:
            o.append('<rect x="%.1f" y="%.1f" width="15" height="%.1f" rx="5" class="body"/>' % (cx - 7.5, cy - Lb / 2, Lb))
            lbl(o, cx - 12, cy - 2, name, "end", "lbn"); lbl(o, cx - 12, cy + 12, VAL[name], "end", "lbv")
        else:
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="15" rx="5" class="body"/>' % (cx - Lb / 2, cy - 7.5, Lb))
            lbl(o, cx, cy + 4, name + " " + VAL[name], "middle", "lbn2")
        for p in (a, b): o.append('<circle cx="%.1f" cy="%.1f" r="4" class="legd"/>' % p)
    # C1
    pp = part_pins("C1"); a, b = xy(*pp["1"]), xy(*pp["2"])
    x0, x1 = min(a[0], b[0]), max(a[0], b[0]); y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="8" class="body"/>' % (x0 - 9, y0 - 8, x1 - x0 + 18, y1 - y0 + 16))
    for p in (a, b): o.append('<circle cx="%.1f" cy="%.1f" r="4" class="legd"/>' % p)
    lbl(o, (a[0] + b[0]) / 2, y0 - 12, "C1", "middle", "lbn")
    # C2
    pp = part_pins("C2"); a, b = xy(*pp["1"]), xy(*pp["2"])
    cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    o.append('<circle cx="%.1f" cy="%.1f" r="20" class="body"/>' % (cx, cy))
    # Minus-Streifen auf der Seite von Bein 2 (GND)
    dx, dy = b[0] - cx, b[1] - cy
    if abs(dx) > abs(dy):
        sx = cx + (8 if dx > 0 else -8)
        o.append('<path d="M %.1f %.1f A 20 20 0 0 %d %.1f %.1f Z" class="stripe"/>' % (sx, cy - 18.3, 1 if dx > 0 else 0, sx, cy + 18.3))
    else:
        sy = cy + (8 if dy > 0 else -8)
        o.append('<path d="M %.1f %.1f A 20 20 0 0 %d %.1f %.1f Z" class="stripe"/>' % (cx - 18.3, sy, 0 if dy > 0 else 1, cx + 18.3, sy))
    for p in (a, b): o.append('<circle cx="%.1f" cy="%.1f" r="4" class="legd"/>' % p)
    lbl(o, a[0] + (a[0] - cx) * 0.2, a[1] - 24, "C2 +", "middle", "lbn")
    # Empfänger (Linse nach unten)
    for name, title in (("TSOP", "TSOP34836"), ("TSMP", "TSMP98000")):
        pp = part_pins(name); xs = [xy(*v)[0] for v in pp.values()]; y = xy(*pp["O"])[1]
        o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="38" rx="5" class="body"/>' % (min(xs) - 15, y - 12, max(xs) - min(xs) + 30))
        cx = (min(xs) + max(xs)) / 2
        o.append('<path d="M %.1f %.1f A 12 12 0 0 0 %.1f %.1f" class="body"/>' % (cx - 12, y + 26, cx + 12, y + 26))
        lbl(o, cx, y + 21, title, "middle", "lbn")
        for pn, c in pp.items():
            x, yy = xy(*c); o.append('<circle cx="%.1f" cy="%.1f" r="4" class="legd"/>' % (x, yy))
            lbl(o, x, yy - 8, {"O": "OUT", "G": "GND", "V": "VS"}[pn], "middle", "lbp")
    # Q1 (senkrecht)
    pp = part_pins("Q1"); ys = [xy(*v)[1] for v in pp.values()]; x = xy(*pp["B"])[0]
    o.append('<path d="M %.1f %.1f L %.1f %.1f A 40 52 0 0 1 %.1f %.1f Z" class="body"/>' % (x + 10, min(ys) - 14, x + 10, max(ys) + 14, x + 10, min(ys) - 14))
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="flat"/>' % (x + 10, min(ys) - 14, x + 10, max(ys) + 14))
    for pn, c in pp.items():
        xx, yy = xy(*c); o.append('<circle cx="%.1f" cy="%.1f" r="4" class="legd"/>' % (xx, yy))
        lbl(o, xx - 7, yy + 4, pn, "end", "lbp")
    lbl(o, x - 4, min(ys) - 20, "Q1", "middle", "lbn")
    # LED (liegend, zeigt nach unten über die Kante)
    pp = part_pins("D1"); a, k = xy(*pp["A"]), xy(*pp["K"])
    cx = (a[0] + k[0]) / 2; y0 = a[1]; yb = MT + ROWS * P - 6
    for p in (a, k):
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="leg"/>' % (p[0], p[1], p[0], yb - 30))
        o.append('<circle cx="%.1f" cy="%.1f" r="4" class="legd"/>' % p)
    o.append('<rect x="%.1f" y="%.1f" width="40" height="7" rx="2" class="body"/>' % (cx - 20, yb - 34))
    o.append('<path d="M %.1f %.1f L %.1f %.1f A 16 16 0 0 0 %.1f %.1f L %.1f %.1f Z" class="body"/>' % (cx - 16, yb - 27, cx - 16, yb + 8, cx + 16, yb + 8, cx + 16, yb - 27))
    fx = k[0] + (6 if k[0] > a[0] else -6)
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="flat"/>' % (cx + (20 if k[0] > a[0] else -20), yb - 36, cx + (20 if k[0] > a[0] else -20), yb - 25))
    lbl(o, a[0], a[1] - 9, "A+", "middle", "lbp"); lbl(o, k[0], k[1] - 9, "K−", "middle", "lbp")
    lbl(o, cx, yb + 26, "IR-LED", "middle", "lbn")
    return o

def bottom():
    o = []; base(o, True); traces(o, True, "trs")
    for (c, r) in legs:
        x, y = xy(c, r, True); o.append('<circle cx="%.1f" cy="%.1f" r="6.5" class="pad"/>' % (x, y))
    for n, a, b in L["jumps"]:
        for q in (a, b):
            x, y = xy(*q, True); o.append('<circle cx="%.1f" cy="%.1f" r="6.5" class="pad"/>' % (x, y))
        (x1, y1), (x2, y2) = xy(*a, True), xy(*b, True)
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="jmpb"/>' % (x1 + 8 * (1 if x2 > x1 else -1), y1, x2 - 8 * (1 if x2 > x1 else -1), y2))
    return o

def svg(fn, title):
    w, h = size()
    return '<svg class="pcbv wingv" viewBox="0 0 %d %d" role="img"><title>%s</title>\n%s\n</svg>' % (w, h, title, "\n".join(fn()))

if __name__ == "__main__":
    open(os.path.join(HERE, "wing_top.svg.html"), "w").write(svg(top, "FeatherWing Proto von oben: links die Streifen 3V und GND, unten TSOP34836 an A0 und TSMP98000 an A4, rechts Q1 und die IR-LED an TX, oben R3 von USB (5V)"))
    open(os.path.join(HERE, "wing_bot.svg.html"), "w").write(svg(bottom, "FeatherWing Proto von unten, gespiegelt"))
