#!/usr/bin/env python3
"""Tidy routed copper after the grid router.

Per (net, layer):
  1. Join endpoints that only touch by overlapping copper (T joints split, near-miss ends merged).
  2. Prune dead ends (an end not on a pad, via or same-net zone).
  3. Straighten router staircases (Douglas-Peucker on chains between junctions, pads and vias).
  4. Undo fold-backs (overlapping edges). Acute notches left over are filled by fillet_notches.py.

    tidy_tracks.py IN OUT [--levels levels.json]

levels.json maps "NET@LAYER" (or "NET") -> level: 0 untouched; 1 joints, stubs, loops and acute corners only;
2 also merge steps < 0.06 mm; 3 also straighten to 0.03 mm, steps < 0.10 mm; 4 straighten to 0.06 mm,
steps < 0.12 mm (default 4). tools/tidy_board.py drives it with a DRC check and per-net fallback.
"""
import json, math, sys
from collections import defaultdict
import pcbnew

TOL_JOIN = 0.13e6      # ends this close (nm) are the same node
DP_TOL = {3: 0.03e6, 4: 0.06e6}
SHORT_BY_LEVEL = {1: 0, 2: 0.06e6, 3: 0.10e6, 4: 0.12e6}
TOP = 4


def main():
    src, dst = sys.argv[1], sys.argv[2]
    levels = {}
    if "--levels" in sys.argv:
        levels = json.load(open(sys.argv[sys.argv.index("--levels") + 1]))
    b = pcbnew.LoadBoard(src)
    tracks = list(b.GetTracks())
    viaobj = [t for t in tracks if t.GetClass() == "PCB_VIA"]
    vias = [(t.GetNetCode(), t.GetPosition().x, t.GetPosition().y, t.GetWidth(), i) for i, t in enumerate(viaobj)]
    pads = [(p.GetNetCode(), p) for fp in b.GetFootprints() for p in fp.Pads()]
    zones = list(b.Zones())
    tobj = defaultdict(list)
    for t in tracks:
        if t.GetClass() == "PCB_TRACK":
            tobj[(t.GetNetCode(), t.GetLayer())].append(t)
    groups = {k: [((t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y), t.GetWidth()) for t in ts]
              for k, ts in tobj.items()}
    names = {k: ts[0].GetNetname() for k, ts in tobj.items()}
    stats = defaultdict(int)
    stats["before"] = sum(len(v) for v in groups.values())
    cu = [l for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)]
    for _ in range(6):
        for (net, layer), segs in groups.items():
            lv = level(levels, names[(net, layer)], b.GetLayerName(layer))
            if lv == 0 or net == 0:
                continue

            def anchored(p, acc=0, net=net, layer=layer):
                x, y = p
                for vn, vx, vy, vw, _ in vias:
                    if vn == net and math.hypot(vx - x, vy - y) <= vw / 2 + acc:
                        return ("via", (vx, vy))
                v = pcbnew.VECTOR2I(int(x), int(y))
                for pn, pd in pads:
                    if pn == net and pd.IsOnLayer(layer) and pd.HitTest(v, int(acc)):
                        return ("pad", (pd.GetParent().GetReference(), pd.GetNumber()), (pd.GetPosition().x, pd.GetPosition().y))
                for z in zones:
                    if z.GetNetCode() == net and z.IsOnLayer(layer) and z.HitTestFilledArea(layer, v, int(acc)):
                        return ("zone", z.GetNetname(), p)
                return None

            taps = [((vx, vy), vw / 2) for vn, vx, vy, vw, _ in vias if vn == net]
            for pn, pd in pads:
                if pn == net and pd.IsOnLayer(layer):
                    c = pd.GetPosition(); sz = pd.GetSize()
                    taps.append(((c.x, c.y), min(sz.x, sz.y) / 2))
            groups[(net, layer)] = tidy(segs, anchored, lv, stats, taps)
        # a via that reaches copper on fewer than two layers is dead: drop it and prune again
        dead = []
        for v in vias:
            vn, vx, vy, vw, i = v
            if any(level(levels, viaobj[i].GetNetname(), b.GetLayerName(l)) == 0 for l in cu):
                continue
            pt = pcbnew.VECTOR2I(vx, vy); used = 0
            for l in cu:
                if any(math.dist((vx, vy), proj((vx, vy), a, e)[1]) <= (vw + w) / 2 for a, e, w in groups.get((vn, l), [])) \
                   or any(z.GetNetCode() == vn and z.IsOnLayer(l) and z.HitTestFilledArea(l, pt) for z in zones) \
                   or any(pn == vn and pd.IsOnLayer(l) and pd.HitTest(pt, int(vw / 2)) for pn, pd in pads):
                    used += 1
            if used < 2:
                dead.append(v)
        if not dead:
            break
        for v in dead:
            vias.remove(v); b.Remove(viaobj[v[4]]); stats["dead_via"] += 1
    for k, ts in tobj.items():
        if level(levels, names[k], b.GetLayerName(k[1])) == 0 or k[0] == 0:
            continue
        for t in ts:
            b.Remove(t)
        for a, e, w in groups[k]:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(int(round(a[0])), int(round(a[1]))))
            t.SetEnd(pcbnew.VECTOR2I(int(round(e[0])), int(round(e[1]))))
            t.SetWidth(w); t.SetLayer(k[1]); t.SetNetCode(k[0])
            b.Add(t)
    stats["after"] = sum(len(v) for v in groups.values())
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(dst, b)
    print(json.dumps(stats))


