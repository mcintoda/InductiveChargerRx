#!/usr/bin/env python3
"""Finish the routing after the autorouter: a small grid maze router driven by KiCad's DRC.

    python3 hardware/tools/fixroute.py        # after route.py finish

1. Delete autorouted vias that violate clearance to a pad of another net (Freerouting's GND fan-out vias).
2. Loop up to N times:
     run DRC -> for every unconnected pair of items, A* route between them on F.Cu / In2.Cu / B.Cu
     (0.2 mm tracks, 0.6/0.3 mm vias, 0.2 mm clearance, 0.5 mm to the board edge, keep-outs respected);
     GND items that only reach a pour island get a via into the In1 GND plane instead.
3. Refill zones, write the DRC report.

Obstacles are rasterised with PIL at 0.05 mm per cell, grown by clearance + half the track (or via) size.
"""
import heapq
import math
import os
import re
import sys

import pcbnew
from PIL import Image, ImageDraw
import numpy as np

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "bath_monitor.kicad_pcb")
RPT = os.path.join(HW, "kicad", "route", "drc.rpt")
OX, OY = 100.0, 50.0
RES = 0.05                         # mm per cell
TRACK_W, CLR, VIA_D, VIA_DRILL, EDGE_CLR, HOLE_CLR = 0.2, 0.15, 0.6, 0.3, 0.5, 0.25   # clearance: .kicad_pro Default
MARGIN = 0.035                     # rasterisation slack
LAYERS = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
VIA_COST = 25.0
# autorouter-only keep-outs, board frame (x0, y0, x1, y1) per layer (see route.py constrain_dsn)
BAND = (36.0, 101.5)
FRONT_BAND = (30.5, 101.5)
KEEPOUTS = {pcbnew.F_Cu: [(-1, FRONT_BAND[0], 39, FRONT_BAND[1])],
            pcbnew.B_Cu: [(-1, BAND[0], 39, BAND[1])]}
VIA_KEEPOUTS = [(-1, BAND[0], 39, BAND[1])]
# flash tab: only the middle bridge carries copper
for ya, yb in [(9.0, 14.5), (16.5, 22.0)]:
    for lay in LAYERS:
        KEEPOUTS.setdefault(lay, []).append((37.5, ya, 40.0, yb))
    VIA_KEEPOUTS.append((37.5, ya, 40.0, yb))


def mm(v):
    return int(round(v * 1e6))


class Grid:
    def __init__(self, board):
        bb = board.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = bb.GetX() / 1e6, bb.GetY() / 1e6
        self.w = int(bb.GetWidth() / 1e6 / RES) + 2
        self.h = int(bb.GetHeight() / 1e6 / RES) + 2

    def ij(self, x_mm, y_mm):
        return int(round((x_mm - self.x0) / RES)), int(round((y_mm - self.y0) / RES))

    def xy(self, i, j):
        return self.x0 + i * RES, self.y0 + j * RES

    def blank(self, val=0):
        return Image.new("1", (self.w, self.h), val)


def poly_points(g, chain):
    return [((chain.CPoint(k).x / 1e6 - g.x0) / RES, (chain.CPoint(k).y / 1e6 - g.y0) / RES)
            for k in range(chain.PointCount())]


def draw_polyset(g, d, ps, fill=1):
    for o in range(ps.OutlineCount()):
        d.polygon(poly_points(g, ps.Outline(o)), fill=fill)
        for h in range(ps.HoleCount(o)):
            d.polygon(poly_points(g, ps.Hole(o, h)), fill=1 - fill)


def item_shape(item, layer, grow):
    """Pads only (tracks / vias are drawn directly, see draw_item)."""
    ps = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(ps, layer, mm(grow), mm(0.005))
    return ps


def draw_item(g, d, item, layer, grow, fill=1):
    if item.GetClass() == "PCB_VIA":
        r = (item.GetWidth() / 2e6 + grow) / RES
        i, j = g.ij(item.GetPosition().x / 1e6, item.GetPosition().y / 1e6)
        d.ellipse([i - r, j - r, i + r, j + r], fill=fill)
    elif item.GetClass() in ("PCB_TRACK", "PCB_ARC"):
        r = (item.GetWidth() / 2e6 + grow) / RES
        a = g.ij(item.GetStart().x / 1e6, item.GetStart().y / 1e6)
        b = g.ij(item.GetEnd().x / 1e6, item.GetEnd().y / 1e6)
        d.line([a, b], fill=fill, width=max(1, int(math.ceil(2 * r))))
        for c in (a, b):
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=fill)
    else:
        draw_polyset(g, d, item_shape(item, layer, grow), fill)


