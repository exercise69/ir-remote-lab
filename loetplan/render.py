from loetplan import *
P = 36
ML, MT, MR, MB = 40, 110, 90, 64

def xy(h, mirror=False):
    x, y = h
    if mirror: x = W - 1 - x
    return ML + x * P, MT + y * P

def size():
    return ML + (W - 1) * P + MR, MT + (H - 1) * P + MB

def board(out, mirror):
    x0, y0 = xy((0, 0)); x1, y1 = xy((W - 1, H - 1))
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="6" class="pcb"/>' % (x0 - P/2, y0 - P/2, x1 - x0 + P, y1 - y0 + P))
    for x in range(W):
        for y in range(H):
            cx, cy = xy((x, y))
            out.append('<circle cx="%d" cy="%d" r="3.2" class="hole"/>' % (cx, cy))

def traces(out, mirror, cls):
    for net, paths in TRACES.items():
        for path in paths:
            pts = " ".join("%d,%d" % xy(h, mirror) for h in path)
            out.append('<polyline points="%s" class="%s"/>' % (pts, cls))

def lbl(out, x, y, text, anchor="start", cls="lb"):
    out.append('<text x="%.1f" y="%.1f" text-anchor="%s" class="%s">%s</text>' % (x, y, anchor, cls, text))

def hu(xh, yh, mirror=False):  # hole units -> px (floats)
    if mirror: xh = W - 1 - xh
    return ML + xh * P, MT + yh * P

LABELS = {  # name: (x, y, anchor) in hole units, component side
    "R1": (3.6, 5.45, "end"), "R2": (8.62, 2.7, "end"), "R3b": (10.4, 4.15, "start"),
    "R3a": (8.6, 8.15, "end"), "R4": (12, 10.62, "middle"), "R5": (16.45, 10.15, "start"),
    "C1": (5, 4.72, "middle"), "C2": (6.5, 9.15, "middle"),
}

def top():
    w, h = size(); o = []
    board(o, False)
    traces(o, False, "tru")
    for net, a, b in JUMPERS:
        (ax, ay), (bx, by) = xy(a), xy(b)
        o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="jmp"/>' % (ax, ay, bx, by))
        for cx, cy in ((ax, ay), (bx, by)):
            o.append('<circle cx="%d" cy="%d" r="4.5" class="jmpd"/>' % (cx, cy))
        lbl(o, ax - 8, (ay + by) / 2 + 4, "Brücke", "end", "lbs")
    for name, typ, pins, val in PARTS:
        hs = [h for h, n in pins.values()]
        if typ == "res":
            (a, b) = hs
            (ax, ay), (bx, by) = xy(a), xy(b)
            span = abs(a[0] - b[0]) + abs(a[1] - b[1])
            o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="leg"/>' % (ax, ay, bx, by))
            if span >= 3:
                cx, cy = (ax + bx) / 2, (ay + by) / 2
                L = span * P - 34
                if a[0] == b[0]:
                    o.append('<rect x="%.1f" y="%.1f" width="16" height="%.1f" rx="5" class="body"/>' % (cx - 8, cy - L / 2, L))
                else:
                    o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="16" rx="5" class="body"/>' % (cx - L / 2, cy - 8, L))
            else:
                o.append('<circle cx="%d" cy="%d" r="10" class="body"/>' % (ax, ay))
            for cx, cy in ((ax, ay), (bx, by)):
                o.append('<circle cx="%d" cy="%d" r="4" class="legd"/>' % (cx, cy))
            x, y, an = LABELS[name]
            px, py = hu(x, y)
            lbl(o, px, py - 7, name, an, "lbn")
            lbl(o, px, py + 8, val, an, "lbv")
            if span < 3:
                lbl(o, px, py + 22, "stehend", an, "lbs")
        elif typ == "cap":
            (ax, ay), (bx, by) = xy(hs[0]), xy(hs[1])
            o.append('<rect x="%d" y="%d" width="18" height="%d" rx="8" class="body"/>' % (ax - 9, ay - 8, by - ay + 16))
            x, y, an = LABELS[name]; px, py = hu(x, y)
            lbl(o, px, py - 7, name, an, "lbn"); lbl(o, px, py + 8, val, an, "lbv")
        elif typ == "elko":
            neg, pos = pins["-"][0], pins["+"][0]
            (nx, ny), (px_, py_) = xy(neg), xy(pos)
            cx, cy = (nx + px_) / 2, ny
            o.append('<circle cx="%.1f" cy="%.1f" r="21" class="body"/>' % (cx, cy))
            o.append('<path d="M %.1f %.1f A 21 21 0 0 0 %.1f %.1f Z" class="stripe"/>' % (cx - 9, cy - 19, cx - 9, cy + 19))
            for q in (neg, pos):
                o.append('<circle cx="%d" cy="%d" r="4" class="legd"/>' % xy(q))
            lbl(o, px_ + 9, py_ - 9, "+", "middle", "lbn")
            x, y, an = LABELS[name]; px, py = hu(x, y)
            lbl(o, px, py - 20, name + " " + val, an, "lbn")
        elif typ == "rx":
            (ax, ay) = xy(hs[0]); (bx, by) = xy(hs[2])
            o.append('<rect x="%d" y="%d" width="%d" height="40" rx="5" class="body"/>' % (ax - 16, ay - 26, bx - ax + 32))
            o.append('<path d="M %d %d A 13 13 0 0 1 %d %d" class="body"/>' % ((ax + bx) / 2 - 13, ay - 26, (ax + bx) / 2 + 13, ay - 26))
            lbl(o, (ax + bx) / 2, ay - 9, val, "middle", "lbn")
            for p, (hh, n) in pins.items():
                cx, cy = xy(hh)
                o.append('<circle cx="%d" cy="%d" r="4" class="legd"/>' % (cx, cy))
                lbl(o, cx, cy + 25, p, "middle", "lbp")
        elif typ == "led":
            (ax, ay), (kx, ky) = xy(pins["A"][0]), xy(pins["K"][0])
            top_y = MT - P / 2 - 6
            for x in (ax, kx):
                o.append('<polyline points="%d,%d %d,%d" class="leg"/>' % (x, ay, x, top_y))
                o.append('<circle cx="%d" cy="%d" r="4" class="legd"/>' % (x, ay))
            cx = (ax + kx) / 2
            o.append('<path d="M %.1f %.1f L %.1f %.1f A 17 17 0 0 1 %.1f %.1f L %.1f %.1f Z" class="body"/>' % (cx - 17, top_y, cx - 17, top_y - 42, cx + 17, top_y - 42, cx + 17, top_y))
            o.append('<rect x="%.1f" y="%.1f" width="42" height="7" rx="2" class="body"/>' % (cx - 21, top_y - 7))
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="flat"/>' % (cx + 21, top_y - 9, cx + 21, top_y + 1))
            lbl(o, ax, ay + 24, "A+", "middle", "lbp"); lbl(o, kx, ky + 24, "K−", "middle", "lbp")
            lbl(o, cx + 30, top_y - 34, "D1 TSAL6200", "start", "lbn")
            lbl(o, cx + 30, top_y - 18, "liegend, zeigt nach vorn", "start", "lbs")
            lbl(o, cx + 30, top_y - 4, "flache Kante = Kathode", "start", "lbs")
        elif typ == "tr":
            (cx_, cy_) = xy(pins["C"][0]); (ex, ey) = xy(pins["E"][0])
            mx = (cx_ + ex) / 2
            o.append('<path d="M %d %d L %d %d A 52 40 0 0 1 %d %d Z" class="body"/>' % (cx_ - 16, cy_ - 13, ex + 16, ey - 13, cx_ - 16, cy_ - 13))
            for p, (hh, n) in pins.items():
                x, y = xy(hh)
                o.append('<circle cx="%d" cy="%d" r="4" class="legd"/>' % (x, y))
                lbl(o, x, y + 18, p, "middle", "lbp")
            lbl(o, mx, cy_ - 20, "Q1 2N2222A", "middle", "lbn")
        elif typ == "hdr":
            (ax, ay) = xy(hs[0]); (bx, by) = xy(hs[-1])
            o.append('<rect x="%d" y="%d" width="%d" height="22" rx="2" class="hdr"/>' % (ax - 15, ay - 11, bx - ax + 30))
            for p, (hh, n) in pins.items():
                x, y = xy(hh)
                o.append('<rect x="%d" y="%d" width="9" height="9" class="hdrp"/>' % (x - 4.5, y - 4.5))
                lbl(o, x, MT + (H - 1) * P + P / 2 + 20, p, "middle", "lbh")
            lbl(o, (ax + bx) / 2, MT + (H - 1) * P + P / 2 + 40, "J1 Stiftleiste → Dupont-Kabel zum QT Py", "middle", "lbs")
    return w, h, o