def level(levels, net, layer):
    return levels.get(f"{net}@{layer}", levels.get(net, TOP))


def proj(p, a, e):
    dx, dy = e[0] - a[0], e[1] - a[1]
    L = dx * dx + dy * dy
    if L == 0:
        return 0.0, a
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L
    t = max(0.0, min(1.0, t))
    return t, (a[0] + t * dx, a[1] + t * dy)


def tidy(segs, anchored, lv, stats, taps=()):
    """segs: [((x,y),(x,y),w)] for one net on one layer. anchored(p, acc) -> truthy if p touches a pad/via/zone."""
    segs = [(tuple(map(int, a)), tuple(map(int, e)), w) for a, e, w in segs if a != e]
    # --- 0: a segment running through a same-net via or pad is split there, so pruning never cuts it
    for c, r in taps:
        c = (int(c[0]), int(c[1]))
        for j in range(len(segs)):
            a, e, w = segs[j]
            t, q = proj(c, a, e)
            if 0.0 < t < 1.0 and math.dist(c, q) <= r and math.dist(c, a) > r and math.dist(c, e) > r:
                segs[j] = (a, c, w); segs.append((c, e, w)); stats["tap_split"] += 1
    # --- 1: joints made only by overlapping copper become real edges
    joints = []
    changed = True
    while changed:                      # an end resting on another segment's middle splits it
        changed = False
        cnt = defaultdict(int)
        for a, e, _ in segs:
            cnt[a] += 1; cnt[e] += 1
        for i in range(len(segs)):
            for p in segs[i][:2]:
                if cnt[p] != 1:
                    continue
                for j, (c, d, w2) in enumerate(segs):
                    if j == i or p in (c, d):
                        continue
                    t, q = proj(p, c, d)
                    q = (int(round(q[0])), int(round(q[1])))
                    if 0.0 < t < 1.0 and q not in (c, d) and math.dist(p, q) < (segs[i][2] + w2) / 2:
                        segs[j] = (c, q, w2); segs.append((q, d, w2))
                        if q != p:
                            joints.append((p, q, min(segs[i][2], w2)))
                        stats["tsplit"] += 1; changed = True; break
                if changed: break
            if changed: break
    width_at = defaultdict(int)
    for a, e, w in segs:
        width_at[a] = max(width_at[a], w); width_at[e] = max(width_at[e], w)
    pts = list(width_at)
    for i, p in enumerate(pts):         # ends that overlap other ends
        for q in pts[i + 1:]:
            if math.dist(p, q) < (width_at[p] + width_at[q]) / 2 and math.dist(p, q) > 0:
                joints.append((p, q, min(width_at[p], width_at[q])))
    adj = defaultdict(dict)
    for a, e, w in segs + joints:
        if a != e:
            adj[a][e] = adj[e][a] = max(w, adj[a].get(e, 0))
    anch = {n: anchored(n, max(adj[n].values()) / 2) for n in adj}
    inside = {n: bool(anchored(n, 0)) for n in adj}

    # --- 1b: contract tiny edges (router staircase steps, joints) so nodes sit >= 0.12 mm apart
    SHORT = SHORT_BY_LEVEL[lv]
    merged = True
    while merged:
        merged = False
        for n in list(adj):
            if n not in adj:
                continue
            for m in list(adj[n]):
                if math.dist(n, m) >= SHORT:
                    continue
                if anch[n] and anch[m] and anch[n][:2] != anch[m][:2]:
                    continue
                def rank(k):
                    c = anch[k][-1] if anch[k] else k
                    return (inside[k], bool(anch[k]), -math.dist(k, c))
                if rank(m) > rank(n):
                    keep, drop = m, n
                else:
                    keep, drop = n, m
                for k, w in adj[drop].items():
                    if k != keep:
                        adj[keep][k] = adj[k][keep] = max(w, adj[keep].get(k, 0))
                    del adj[k][drop]
                del adj[drop]
                anch[keep] = anch[keep] or anch[drop]; inside[keep] = inside[keep] or inside[drop]
                stats["contract"] += 1; merged = True
                break
            if merged:
                break

    # --- 1c: overlapping collinear edges from one node: hang the far one off the near one
    moved = True
    while moved:
        moved = False
        for n in list(adj):
            ns = list(adj[n])
            for i in range(len(ns)):
                for j in range(len(ns)):
                    a, c = ns[i], ns[j]
                    if i == j or c not in adj[n] or a not in adj[n]:
                        continue
                    if angle(a, n, c) < 1.0 and math.dist(n, a) < math.dist(n, c):
                        w = adj[n].pop(c); del adj[c][n]
                        if a != c and c not in adj[a]:
                            adj[a][c] = adj[c][a] = w
                        stats["overlap"] += 1; moved = True

    # --- 1d: loops on one net and layer are router artefacts (tiny triangles = acute corners): keep a
    #        spanning forest, longest edges first
    parent = {n: n for n in adj}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    edges = sorted({(min(n, m), max(n, m)) for n in adj for m in adj[n]}, key=lambda e: -math.dist(*e))
    for n, m in edges:
        rn, rm = find(n), find(m)
        if rn == rm:
            del adj[n][m]; del adj[m][n]; stats["loop_cut"] += 1
        else:
            parent[rn] = rm

    # --- 2: prune dead ends
    pruned = True
    while pruned:
        pruned = False
        for n in list(adj):
            if len(adj[n]) == 1 and not anch[n]:
                (m,) = adj[n]
                del adj[m][n]; del adj[n]; pruned = True; stats["stub"] += 1
            elif len(adj[n]) == 0:
                del adj[n]

    # --- 3: chains between key nodes
    def key(n):
        return anch[n] or len(adj[n]) != 2 or len(set(adj[n].values())) > 1
    seen = set(); chains = []
    for n in adj:
        if not key(n):
            continue
        for m in adj[n]:
            if (n, m) in seen:
                continue
            path = [n, m]; w = adj[n][m]; seen.add((n, m)); seen.add((m, n))
            while not key(path[-1]):
                cur, prev = path[-1], path[-2]
                (nxt,) = [x for x in adj[cur] if x != prev]
                seen.add((cur, nxt)); seen.add((nxt, cur)); path.append(nxt)
            chains.append((path, w))
    # pure loops with no key node: keep as-is
    for n in adj:
        for m in adj[n]:
            if (n, m) not in seen:
                seen.add((n, m)); seen.add((m, n)); chains.append(([n, m], adj[n][m]))

    out = []
    for path, w in chains:
        if lv >= 3:
            path = dp(path, DP_TOL[lv])
        path = merge_collinear(path)
        out += [(path[i], path[i + 1], w) for i in range(len(path) - 1) if path[i] != path[i + 1]]
    return fix_corners(out, lambda n: anchored(n, 0), stats)


