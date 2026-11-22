"""Orthogonal wire router for the generated schematic: replaces net-label connections with real wires.

Called by gen_schematic.main() before writing. Each group of same-named labels marks wire stubs that belong to one
net; the router joins them with Manhattan wires on the 1.27 mm grid and drops the labels. Rules:
  * never through a symbol body, a pin, another net's connection point (pin end, wire end / corner, label);
  * never along another net's wire; crossing one at right angles is allowed (no junction is made there);
  * text (references, values, headings) costs extra, so wires avoid it where they can;
  * bends cost extra, so runs stay straight and tidy.
A net that cannot be routed keeps its labels (the rare exception).
"""
import heapq
import math

G = 1.27
BEND, CROSS, TEXT, NEAR, HUG = 8.0, 14.0, 10.0, 1.5, 2.5


def ij(p):
    return (round(p[0] / G), round(p[1] / G))


def xy(c):
    return (round(c[0] * G, 2), round(c[1] * G, 2))


def _coords(node, out):
    if isinstance(node, list) and node:
        head = str(node[0])
        if head == "pin":
            return
        if head in ("start", "end", "xy", "center", "mid") and len(node) >= 3 and all(
                isinstance(v, (int, float)) for v in node[1:3]):
            out.append((float(node[1]), float(node[2])))
        if head == "circle":
            c = next((n for n in node if isinstance(n, list) and str(n[0]) == "center"), None)
            r = next((n for n in node if isinstance(n, list) and str(n[0]) == "radius"), None)
            num = lambda v: isinstance(v, (int, float))  # noqa: E731
            if c and r and len(c) >= 3 and num(c[1]) and num(c[2]) and num(r[1]):
                out += [(c[1] - r[1], c[2] - r[1]), (c[1] + r[1], c[2] + r[1])]
        for n in node[1:]:
            _coords(n, out)


