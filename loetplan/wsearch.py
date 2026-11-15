# Platzierungssuche (Simulated Annealing) fuer das IR-Modul auf der FeatherWing Proto
import heapq, math, random, sys, json
from wing import board, TOP_PINS, BOT_PINS

CELLS = board()
HDR = set()
for c in range(0, 4):
    for r in range(0, 7): HDR.add((c, r))   # links der Streifen: abgeschnitten, gesperrt
for c in range(6, 18): HDR.add((c, 0))
for c in range(2, 18): HDR.add((c, 8))
PINCELL = {}
for i, n in enumerate(TOP_PINS): PINCELL[n] = (6 + i, 1)
for i, n in enumerate(BOT_PINS): PINCELL[n] = (2 + i, 7)
GPIO = ["A0", "A1", "A2", "A3", "A4", "A5", "RX", "TX", "D12", "D11", "D10", "D9", "D6", "D5"]
FIXEDNET = {"USB": "5V", "GND": "GND", "3V3": "3V"}
STRIP = {}
for r in range(0, 7):
    STRIP[(4, r)] = "3V"; STRIP[(5, r)] = "GND"
STRIP[(5, 7)] = "GND"; STRIP[(3, 7)] = "3V"

RES = [("R1", "3V", "VSF"), ("R2", "OUTM", "VSF"), ("R3", "5V", "AN"), ("R4", "DRV", "BASE"), ("R5", "BASE", "GND")]

def rx_cands():
    out = []
    for c in range(6, 18):   # Reihe 6, Linse nach unten: O G V
        out.append(("down", [(c, 6), (c + 1, 6), (c + 2, 6)], [(c, 7), (c + 1, 7), (c + 2, 7)]))
        out.append(("up", [(c, 2), (c + 1, 2), (c + 2, 2)][::-1], [(c, 1), (c + 1, 1), (c + 2, 1)]))
    return [x for x in out if all(p in CELLS and p not in HDR for p in x[1])]
RXC = rx_cands()  # pins listed in order O, G, V

def led_cands():
    out = []
    for c in range(6, 19):
        out.append(("down", [(c, 6), (c + 1, 6)], [(c, 7), (c + 1, 7)]))
        out.append(("up", [(c, 2), (c + 1, 2)], [(c, 1), (c + 1, 1)]))
    for r in range(2, 6):
        out.append(("right", [(19, r), (19, r + 1)], []))
    return [x for x in out if all(p in CELLS for p in x[1])]
LEDC = led_cands()

def line_cands(n, span=None):
    out = []
    for (c, r) in CELLS:
        for d in ((1, 0), (0, 1)):
            if span is None:
                pts = [(c + d[0] * i, r + d[1] * i) for i in range(n)]
            else:
                pts = [(c, r), (c + d[0] * span, r + d[1] * span)]
            if all(p in CELLS and p not in HDR for p in pts):
                out.append(pts)
    return out
Q1C = line_cands(3)
R4C = line_cands(2, 4)
R3C = line_cands(2, 3)
CC = line_cands(2, 1)

def rand_state():
    s = {}
    s["rxdir"] = random.choice(["down", "up"])
    s["tsop"] = random.randrange(len(RXC)); s["tsmp"] = random.randrange(len(RXC))
    s["led"] = random.randrange(len(LEDC)); s["ledflip"] = random.random() < .5
    s["q1"] = random.randrange(len(Q1C)); s["q1flip"] = random.random() < .5
    for name, a, b in RES:
        s[name] = (random.random() < 0.9, random.randrange(len(R4C)), random.randrange(len(R3C)), random.random() < .5)
    s["C1"] = (random.randrange(len(CC)), random.random() < .5)
    s["C2"] = (random.randrange(len(CC)), random.random() < .5)
    s["pins"] = random.sample(GPIO, 3)
    return s

