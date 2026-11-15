import json, sys
from wsearch import *
d = json.load(open(sys.argv[1])); s = d["state"]
sc, (owner, traces, jumps, un, length, legs, bodies, pinnet, order) = score(s)
print("score", sc, "unrouted", un, "jumps", jumps, "len", length, "pins", s["pins"], "rx", s["rxdir"], "led", LEDC[s["led"]][0])
for r in range(9):
    row = ""
    for c in range(20):
        cell = (c, r)
        if cell not in CELLS: row += "  .   "; continue
        if cell in HDR: row += " hdr  "; continue
        if cell in legs: p = legs[cell]; t = p[0][:4] + p[1]
        elif cell in pinnet and cell not in STRIP: t = [k for k, v in PINCELL.items() if v == cell][0]
        elif cell in STRIP: t = STRIP[cell].lower()
        elif cell in owner: t = owner[cell].lower()
        elif cell in bodies: t = "#" + bodies[cell]
        else: t = "o"
        row += "%-6s" % t[:6]
    print(r, row)
