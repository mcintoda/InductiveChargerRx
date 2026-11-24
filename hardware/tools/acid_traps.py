#!/usr/bin/env python3
"""Find acid traps: notches in the copper outline narrower than 90 degrees.

For each net and copper layer, the copper is the union of its tracks (round-ended), vias, pads and zone
fill. A notch is a concave vertex of that outline; it traps etchant when its open angle is under 90 deg.
Only notches within a track width of a track are reported (zone-fill corners are KiCad's).

    acid_traps.py BOARD [--min-deg 90] [--list]
"""
import math, sys
from collections import defaultdict
import pcbnew
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

MM = 1e6


def sps_to_shapely(sps):
    polys = []
    for i in range(sps.OutlineCount()):
        o = sps.Outline(i)
        pts = [(o.CPoint(j).x / MM, o.CPoint(j).y / MM) for j in range(o.PointCount())]
        holes = []
        for h in range(sps.HoleCount(i)):
            hh = sps.Hole(i, h)
            holes.append([(hh.CPoint(j).x / MM, hh.CPoint(j).y / MM) for j in range(hh.PointCount())])
        if len(pts) >= 3:
            polys.append(Polygon(pts, holes).buffer(0))
    return polys


def copper(board):
    """{(netname, layer): (union polygon, [track LineStrings with width])}"""
    shapes = defaultdict(list); tracks = defaultdict(list)
    cu = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    for t in board.GetTracks():
        n = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            for l in cu:
                shapes[(n, l)].append(Point(p.x / MM, p.y / MM).buffer(t.GetWidth() / MM / 2, 16))
        elif t.GetClass() == "PCB_TRACK":
            a, e = t.GetStart(), t.GetEnd()
            ls = LineString([(a.x / MM, a.y / MM), (e.x / MM, e.y / MM)]) if (a.x, a.y) != (e.x, e.y) else Point(a.x / MM, a.y / MM)
            shapes[(n, t.GetLayer())].append(ls.buffer(t.GetWidth() / MM / 2, 16))
            if isinstance(ls, LineString):
                tracks[(n, t.GetLayer())].append((ls, t.GetWidth() / MM))
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            for l in cu:
                if pd.IsOnLayer(l):
                    sps = pcbnew.SHAPE_POLY_SET()
                    pd.TransformShapeToPolygon(sps, l, 0, 2000)
                    shapes[(pd.GetNetname(), l)] += sps_to_shapely(sps)
    for z in board.Zones():
        for l in cu:
            if z.IsOnLayer(l) and z.IsFilled():
                shapes[(z.GetNetname(), l)] += sps_to_shapely(z.GetFilledPolysList(l))
    # a 1 um closing merges edges that coincide exactly (e.g. a track edge lying on a pad edge)
    return {k: (unary_union(v).buffer(0.001, 4).buffer(-0.001, 4), tracks.get(k, [])) for k, v in shapes.items() if tracks.get(k)}


def notches(geom, min_deg):
    out = []
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    for poly in polys:
        poly = poly.simplify(0.004)
        rings = [poly.exterior] + list(poly.interiors)
        for ri, ring in enumerate(rings):
            pts = list(ring.coords)[:-1]
            if len(pts) < 3:
                continue
            ccw = ring.is_ccw
            # copper on the left of a CCW exterior; holes are CW in shapely, copper still on the left
            for i in range(len(pts)):
                p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
                d1 = (p1[0] - p0[0], p1[1] - p0[1]); d2 = (p2[0] - p1[0], p2[1] - p1[1])
                cross = d1[0] * d2[1] - d1[1] * d2[0]
                n1, n2 = math.hypot(*d1), math.hypot(*d2)
                if n1 == 0 or n2 == 0:
                    continue
                turn = math.degrees(math.atan2(cross, d1[0] * d2[0] + d1[1] * d2[1]))
                concave = (turn < 0) if (ccw if ri == 0 else ccw) else (turn > 0)
                if concave and 180 - abs(turn) < min_deg - 0.5:
                    out.append((p1, 180 - abs(turn), (-d1[0] / n1, -d1[1] / n1), (d2[0] / n2, d2[1] / n2)))
    return out


def find(board, min_deg=90.0):
    res = []
    for (net, layer), (geom, trs) in copper(board).items():
        for p, ang, da, db in notches(geom, min_deg):
            P = Point(p)
            near = [w for ls, w in trs if ls.distance(P) <= w * 0.75]
            if near:
                res.append((net, board.GetLayerName(layer), round(p[0], 4), round(p[1], 4), round(ang, 1), da, db, min(near)))
    return res


if __name__ == "__main__":
    b = pcbnew.LoadBoard(sys.argv[1])
    md = float(sys.argv[sys.argv.index("--min-deg") + 1]) if "--min-deg" in sys.argv else 90.0
    r = find(b, md)
    print(f"acid traps (< {md:g} deg): {len(r)}")
    if "--list" in sys.argv:
        for x in r:
            print("  ", x[:5])