def route(S):
    """S = the gen_schematic module (PARTS, WIRES, LABELS, NCS, TEXTS, helpers). Mutates WIRES and LABELS."""
    W, H = round(594 / G), round(420 / G)
    body = set()          # cells no wire may enter
    soft = {}             # cell -> extra cost (text)
    point = {}            # cell -> net id of a connection point (pin end, wire end / corner, label anchor)
    occ = {}              # cell -> {(net, 'h'|'v')}
    pin_net = {}          # pin end cell -> net name (from the intended maps / power symbols)
    pwr_cells = {}        # power symbols connect by name (the one kind of name connection that stays)

    # sheet frame and title block
    for i in range(W):
        for j in range(H):
            x, y = i * G, j * G
            if x < 14 or x > 580 or y < 14 or y > 406 or (x > 456 and y > 358):
                body.add((i, j))

    for p in S.PARTS:
        sym = S.load_symbol(p["lib"])
        pts = []
        _coords(sym, pts)
        pins = S.pins_of(sym)
        if pts:
            xs = [S.rot(px, py, p["r"]) for px, py in pts]
            x0, x1 = min(a for a, _ in xs), max(a for a, _ in xs)
            y0, y1 = min(b for _, b in xs), max(b for _, b in xs)
            for i in range(math.floor((p["x"] + x0) / G), math.ceil((p["x"] + x1) / G) + 1):
                for j in range(math.floor((p["y"] + y0) / G), math.ceil((p["y"] + y1) / G) + 1):
                    body.add((i, j))
        # pins: the leg is body, the end is a connection point
        for num, (px, py) in pins.items():
            end = ij(S.pin(p["ref"], num))
            net = p["nets"].get(num) if not p["ref"].startswith("#") else p["value"]
            cx, cy = ij((p["x"], p["y"]))
            dx = (cx > end[0]) - (cx < end[0]); dy = (cy > end[1]) - (cy < end[1])
            c = end
            for _ in range(3):                         # the 2.54 mm leg towards the body
                c = (c[0] + dx, c[1] + dy)
                body.add(c)
            pin_net[end] = net
            if p["ref"].startswith("#PWR"):                # power ports join by name; PWR_FLAGs only mark a net
                pwr_cells.setdefault(net, []).append(end)
        # visible reference / value text
        if not p["ref"].startswith("#"):
            (rx, ry, rj), (vx, vy, vj), hr, hv = S.field_layout(p, sym)
            for (tx, ty, tj), txt, hid in (((rx, ry, rj), p["ref"], hr), ((vx, vy, vj), p["value"], hv)):
                if hid:
                    continue
                w = 1.05 * len(str(txt))
                xa = tx if tj == "left" else tx - w if tj == "right" else tx - w / 2
                for i in range(math.floor(xa / G), math.ceil((xa + w) / G) + 1):
                    for j in range(math.floor((ty - 0.8) / G), math.ceil((ty + 0.8) / G) + 1):
                        soft[(i, j)] = soft.get((i, j), 0) + TEXT
    for t, x, y in S.TEXTS:                            # block headings: wires never cross them
        for i in range(math.floor(x / G) - 1, math.ceil((x + 1.75 * len(t)) / G) + 2):
            for j in range(math.floor((y - 2.6) / G), math.ceil((y + 0.6) / G) + 1):
                body.add((i, j))
    for x, y in S.NCS:
        body.add(ij((x, y)))
    body_margin = {(c[0] + di, c[1] + dj) for c in body for di in (-1, 0, 1) for dj in (-1, 0, 1)} - body

    # nets of the existing wiring: union-find over wire ends, pin ends and label anchors
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    def cells(a, b):
        a, b = ij(a), ij(b)
        n = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        sx = (b[0] > a[0]) - (b[0] < a[0]); sy = (b[1] > a[1]) - (b[1] < a[1])
        return [(a[0] + k * sx, a[1] + k * sy) for k in range(n + 1)], ("h" if sy == 0 else "v")

    wire_cells = []
    for a, b in S.WIRES:
        cs, o = cells(a, b)
        wire_cells.append((cs, o))
        for c in cs[1:]:
            union(cs[0], c)
    # anything sitting on a wire cell (pin ends, label anchors) joins that wire
    on_wire = {}
    for cs, _ in wire_cells:
        for c in cs:
            on_wire[c] = cs[0]
    for c in list(pin_net) + [ij((x, y)) for _, x, y, _ in S.LABELS]:
        find(c)
        if c in on_wire:
            union(c, on_wire[c])
    # power symbols with the same name are one net
    for n, cs in pwr_cells.items():
        for c in cs[1:]:
            union(cs[0], c)
    for _, x, y, _ in S.LABELS:
        pass
    # label names join their clusters too (that is what labels do) -> final net id = root
    lab_by = {}
    for name, x, y, a in S.LABELS:
        lab_by.setdefault(name, []).append(ij((x, y)))

    def net_of(c):
        return find(c)

    for cs, o in wire_cells:
        for k, c in enumerate(cs):
            occ.setdefault(c, set()).add((net_of(cs[0]), o))
            if k in (0, len(cs) - 1):
                point[c] = net_of(cs[0])
    for c in pin_net:
        point[c] = net_of(c)
    for name, cs in lab_by.items():
        for c in cs:
            point[c] = net_of(c)

    def astar(srcs, goal_root, net_ids):
        """Shortest Manhattan path from any src cell to a cell whose net is goal_root (or any of net_ids)."""
        openq, best, came = [], {}, {}
        for s in srcs:
            for d in "hv":
                k = (s, d)
                best[k] = 0.0; came[k] = None
                heapq.heappush(openq, (0.0, 0.0, s, d))
        goals = [c for c, n in point.items() if n in net_ids] + [c for c, s in occ.items() if any(n in net_ids for n, _ in s)]
        gx = sum(c[0] for c in goals) / max(1, len(goals)); gy = sum(c[1] for c in goals) / max(1, len(goals))
        n_iter = 0
        while openq:
            f, g, c, d = heapq.heappop(openq)
            if g > best.get((c, d), 1e18):
                continue
            n_iter += 1
            if n_iter > 400000:
                return None
            if c not in srcs:
                pn = point.get(c)
                here = occ.get(c, ())
                clean = not any(n not in net_ids for n, _ in here) and (pn is None or pn in net_ids)
                if clean and (pn in net_ids or any(n in net_ids for n, _ in here)):
                    path = [(c, d)]
                    while came[path[-1]] is not None:
                        path.append(came[path[-1]])
                    return [p for p, _ in reversed(path)]
            for nd, (di, dj) in (("h", (1, 0)), ("h", (-1, 0)), ("v", (0, 1)), ("v", (0, -1))):
                n = (c[0] + di, c[1] + dj)
                if not (0 <= n[0] < W and 0 <= n[1] < H) or n in body:
                    continue
                pn = point.get(n)
                if pn is not None and pn not in net_ids:
                    continue
                cost = 1.0 + soft.get(n, 0)
                others = [(nn, o) for nn, o in occ.get(n, ()) if nn not in net_ids]
                if any(o == nd for _, o in others):
                    continue                            # would run along another net's wire
                if others:
                    cost += CROSS
                # turning on a crossing cell would connect: only straight through
                if d != nd and c not in srcs:
                    if any(nn not in net_ids for nn, _ in occ.get(c, ())):
                        continue
                    cost += BEND
                # keep a cell of air next to other nets' points where possible
                for a in ((n[0] + 1, n[1]), (n[0] - 1, n[1]), (n[0], n[1] + 1), (n[0], n[1] - 1)):
                    q = point.get(a)
                    if q is not None and q not in net_ids:
                        cost += NEAR
                    if any(nn not in net_ids and o == nd for nn, o in occ.get(a, ())):
                        cost += HUG                     # running right next to another net's wire
                if n in body_margin:
                    cost += NEAR
                ng = g + cost
                if ng < best.get((n, nd), 1e18):
                    best[(n, nd)] = ng; came[(n, nd)] = (c, d)
                    h = abs(n[0] - gx) + abs(n[1] - gy)
                    heapq.heappush(openq, (ng + 0.5 * h, ng, n, nd))
        return None

    def commit(path, net):
        """Path cells -> straight wire runs; register the new copper."""
        runs, start = [], path[0]
        for k in range(1, len(path) - 1):
            a, b, c = path[k - 1], path[k], path[k + 1]
            if (a[0] == b[0]) != (b[0] == c[0]):
                runs.append((start, b)); start = b
        runs.append((start, path[-1]))
        for a, b in runs:
            if a == b:
                continue
            S.WIRES.append((xy(a), xy(b)))
            cs, o = cells(xy(a), xy(b))
            for k, c in enumerate(cs):
                occ.setdefault(c, set()).add((net, o))
            point[a] = net; point[b] = net

    kept, routed = [], 0
    names = sorted(lab_by, key=lambda n: (len(lab_by[n]), n))
    for name in names:
        anchors = lab_by[name]
        roots = []
        for c in anchors:
            r = net_of(c)
            if r not in roots:
                roots.append(r)
        tree = {roots[0]}
        ok = True
        rest = roots[1:]
        while rest:
            # connect the cluster nearest to the tree first
            best_r = min(rest, key=lambda r: min(abs(a[0] - b[0]) + abs(a[1] - b[1])
                                                 for a in anchors if net_of(a) == r for b in anchors if net_of(b) in tree))
            srcs = {a for a in anchors if net_of(a) == best_r}
            path = astar(srcs, None, tree | {best_r} - {best_r})
            if path is None:
                ok = False
                break
            commit(path, best_r)
            # merge the ids: relabel the new cluster as part of the tree
            tree.add(best_r)
            for c, n in list(point.items()):
                if n == best_r:
                    point[c] = roots[0]
            for c, s in occ.items():
                occ[c] = {(roots[0] if n == best_r else n, o) for n, o in s}
            tree = {roots[0]}
            rest.remove(best_r)
            routed += 1
        if not ok:
            kept.append(name)
    S.LABELS[:] = [l for l in S.LABELS if l[0] in kept]
    return routed, kept