def on_layer(item, layer):
    return item.IsOnLayer(layer)


def build_obstacles(board, g, net, grow, keepouts=True):
    """Per layer: 1 = centre-line of new copper (track if grow = track rule, via if via rule) not allowed."""
    gnd = board.FindNet("GND").GetNetCode()
    maps = {}
    for lay in LAYERS + [pcbnew.In1_Cu]:
        im = g.blank(0)
        d = ImageDraw.Draw(im)
        # outside the board (edge clearance) and the slots
        ps = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(ps)
        ps.Deflate(mm(EDGE_CLR + grow - CLR), 16)
        inside = g.blank(0)
        draw_polyset(g, ImageDraw.Draw(inside), ps, 1)
        inside = np.array(inside, dtype=bool)
        items = []
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    r = p.GetDrillSize().x / 2e6 + HOLE_CLR + grow - CLR
                    cx, cy = p.GetPosition().x / 1e6, p.GetPosition().y / 1e6
                    i, j = g.ij(cx, cy); rr = r / RES
                    d.ellipse([i - rr, j - rr, i + rr, j + rr], fill=1)
                elif on_layer(p, lay) and p.GetNetCode() != net:
                    items.append(p)
        for t in board.GetTracks():
            if on_layer(t, lay) and t.GetNetCode() != net:
                items.append(t)
        for it in items:
            draw_item(g, d, it, lay, grow)
        # other nets' pours on this layer (GND pours refill around new copper, so they are not obstacles)
        for z in board.Zones():
            if z.GetIsRuleArea():
                if z.IsOnLayer(lay) and z.GetDoNotAllowTracks():
                    zp = pcbnew.SHAPE_POLY_SET(z.Outline())
                    zp.Inflate(mm(grow), 16)
                    draw_polyset(g, d, zp, 1)
                continue
            if z.IsOnLayer(lay) and z.GetNetCode() not in (net, gnd) and lay != pcbnew.In1_Cu:
                fp_ = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(lay))
                fp_.Inflate(mm(grow), 16)
                draw_polyset(g, d, fp_, 1)
        for (x0, y0, x1, y1) in (KEEPOUTS.get(lay, []) if keepouts else []):
            a = g.ij(OX + x0, OY + y0); b = g.ij(OX + x1, OY + y1)
            d.rectangle([a[0], a[1], b[0], b[1]], fill=1)
        maps[lay] = np.array(im, dtype=bool) | ~inside
    return maps


def via_map(board, g, net):
    # track keep-outs do not apply to vias (they only need clearance to real copper + VIA_KEEPOUTS)
    m = build_obstacles(board, g, net, VIA_D / 2 + CLR + MARGIN, keepouts=False)
    # In1 copper that is not a pour (the GND strap) also blocks vias of other nets
    blocked = m[pcbnew.F_Cu] | m[pcbnew.In2_Cu] | m[pcbnew.B_Cu] | m[pcbnew.In1_Cu]
    im = Image.fromarray(blocked)
    d = ImageDraw.Draw(im)
    for (x0, y0, x1, y1) in VIA_KEEPOUTS:
        a = g.ij(OX + x0, OY + y0); b = g.ij(OX + x1, OY + y1)
        d.rectangle([a[0], a[1], b[0], b[1]], fill=1)
    # vias also keep hole-to-hole distance from every other hole (any net, incl. its own pads' holes)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.HasHole():
                r = p.GetDrillSize().x / 2e6 + VIA_DRILL / 2 + HOLE_CLR + MARGIN
                i, j = g.ij(p.GetPosition().x / 1e6, p.GetPosition().y / 1e6); rr = r / RES
                d.ellipse([i - rr, j - rr, i + rr, j + rr], fill=1)
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            r = t.GetDrillValue() / 2e6 + VIA_DRILL / 2 + HOLE_CLR + MARGIN
            i, j = g.ij(t.GetPosition().x / 1e6, t.GetPosition().y / 1e6); rr = r / RES
            d.ellipse([i - rr, j - rr, i + rr, j + rr], fill=1)
    return np.array(im, dtype=bool)