def build(s):
    """-> legs {cell:(part,pin,net)}, bodies set, pinnet {cellofpin:net}, penalty"""
    pen = 0
    legs = {}; bodies = {}
    def leg(cell, part, pin, net):
        nonlocal pen
        if cell in legs: pen += 100; return
        legs[cell] = (part, pin, net)
    def body(cells, part):
        nonlocal pen
        for c in cells:
            if c in bodies: pen += 100
            bodies[c] = part
    outm, outp, drv = s["pins"]
    pinnet = {}
    for name, cell in PINCELL.items():
        pinnet[cell] = FIXEDNET.get(name, "PIN_" + name)
    pinnet[PINCELL[outm]] = "OUTM"; pinnet[PINCELL[outp]] = "OUTP"; pinnet[PINCELL[drv]] = "DRV"
    for part, net_o in (("TSMP", "OUTM"), ("TSOP", "OUTP")):
        if part.lower() not in s: continue
        d, pins, front = RXC[s[part.lower()]]
        if d != s["rxdir"]: pen += 100
        for p, net in zip(pins, (net_o, "GND", "VSF")):
            leg(p, part, "OGV"[pins.index(p)], net)
        body(front, part)
    if "led" in s:
        d, pins, front = LEDC[s["led"]]
        a, k = (pins if not s["ledflip"] else pins[::-1])
        leg(a, "D1", "A", "AN"); leg(k, "D1", "K", "COL")
        body(front, "D1")
        if d != s["rxdir"]: pen += 30
    if "q1" in s:
        q = Q1C[s["q1"]]; q = q if not s["q1flip"] else q[::-1]
        for p, (pn, net) in zip(q, (("E", "GND"), ("B", "BASE"), ("C", "COL"))):
            leg(p, "Q1", pn, net)
    for name, na, nb in RES:
        if name not in s: continue
        long_, i4, i3, flip = s[name]
        pts = R4C[i4] if long_ else R3C[i3]
        if not long_: pen += 6
        a, b = pts if not flip else pts[::-1]
        leg(a, name, "1", na); leg(b, name, "2", nb)
        (x1, y1), (x2, y2) = a, b
        if x1 == x2: bc = [(x1, y) for y in range(min(y1, y2) + 1, max(y1, y2))]
        else: bc = [(x, y1) for x in range(min(x1, x2) + 1, max(x1, x2))]
        body(bc, name)
    for name, (na, nb) in (("C1", ("VSF", "GND")), ("C2", ("5V", "GND"))):
        if name not in s: continue
        i, flip = s[name]
        a, b = CC[i] if not flip else CC[i][::-1]
        leg(a, name, "1", na); leg(b, name, "2", nb)
    for c, (part, pin, net) in legs.items():
        if c in bodies and bodies[c] != part: pen += 100
        if c in HDR: pen += 100
        if c in STRIP and STRIP[c] != net: pen += 100
        if c in pinnet and pinnet[c] != net: pen += 100
    return legs, bodies, pinnet, pen

NETS = ["GND", "3V", "VSF", "OUTM", "OUTP", "5V", "AN", "COL", "BASE", "DRV"]

def nbrs(c):
    x, y = c
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        n = (x + dx, y + dy)
        if n in CELLS and n not in HDR: yield n, 1.0, None
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        for k in (2, 3, 4):
            n = (x + dx * k, y + dy * k)
            if n in CELLS and n not in HDR:
                over = [(x + dx * i, y + dy * i) for i in range(1, k)]
                yield n, 7.0 + k, over

def route(legs, bodies, pinnet, order=NETS, max_jump=3):
    owner = {}
    for c, (_, _, net) in legs.items(): owner[c] = net
    for c, net in STRIP.items(): owner.setdefault(c, net)
    for c, net in pinnet.items(): owner.setdefault(c, net)
    tall = {c for c, p in bodies.items()}
    traces = []; jumps = []; unrouted = 0; length = 0
    for net in order:
        terms = [c for c, n in owner.items() if n == net and (c in legs or (c in pinnet and net in ("OUTM", "OUTP", "DRV", "5V")))]
        tree = set(c for c, n in STRIP.items() if n == net)
        if net == "5V": tree = {PINCELL["USB"]}
        pend = [t for t in terms if t not in tree]
        if not tree and pend: tree = {pend.pop(0)}
        while pend:
            dist = {c: 0 for c in tree}; prev = {}
            pq = [(0, c) for c in tree]; heapq.heapify(pq)
            found = None
            ps = set(pend)
            while pq:
                d, c = heapq.heappop(pq)
                if d > dist.get(c, 1e9): continue
                if c in ps: found = c; break
                for n, w, over in nbrs(c):
                    o = owner.get(n)
                    if o is not None and o != net: continue
                    if o == net and n not in ps and n not in tree: continue  # fremde Pins des Netzes nur als Ziel
                    if (n in STRIP or n in pinnet) and n not in ps: continue
                    if over is not None:
                        if len(jumps) >= max_jump: continue
                        if any(x in legs for x in over): continue
                        if n in legs and n not in ps: continue
                        if c in legs and c not in tree: continue
                        if c in legs: continue  # Bruecke braucht eigenes Loch
                        if n in legs: continue
                    nd = d + w
                    if nd < dist.get(n, 1e9):
                        dist[n] = nd; prev[n] = (c, over is not None); heapq.heappush(pq, (nd, n))
            if not found:
                unrouted += len(pend); break
            c = found; path = []
            while c not in tree:
                p, j = prev[c]; path.append((p, c, j)); c = p
            for p, c2, j in path:
                if j: jumps.append((net, p, c2))
                else: traces.append((net, p, c2)); length += 1
                owner[c2] = net; owner[p] = net if p not in owner else owner[p]
                tree.add(c2)
            pend = [t for t in pend if t not in tree]
    return owner, traces, jumps, unrouted, length

