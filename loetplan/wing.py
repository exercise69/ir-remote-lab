# FeatherWing Proto: Raster, feste Netze, Router, ASCII-Ausgabe
from collections import deque
import itertools, sys

COLS, ROWS = 20, 9
TOP_PINS = ["BAT", "EN", "USB", "D13", "D12", "D11", "D10", "D9", "D6", "D5", "SCL", "SDA"]   # c=6..17, r=1 (r=0 Stiftleiste)
BOT_PINS = ["RST", "3V3", "AREF", "GND", "A0", "A1", "A2", "A3", "A4", "A5", "SCK", "MO", "MI", "RX", "TX", "DB"]  # c=2..17, r=7 (r=8 Stiftleiste)
PIN_NET = {"USB": "5V", "GND": "GND", "3V3": "3V"}

def board():
    """cell -> ('free'|'fixed'|'pin', net or name)"""
    cells = {}
    for c in range(COLS):
        for r in range(2, 7):
            cells[(c, r)] = ("free", None)
    for r in range(0, 7):
        cells[(4, r)] = ("fixed", "3V")
        cells[(5, r)] = ("fixed", "GND")
    for c in (2, 3):
        for r in (0, 1):
            cells[(c, r)] = ("free", None)
    for i, n in enumerate(TOP_PINS):
        cells[(6 + i, 1)] = ("pin", n)
    for i, n in enumerate(BOT_PINS):
        cells[(2 + i, 7)] = ("pin", n)
    return cells


def route(cells, parts, nets_order, bodies=(), jumpers=(), pinmap=None, verbose=False):
    """parts: list (name, {pin: (cell, net)}); pinmap: board pin name -> net it must carry.
    Returns dict cell->net for traces and list of failures."""
    pinmap = pinmap or {}
    owner = {}
    legs = {}
    for name, pins in parts:
        for p, (cell, net) in pins.items():
            assert cell in cells, (name, p, cell)
            assert cell not in legs, ("doppelt", cell, legs.get(cell), name)
            legs[cell] = (name, p)
            owner[cell] = net
    for cell, (kind, val) in cells.items():
        if kind == "fixed":
            if cell in owner and owner[cell] != val:
                raise ValueError("Bein %s im Streifen %s" % (owner[cell], val))
            owner[cell] = val
        elif kind == "pin":
            net = pinmap.get(val, PIN_NET.get(val, "PIN_" + val))
            if cell in owner and owner[cell] != net:
                raise ValueError("Bein auf Pin %s (%s) mit Netz %s" % (val, net, owner[cell]))
            owner[cell] = net
    for net, a, b in jumpers:
        for x in (a, b):
            if owner.get(x, net) != net:
                raise ValueError("Bruecke %s auf %s" % (x, owner[x]))
            owner[x] = net
    body_cells = set(bodies)
    for b in body_cells:
        if b in legs:
            raise ValueError("Bein %s unter Koerper" % (legs[b],))
    fails = []
    edges = []  # trace segments
    def nb(c):
        x, y = c
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + d[0], y + d[1])
            if n in cells:
                yield n
    # Strips count as already connected internally
    fixed_groups = {}
    for cell, (kind, val) in cells.items():
        if kind == "fixed":
            fixed_groups.setdefault(val, set()).add(cell)
    # pins GND(5,7) is connected to GND strip on the board; 3V3 (3,7) to 3V strip
    fixed_groups["GND"].add((5, 7)); fixed_groups["3V"].add((3, 7))
    for net in nets_order:
        terms = [c for c, n in owner.items() if n == net]
        tree = set(fixed_groups.get(net, set()))
        jl = [(a, b) for n, a, b in jumpers if n == net]
        pending = [t for t in terms if t not in tree]
        if not tree:
            tree = {pending.pop(0)}
        def expand(tree):
            changed = True
            while changed:
                changed = False
                for a, b in jl:
                    if (a in tree) != (b in tree):
                        tree |= {a, b}; changed = True
        expand(tree)
        pending = [t for t in pending if t not in tree]
        while pending:
            # BFS from tree to any pending terminal through free cells
            prev = {c: None for c in tree}
            q = deque(tree)
            found = None
            while q:
                c = q.popleft()
                if c in pending and c not in tree:
                    found = c; break
                for n in nb(c):
                    if n in prev:
                        continue
                    if owner.get(n) not in (None, net):
                        continue
                    # don't walk through pin/fixed cells of own net except terminals/tree
                    k = cells[n][0]
                    if k in ("pin", "fixed") and n not in pending:
                        continue
                    if n in legs and n not in pending and owner.get(n) == net and n not in tree:
                        pass
                    prev[n] = c
                    q.append(n)
            if not found:
                fails.append((net, pending))
                break
            c = found
            path = []
            while c is not None and c not in tree:
                path.append(c); c = prev[c]
            last = c
            for p in path:
                owner[p] = net
            seq = [last] + path[::-1]
            for a, b in zip(seq, seq[1:]):
                edges.append((net, a, b))
            tree |= set(path)
            expand(tree)
            pending = [t for t in pending if t not in tree]
    return owner, edges, fails, legs


SYM = {}
def show(cells, owner, legs, bodies=()):
    out = []
    for r in range(ROWS):
        row = ""
        for c in range(COLS):
            if (c, r) not in cells:
                row += "  .  " if r not in (0, 8) or not (6 <= c <= 17 or (r == 8 and 2 <= c <= 17)) else " hdr "
                continue
            kind, val = cells[(c, r)]
            n = owner.get((c, r))
            if (c, r) in legs:
                s = legs[(c, r)][0][:3] + "." + legs[(c, r)][1][:1]
            elif kind == "pin":
                s = val
            elif n:
                s = n.lower()
            elif (c, r) in bodies:
                s = "##"
            else:
                s = "o"
            row += "%-5s" % s[:5]
        out.append("%d  %s" % (r, row))
    out.insert(0, "   " + "".join("%-5d" % c for c in range(COLS)))
    return "\n".join(out)