def item_cells(g, item, layers):
    """Grid cells covered by an item (its own copper), per routing layer."""
    out = {}
    for lay in layers:
        if not item.IsOnLayer(lay):
            continue
        im = g.blank(0)
        draw_item(g, ImageDraw.Draw(im), item, lay, 0)
        ys, xs = np.nonzero(np.array(im, dtype=bool))
        if len(xs):
            out[lay] = set(zip(xs.tolist(), ys.tolist()))
    return out


def astar(g, obst, vmap, src, dst, dst_any_via=None):
    """src/dst: {layer: set(cells)}. dst_any_via: bool mask, reaching a via-legal cell there also ends."""
    L = {lay: k for k, lay in enumerate(LAYERS)}
    goal = {(L[l], i, j) for l, cells in dst.items() if l in L for (i, j) in cells}
    gx = [c for c in goal]
    if not goal and dst_any_via is None:
        return None
    tx = np.mean([c[1] for c in gx]) if gx else None
    ty = np.mean([c[2] for c in gx]) if gx else None

    def h(i, j):
        return 0 if tx is None else math.hypot(i - tx, j - ty) * 0.9

    openq, came, cost = [], {}, {}
    for l, cells in src.items():
        if l not in L:
            continue
        for (i, j) in cells:
            s = (L[l], i, j)
            cost[s] = 0.0
            heapq.heappush(openq, (h(i, j), 0.0, s))
            came[s] = None
    blocked = [obst[l] for l in LAYERS]
    steps = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    n = 0
    while openq:
        f, c, s = heapq.heappop(openq)
        if c > cost.get(s, 1e18):
            continue
        k, i, j = s
        if s in goal and came[s] is not None:
            return reconstruct(came, s)
        if dst_any_via is not None and dst_any_via[j, i] and not vmap[j, i] and came[s] is not None:
            return reconstruct(came, s) + [("via_end", i, j)]
        n += 1
        if n > 3_000_000:
            return None
        for di, dj, w in steps:
            a, b = i + di, j + dj
            if not (0 <= a < g.w and 0 <= b < g.h):
                continue
            ns = (k, a, b)
            if blocked[k][b, a] and ns not in goal:
                continue
            nc = c + w
            if nc < cost.get(ns, 1e18):
                cost[ns] = nc; came[ns] = s
                heapq.heappush(openq, (nc + h(a, b), nc, ns))
        if not vmap[j, i]:
            for k2 in range(len(LAYERS)):
                if k2 == k:
                    continue
                ns = (k2, i, j)
                if blocked[k2][j, i] and ns not in goal:
                    continue
                nc = c + VIA_COST
                if nc < cost.get(ns, 1e18):
                    cost[ns] = nc; came[ns] = s
                    heapq.heappush(openq, (nc + h(i, j), nc, ns))
    return None


def reconstruct(came, s):
    path = []
    while s is not None:
        path.append(s); s = came[s]
    return path[::-1]


def commit_path(board, g, net, path):
    """Turn a cell path into tracks (merged straight runs) and vias."""
    netobj = board.FindNet(net) if isinstance(net, str) else board.GetNetInfo().GetNetItem(net)
    added = 0
    via_end = None
    if path and path[-1][0] == "via_end":
        via_end = path.pop()
    pts = [(LAYERS[k], i, j) for k, i, j in path]

    def add_track(a, b, lay):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(g.xy(*a)[0]), mm(g.xy(*a)[1])))
        t.SetEnd(pcbnew.VECTOR2I(mm(g.xy(*b)[0]), mm(g.xy(*b)[1])))
        t.SetWidth(mm(TRACK_W)); t.SetLayer(lay); t.SetNet(netobj)
        board.Add(t)

    def add_via(c):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm(g.xy(*c)[0]), mm(g.xy(*c)[1])))
        v.SetWidth(mm(VIA_D)); v.SetDrill(mm(VIA_DRILL)); v.SetNet(netobj)
        board.Add(v)

    run_start = 0
    for idx in range(1, len(pts) + 1):
        end_run = idx == len(pts) or pts[idx][0] != pts[run_start][0]
        if end_run:
            lay = pts[run_start][0]
            cells = [(p[1], p[2]) for p in pts[run_start:idx]]
            # merge collinear steps
            seg_a = cells[0]; prev = cells[0]; d0 = None
            for c in cells[1:]:
                dd = (c[0] - prev[0], c[1] - prev[1])
                if d0 is not None and dd != d0:
                    add_track(seg_a, prev, lay); added += 1; seg_a = prev
                d0 = dd; prev = c
            if prev != seg_a:
                add_track(seg_a, prev, lay); added += 1
            if idx < len(pts):
                add_via((pts[idx][1], pts[idx][2]))
            run_start = idx
    if via_end:
        add_via((via_end[1], via_end[2]))
    return added


