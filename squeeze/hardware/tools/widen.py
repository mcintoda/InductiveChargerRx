#!/usr/bin/env python3
"""Widen the power tracks after routing, wherever the copper around them allows.

Freerouting routes everything at the default width. The servo boost draws ~1 A peaks from VBAT and its
switch node carries ~2 A; the Qi AC nets carry ~0.5 A. Each track of those nets is tried at
0.5 / 0.4 / 0.3 mm and keeps the widest that stays 0.15 mm from other-net copper and 0.3 mm from
the board edge. Pads are not changed.

    python3 squeeze/hardware/tools/widen.py      (after route.py)
"""
import os
import sys

import pcbnew

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "squeeze.kicad_pcb")
POWER = {"SW": (0.5, 0.4, 0.3), "VBAT": (0.5, 0.4, 0.3), "+5V": (0.5, 0.4, 0.3), "RECT": (0.4, 0.3),
         "AC1": (0.4, 0.3), "AC2": (0.4, 0.3), "COIL_A": (0.4, 0.3), "+3V3": (0.3,), "GND": (0.4, 0.3)}
CLR, EDGE = 0.15, 0.3


def mm(v):
    return int(round(v * 1e6))


def main():
    b = pcbnew.LoadBoard(PCB)
    edge = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(edge)
    pads = [q for f in b.GetFootprints() for q in f.Pads()]
    tracks = list(b.GetTracks())
    stats = {}
    for t in tracks:
        n = t.GetNetname()
        if t.GetClass() == "PCB_VIA" or n not in POWER:
            continue
        lay = t.GetLayer()
        nc = t.GetNetCode()
        old = t.GetWidth()
        for w in POWER[n]:
            if mm(w) <= old:
                break
            seg = pcbnew.SHAPE_SEGMENT(t.GetStart(), t.GetEnd(), mm(w))
            # stay inside the board with the edge clearance
            inner = pcbnew.SHAPE_POLY_SET(edge)
            inner.Deflate(mm(EDGE + w / 2), 16)
            if not (inner.Contains(t.GetStart()) and inner.Contains(t.GetEnd())):
                continue
            hit = False
            for q in pads:
                if q.GetNetCode() != nc and q.IsOnLayer(lay) and q.GetEffectiveShape(lay).Collide(seg, mm(CLR)):
                    hit = True; break
                if q.HasHole() and q.GetNetCode() != nc and q.GetEffectiveHoleShape().Collide(seg, mm(0.25)):
                    hit = True; break
            if not hit:
                for o in tracks:
                    if o is t or o.GetNetCode() == nc:
                        continue
                    if (o.GetClass() == "PCB_VIA" or o.GetLayer() == lay) and \
                            o.GetEffectiveShape(lay).Collide(seg, mm(CLR)):
                        hit = True; break
            if not hit:
                t.SetWidth(mm(w))
                stats.setdefault(n, []).append(w)
                break
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(PCB)
    for n, ws in sorted(stats.items()):
        print(f"{n:7s} widened {len(ws)} segments (to {', '.join(f'{x:.1f}' for x in sorted(set(ws), reverse=True))} mm)")


if __name__ == "__main__":
    sys.exit(main())
