#!/usr/bin/env python3
"""Rev C hand fixes for the last acute notches the automatic passes could not reach.

Pipeline (from the routed board): tidy_board.py -> hand_fixes_revC.py -> fillet_notches.py
    hand_fixes_revC.py kicad/bath_monitor.kicad_pcb
Each fix deletes the listed track segments (matched by end points, 5 um, against tidy_board.py's output,
which is deterministic) and adds the replacements. It stops if a segment is missing.
"""
import math, sys
import pcbnew

FIXES = [
    # +3V3: U7 pad 10 -> pad 9 was a dog-leg with slanted pad exits -> straight, square in and out
    # (the old exit towards (127.4, 76.6) ended inside pad 9 after tidy pruned its dead end)
    ("+3V3", "B.Cu", "segs",
     [((127.2375, 76.15), (127.209057, 76.301698)), ((127.209057, 76.301698), (127.25, 76.45)),
      ((127.25, 76.45), (127.4, 76.6)), ((127.212308, 75.948462), (127.2375, 76.15)),
      ((127.212308, 75.948462), (127.25, 75.8))],
     [((127.25, 75.8), (127.25, 76.15)), ((127.2375, 76.15), (127.2375, 76.65))]),
    # +3V3: router cluster between U7 pads 2/3 and the via at (129.35, 77.05) -> pad 2 to pad 3 straight,
    # square exit right into the via, and the two runs that leave the via (down, and down-right to C28)
    ("+3V3", "B.Cu", "segs",
     [((128.9, 77.1), (129.05, 77.15)), ((129.15, 77.2), (129.25, 77.25)), ((128.9, 77.1), (129.0, 77.05)),
      ((129.0, 77.05), (129.15, 77.2)), ((129.0, 77.05), (129.35, 77.05)), ((129.25, 77.25), (129.35, 77.35)),
      ((128.7, 76.8), (128.9, 77.1)), ((128.9, 77.0), (129.05, 77.15)), ((128.7, 76.8), (128.7, 76.95)),
      ((129.25, 77.25), (129.25, 77.85))],
     [((128.7625, 76.65), (128.7625, 77.15)), ((128.7625, 77.15), (129.25, 77.15)), ((129.25, 77.15), (129.25, 77.85)),
      ((129.25, 77.15), (129.35, 77.05)), ((129.35, 77.05), (129.35, 77.35))]),
    # ILIM: 45 deg entry into U2 pad 12 -> come up square into the pad's lower edge
    ("ILIM", "B.Cu", "segs", [((103.464, 64.836), (103.95, 64.35))],
     [((103.464, 64.836), (103.80, 64.70)), ((103.80, 64.70), (103.80, 64.35))]),
    # FDC_CIN2: slanted entry into U5 pad 3's end -> short horizontal run into the pad (squeezed between CIN1/CIN3)
    ("FDC_CIN2", "B.Cu", "segs", [((126.255, 83.8567), (128.25, 82.05))],
     [((126.255, 83.8567), (128.10, 82.1859)), ((128.10, 82.1859), (128.19, 81.975)), ((128.19, 81.975), (128.45, 81.975))]),
    # ACC_INT: via -> U7 pad 12 slightly slanted -> vertical
    ("ACC_INT", "B.Cu", "segs", [((128.25, 75.95), (128.3, 75.4))],
     [((128.30, 76.00), (128.30, 75.40))]),
]


def near(p, q, tol=0.005):
    return math.dist(p, q) <= tol


def main():
    f = sys.argv[1]
    b = pcbnew.LoadBoard(f)
    nets = b.GetNetsByName()
    tracks = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
    # read every end point before touching the board: SWIG proxies go stale after a Remove()
    info = {id(t): (t.GetNetname(), t.GetLayer(), t.GetWidth(),
                    ((t.GetStart().x / 1e6, t.GetStart().y / 1e6), (t.GetEnd().x / 1e6, t.GetEnd().y / 1e6))) for t in tracks}
    for net, lay, kind, sel, new in FIXES:
        L = b.GetLayerID(lay)
        mine = [t for t in tracks if info[id(t)][0] == net and info[id(t)][1] == L]
        ends = lambda t: info[id(t)][3]
        if kind == "box":
            x0, y0, x1, y1 = sel
            inb = lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1
            gone = [t for t in mine if inb(ends(t)[0]) or inb(ends(t)[1])]
        else:
            gone = [t for t in mine if any((near(ends(t)[0], a) and near(ends(t)[1], e)) or (near(ends(t)[0], e) and near(ends(t)[1], a)) for a, e in sel)]
            if len(gone) != len(sel):
                sys.exit(f"{net}: expected {len(sel)} segments, found {len(gone)}; board changed, review the fix")
        w = max(info[id(t)][2] for t in gone)
        for t in gone:
            b.Remove(t); tracks.remove(t)
        for a, e in new:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(e[0]), pcbnew.FromMM(e[1])))
            t.SetWidth(w); t.SetLayer(L); t.SetNet(nets[net]); b.Add(t)
        print(f"{net} {lay}: -{len(gone)} +{len(new)}")
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(f, b)


if __name__ == "__main__":
    main()