def drc(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.WriteDRCReport(board, RPT, pcbnew.EDA_UNITS_MILLIMETRES, True)
    return open(RPT).read()


ITEM = re.compile(r"@\((-?[\d.]+) mm, (-?[\d.]+) mm\): (.*) on ([\w.]+)")


def find_item(board, x, y, desc, layer):
    pos = pcbnew.VECTOR2I(mm(x), mm(y))
    netm = re.search(r"\[(.*?)\]", desc)
    netname = netm.group(1) if netm else None
    m = re.match(r"(?:PTH )?[Pp]ad (\S+) \[(.*?)\] of (\S+)", desc)
    if m:
        fp = board.FindFootprintByReference(m.group(3))
        for p in fp.Pads():
            if p.GetNumber() == m.group(1) and p.GetPosition() == pos:
                return p
        return next((p for p in fp.Pads() if p.GetNumber() == m.group(1)), None)
    if desc.startswith("Track") or desc.startswith("Via"):
        best, bd = None, 1e18
        for t in board.GetTracks():
            if desc.startswith("Via") != (t.GetClass() == "PCB_VIA"):
                continue
            if netname and t.GetNetname() != netname:
                continue
            if t.GetClass() != "PCB_VIA" and board.GetLayerName(t.GetLayer()) != layer:
                continue
            for q in ([t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]):
                dd = (q.x - pos.x) ** 2 + (q.y - pos.y) ** 2
                if dd < bd:
                    best, bd = t, dd
        return best
    return None


def unconnected(report):
    pairs = []
    blocks = report.split("[unconnected_items]")[1:]
    for b in blocks:
        its = ITEM.findall(b.split("\n[")[0])[:2]
        if len(its) == 2:
            pairs.append(its)
    return pairs


def remove_bad_vias(board, report):
    """Autorouted vias with a clearance / hole-clearance error against a pad of another net."""
    bad = set()
    for kind in ("[clearance]", "[hole_clearance]", "[solder_mask_bridge]"):
        for b in report.split(kind)[1:]:
            its = ITEM.findall(b.split("\n[")[0])[:2]
            for x, y, desc, lay in its:
                if desc.startswith("Via"):
                    bad.add((round(float(x), 3), round(float(y), 3)))
    doomed = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and
              (round(t.GetPosition().x / 1e6, 3), round(t.GetPosition().y / 1e6, 3)) in bad]
    for v in doomed:
        # take the via's stub tracks with it
        p = v.GetPosition()
        for t in list(board.GetTracks()):
            if t.GetClass() != "PCB_VIA" and t.GetNetCode() == v.GetNetCode() and (t.GetStart() == p or t.GetEnd() == p) \
                    and t.GetLength() < mm(1.0):
                board.Delete(t)
        board.Delete(v)
    return len(doomed)


def remove_bad_tracks(board, report, kinds=("[clearance]",)):
    """Unlocked tracks with a clearance error, or with a dangling end."""
    doomed = set()
    for kind in kinds:
        for blk in report.split(kind)[1:]:
            for x, y, desc, lay in ITEM.findall(blk.split("\n[")[0])[:2]:
                if desc.startswith("Track"):
                    t = find_item(board, float(x), float(y), desc, lay)
                    if t is not None and not t.IsLocked():
                        doomed.add(t.m_Uuid.AsString())
    n = 0
    for t in list(board.GetTracks()):
        if t.m_Uuid.AsString() in doomed:
            board.Delete(t); n += 1
    return n