def fix_corners(out, inside, stats):
    """Clean-up after straightening: merge sub-5 um edges and undo fold-backs (two edges leaving a node in
    the same direction). Acute notches that remain are filled by fillet_notches.py, which checks the real
    copper outline instead of centre lines."""
    E = {}
    for a, e, w in out:
        if a != e:
            E[(min(a, e), max(a, e))] = w
    def adjacency():
        adj = defaultdict(dict)
        for (a, e), w in E.items():
            adj[a][e] = w; adj[e][a] = w
        return adj
    def drop(a, e):
        return E.pop((min(a, e), max(a, e)))
    def add(a, e, w):
        a = (int(round(a[0])), int(round(a[1]))); e = (int(round(e[0])), int(round(e[1])))
        if a != e:
            E[(min(a, e), max(a, e))] = w
        return a
    cache = {}
    def ins(n):
        if n not in cache:
            cache[n] = bool(inside(n))
        return cache[n]
    for _ in range(5000):
        adj = adjacency(); changed = False
        # merge sub-5 um edges (rounding left-overs); the end inside a pad/via stays put
        for (a, e) in list(E):
            if math.dist(a, e) < 0.005e6 and not (ins(a) and ins(e)):
                keep, gone = (a, e) if (ins(a), len(adj[a])) >= (ins(e), len(adj[e])) else (e, a)
                drop(a, e)
                for k, w in list(adj[gone].items()):
                    if k != keep and (min(gone, k), max(gone, k)) in E:
                        drop(gone, k); add(keep, k, w)
                stats["tiny_merged"] += 1; changed = True
                break
        if changed:
            continue
        # fold-backs: two edges leaving a node in the same direction overlap; hang the longer off the shorter
        for n, nb in adj.items():
            ns = list(nb)
            for i in range(len(ns)):
                for j in range(len(ns)):
                    a, b = ns[i], ns[j]
                    if i != j and angle(a, n, b) < 1.0 and math.dist(n, a) > math.dist(n, b):
                        w = drop(n, a); add(b, a, w); stats["overlap"] += 1; changed = True
                        break
                if changed: break
            if changed: break
        if not changed:
            break
    adj = adjacency()
    for n in list(adj):
        if len(adj[n]) == 2 and not ins(n):
            a, c = adj[n]
            if angle(a, n, c) > 179.5 and adj[n][a] == adj[n][c] and (min(a, n), max(a, n)) in E and (min(c, n), max(c, n)) in E:
                w = drop(a, n); drop(n, c); add(a, c, w)
                adj[a].pop(n, None); adj[c].pop(n, None); adj[a][c] = adj[c][a] = w
                stats["collinear"] += 1
    return [(a, e, w) for (a, e), w in E.items()]


def dp(path, tol):
    if len(path) < 3:
        return path
    a, e = path[0], path[-1]
    dmax, k = 0, 0
    for i in range(1, len(path) - 1):
        d = math.dist(path[i], proj(path[i], a, e)[1])
        if d > dmax:
            dmax, k = d, i
    if dmax <= tol:
        return [a, e]
    return dp(path[:k + 1], tol)[:-1] + dp(path[k:], tol)


def merge_collinear(path):
    out = [path[0]]
    for i in range(1, len(path) - 1):
        a, p, c = out[-1], path[i], path[i + 1]
        cross = (p[0] - a[0]) * (c[1] - p[1]) - (p[1] - a[1]) * (c[0] - p[0])
        dot = (p[0] - a[0]) * (c[0] - p[0]) + (p[1] - a[1]) * (c[1] - p[1])
        if abs(cross) < 1e3 * max(1, math.dist(a, c)) and dot > 0:
            continue
        out.append(p)
    out.append(path[-1])
    return out


def angle(a, p, c):
    v1 = (a[0] - p[0], a[1] - p[1]); v2 = (c[0] - p[0], c[1] - p[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 180.0
    return math.degrees(math.acos(max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / n1 / n2))))


if __name__ == "__main__":
    main()