def score(s, orders=None):
    legs, bodies, pinnet, pen = build(s)
    if pen >= 100: return pen * 10, None
    best = None
    for order in (orders or [NETS, NETS[::-1], ["VSF", "GND", "3V", "OUTM", "OUTP", "COL", "AN", "5V", "BASE", "DRV"]]):
        owner, traces, jumps, un, length = route(legs, bodies, pinnet, order)
        sc = pen + un * 60 + len(jumps) * 15 + length * 0.4
        if best is None or sc < best[0]:
            best = (sc, (owner, traces, jumps, un, length, legs, bodies, pinnet, order))
    return best

def mutate(s):
    s = json.loads(json.dumps(s))
    k = random.choice(["tsop", "tsmp", "led", "q1", "R1", "R2", "R3", "R4", "R5", "C1", "C2", "pins", "rxdir", "flip"])
    if k in ("tsop", "tsmp"):
        cands = [i for i, x in enumerate(RXC) if x[0] == s["rxdir"]]
        s[k] = random.choice(cands)
    elif k == "rxdir":
        s["rxdir"] = "up" if s["rxdir"] == "down" else "down"
        for p in ("tsop", "tsmp"):
            s[p] = random.choice([i for i, x in enumerate(RXC) if x[0] == s["rxdir"]])
    elif k == "led": s["led"] = random.randrange(len(LEDC))
    elif k == "q1": s["q1"] = random.randrange(len(Q1C))
    elif k == "flip":
        f = random.choice(["ledflip", "q1flip"]); s[f] = not s[f]
    elif k in ("C1", "C2"): s[k] = [random.randrange(len(CC)), random.random() < .5]
    elif k == "pins":
        i = random.randrange(3); choices = [g for g in GPIO if g not in s["pins"]]
        s["pins"][i] = random.choice(choices)
    else:
        long_, i4, i3, flip = s[k]
        r = random.random()
        if r < .15: flip = not flip
        elif r < .25: long_ = not long_
        else:
            if long_: i4 = random.randrange(len(R4C))
            else: i3 = random.randrange(len(R3C))
        s[k] = [long_, i4, i3, flip]
    return s

def valid(s):
    return build(s)[3] < 100

def valid_mutate(s):
    for _ in range(500):
        n = mutate(s)
        if valid(n): return n
    return s

def valid_start():
    full = rand_state()
    for _ in range(100):
        s = {"rxdir": full["rxdir"], "pins": full["pins"], "ledflip": full["ledflip"], "q1flip": full["q1flip"]}
        ok = True
        for key in ["tsop", "tsmp", "led", "q1", "R1", "R2", "R3", "R4", "R5", "C1", "C2"]:
            for _ in range(3000):
                t = dict(s); t[key] = rand_state()[key]
                if key in ("tsop", "tsmp"):
                    t[key] = random.choice([i for i, x in enumerate(RXC) if x[0] == s["rxdir"]])
                if build(t)[3] < 100: s = t; break
            else:
                ok = False; break
        if ok: return s
    raise SystemExit("kein Start")

def anneal(seed, iters=20000):
    random.seed(seed)
    s = valid_start(); sc = score(s)[0]
    best = (sc, s)
    T0 = 30.0
    for it in range(iters):
        T = T0 * (1 - it / iters) + 0.3
        n = valid_mutate(s); nsc = score(n)[0]
        if nsc <= sc or random.random() < math.exp((sc - nsc) / T):
            s, sc = n, nsc
            if sc < best[0]: best = (sc, s)
    return best

if __name__ == "__main__":
    seed = int(sys.argv[1]); iters = int(sys.argv[2])
    sc, s = anneal(seed, iters)
    print(json.dumps({"score": sc, "state": s}))