def score(report):
    return len(unconnected(report)) + 10 * report.count("[clearance]:") + 10 * report.count("[hole_clearance]:")


def rip_up(board, net, a, b, pad):
    if b is None:
        bb = a.GetBoundingBox()
    elif a is None:
        bb = b.GetBoundingBox()
    else:
        bb = a.GetBoundingBox(); bb.Merge(b.GetBoundingBox())
    bb.Inflate(mm(pad))
    doomed = [t for t in board.GetTracks() if not t.IsLocked() and t.GetNetCode() != net
              and bb.Intersects(t.GetBoundingBox())]
    for t in doomed:
        board.Delete(t)
    return len(doomed)


def fix_islands(board, g):
    """Every filled GND fragment on an outer layer that holds no GND via / PTH gets a via into In1."""
    gnd = board.FindNet("GND")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    vmap = via_map(board, g, gnd.GetNetCode())
    holes = [t.GetPosition() for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gnd.GetNetCode()]
    holes += [p.GetPosition() for fp in board.GetFootprints() for p in fp.Pads()
              if p.GetNetCode() == gnd.GetNetCode() and p.HasHole()]
    in1 = g.blank(0); d = ImageDraw.Draw(in1)
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.GetNetCode() == gnd.GetNetCode() and z.IsOnLayer(pcbnew.In1_Cu):
            draw_polyset(g, d, z.GetFilledPolysList(pcbnew.In1_Cu), 1)
    in1 = np.array(in1, dtype=bool)
    added = 0
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() != gnd.GetNetCode():
            continue
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu):
            if not z.IsOnLayer(lay):
                continue
            polys = z.GetFilledPolysList(lay)
            for o in range(polys.OutlineCount()):
                one = pcbnew.SHAPE_POLY_SET(); one.AddOutline(polys.Outline(o))
                if any(one.Contains(h) for h in holes):
                    continue
                im = g.blank(0)
                ImageDraw.Draw(im).polygon(poly_points(g, polys.Outline(o)), fill=1)
                ok = np.array(im, dtype=bool) & ~vmap & in1
                ys, xs = np.nonzero(ok)
                if not len(xs):
                    continue
                c = len(xs) // 2
                v = pcbnew.PCB_VIA(board)
                x, y = g.xy(xs[c], ys[c])
                v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y))); v.SetWidth(mm(VIA_D)); v.SetDrill(mm(VIA_DRILL))
                v.SetNet(gnd)
                board.Add(v); added += 1
                holes.append(v.GetPosition())
                vmap = via_map(board, g, gnd.GetNetCode())
    return added


def fix_pad_islands(board, g, in1):
    """GND SMD pads whose outer-layer pour fragment has no via: short track + via into the In1 plane."""
    gnd = board.FindNet("GND"); gc = gnd.GetNetCode()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    holes = [t.GetPosition() for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gc]
    holes += [p.GetPosition() for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetCode() == gc and p.HasHole()]
    added = 0
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != gc or p.HasHole():
                continue
            lay = pcbnew.B_Cu if p.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu
            frag = None
            for z in board.Zones():
                if z.GetIsRuleArea() or z.GetNetCode() != gc or not z.IsOnLayer(lay):
                    continue
                polys = z.GetFilledPolysList(lay)
                for o in range(polys.OutlineCount()):
                    one = pcbnew.SHAPE_POLY_SET(); one.AddOutline(polys.Outline(o))
                    if one.Contains(p.GetPosition()):
                        frag = one
            if frag is None or any(frag.Contains(h) for h in holes):
                continue
            obst = build_obstacles(board, g, gc, TRACK_W / 2 + CLR + MARGIN)
            vmap = via_map(board, g, gc)
            path = astar(g, obst, vmap, item_cells(g, p, [lay]), {}, in1)
            if path is None:
                print("  no via escape for", fp.GetReference(), p.GetNumber())
                continue
            commit_path(board, g, gc, path); added += 1
            holes = [t.GetPosition() for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gc]
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return added


def in1_mask(board, g):
    gnd = board.FindNet("GND").GetNetCode()
    im = g.blank(0); d = ImageDraw.Draw(im)
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.GetNetCode() == gnd and z.IsOnLayer(pcbnew.In1_Cu):
            draw_polyset(g, d, z.GetFilledPolysList(pcbnew.In1_Cu), 1)
    return np.array(im, dtype=bool)