def bottom():
    w, h = size(); o = []
    board(o, True)
    traces(o, True, "trs")
    for name, typ, pins, val in PARTS:
        for p, (hh, n) in pins.items():
            x, y = xy(hh, True)
            o.append('<circle cx="%d" cy="%d" r="6.5" class="pad"/>' % (x, y))
    for net, a, b in JUMPERS:
        for q in (a, b):
            x, y = xy(q, True)
            o.append('<circle cx="%d" cy="%d" r="6.5" class="pad"/>' % (x, y))
    # Beschriftung der Teile an ihrem ersten Bein, gespiegelt platziert
    tags = {"U2": (2, 1, "TSOP", -16), "U1": (7, 1, "TSMP", -16), "D1": (10.5, 1, "LED", -16),
            "Q1": (14, 9, "Q1", -14), "J1": (5.5, 11, "", 0)}
    for name, (x, y, t, dy) in tags.items():
        if t:
            px, py = hu(x, y, True)
            lbl(o, px, py + dy, t, "middle", "lbs")
    for p, (hh, n) in PARTS[-1][2].items():
        x, y = xy(hh, True)
        lbl(o, x, MT + (H - 1) * P + P / 2 + 20, p, "middle", "lbh")
    lbl(o, w / 2, MT + (H - 1) * P + P / 2 + 40, "von unten gesehen: links und rechts vertauscht", "middle", "lbs")
    for net, a, b in JUMPERS:
        x, y = xy(a, True); x2, y2 = xy(b, True)
        o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="jmpb"/>' % (x, y + 7, x2, y2 - 7))
    return w, h, o

def svg(fn, title, y0=0):
    w, h, o = fn()
    return ('<svg class="pcbv" viewBox="0 %d %d %d" role="img"><title>%s</title>\n' % (y0, w, h - y0, title)
            + "\n".join(o) + "\n</svg>")

if __name__ == "__main__":
    open("top.svg.html", "w").write(svg(top, "Lötplan Bauteilseite von oben: links TSOP34836 und TSMP98000, rechts IR-LED liegend nach vorn, darunter R3b, R3a, Q1, R4, R5; unten Stiftleiste RX 3V TX GND 5V A3"))
    open("bot.svg.html", "w").write(svg(bottom, "Lötplan Lötseite, von unten gesehen, links und rechts vertauscht", 70))