def route_pair(board, g, pair, in1, rip=0.0, side="ab"):
    """Route one DRC unconnected pair. Returns (net name, segments or None)."""
    global TRACK_W
    (xa, ya, da, la), (xb, yb, db, lb) = pair
    ia = None if da.startswith("Zone") else find_item(board, float(xa), float(ya), da, la)
    ib = None if db.startswith("Zone") else find_item(board, float(xb), float(yb), db, lb)
    src_item = ia or ib
    if src_item is None:
        return None, None
    other = ib if src_item is ia else ia
    net = src_item.GetNetCode()
    name = board.GetNetInfo().GetNetItem(net).GetNetname()
    if rip and other is not None:
        rip_up(board, net, src_item if "a" in side else None, other if "b" in side else None, pad=rip)
    obst = build_obstacles(board, g, net, TRACK_W / 2 + CLR + MARGIN)
    vmap = via_map(board, g, net)
    src = item_cells(g, src_item, LAYERS)
    dst = item_cells(g, other, LAYERS) if other is not None else {}
    dst_via = in1 if name == "GND" else None
    path = astar(g, obst, vmap, src, dst, dst_via)
    if path is None:                                   # fine-pitch fallback: 0.15 mm track
        TRACK_W = 0.15
        try:
            obst = build_obstacles(board, g, net, TRACK_W / 2 + CLR + MARGIN)
            path = astar(g, obst, vmap, src, dst, dst_via)
            if path is None:
                return name, None
            return name, commit_path(board, g, net, path)
        finally:
            TRACK_W = 0.2
    return name, commit_path(board, g, net, path)


def plain_rounds(board, g, in1, rounds=3):
    for _ in range(rounds):
        rep = drc(board)
        remove_bad_tracks(board, rep)
        pairs = unconnected(drc(board))
        if not pairs:
            return score(drc(board))
        progress = False
        for pr in pairs:
            name, n = route_pair(board, g, pr, in1)
            progress |= bool(n)
        if not progress:
            break
    return score(drc(board))


def main():
    tmp = os.path.join(HW, "kicad", "route", "fix_tmp.kicad_pcb")
    board = pcbnew.LoadBoard(PCB)
    g = Grid(board)
    print("removed vias with clearance errors:", remove_bad_vias(board, drc(board)))
    print("GND island vias:", fix_islands(board, g))
    in1 = in1_mask(board, g)
    print("GND pad island escapes:", fix_pad_islands(board, g, in1))
    best = plain_rounds(board, g, in1)
    print("after plain routing:", best, "unconnected")
    # transactional rip-up: keep a rip-up only if the total number of open connections goes down
    for attempt in range(25):
        if best == 0:
            break
        board.Save(tmp)
        pairs = unconnected(drc(board))
        improved = False
        for pr in pairs:
            for side, rip in (("a", 0.6), ("b", 0.6), ("a", 1.2), ("b", 1.2), ("ab", 0.8), ("ab", 1.6)):
                name, n = route_pair(board, g, pr, in1, rip=rip, side=side)
                count = plain_rounds(board, g, in1) if n else 10 ** 6
                if count < best:
                    print(f"  rip-up for {name} ({side} window {rip} mm): {best} -> {count} unconnected")
                    best = count; board.Save(tmp); improved = True
                    break
                board = pcbnew.LoadBoard(tmp)            # undo
            if improved:
                break
        if not improved:
            print("no rip-up improves further")
            break
    print("GND island vias:", fix_islands(board, g))
    for _ in range(6):                                  # trim dangling stubs, only if nothing opens up
        before = score(drc(board)); board.Save(tmp)
        if not remove_bad_tracks(board, drc(board), kinds=("[track_dangling]",)):
            break
        if score(drc(board)) > before:
            board = pcbnew.LoadBoard(tmp)
            break
    rep = drc(board)
    board.Save(PCB)
    if os.path.exists(tmp):
        os.remove(tmp)
    print(rep[rep.index("** Found"):][:200] if "** Found" in rep else rep[-200:])


if __name__ == "__main__":
    main()
