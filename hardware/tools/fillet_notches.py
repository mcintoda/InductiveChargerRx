#!/usr/bin/env python3
"""Fill acid traps (copper notches under 90 deg) with a short fillet track across the notch mouth.

Each fillet runs from just inside the copper on one side of the notch to just inside the other, close
enough to the apex that its copper covers it. The new outline meets each side at 90 + angle/2 degrees,
so no acute notch is left. Existing tracks are not moved; DRC decides which fillets stay.

    fillet_notches.py BOARD          fillet in place: up to 4 passes, DRC after each; a fillet that causes a
                                     violation is removed and its notch reported for a hand fix
"""
import json, math, sys, os
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acid_traps

DELTA = 0.03     # mm the fillet ends sit inside the copper
WIDTHS = (0.2, 0.15)   # fillet width tried first, then after a DRC failure (0.15 = board minimum track)


def one_pass(src, dst, skip, log):
    b = pcbnew.LoadBoard(src)
    nets = b.GetNetsByName()
    added = 0
    for net, lay, x, y, ang, da, db, w in acid_traps.find(b):
        key = (net, lay, round(x, 2), round(y, 2))
        tries = skip.get(key, 0)
        if tries >= len(WIDTHS) or ang < 2.0:
            continue
        th = math.radians(ang)
        wf = min(WIDTHS[tries], w)
        m = (da[0] + db[0], da[1] + db[1]); ml = math.hypot(*m)
        m = (m[0] / ml, m[1] / ml)
        def inward(d):              # normal to d pointing away from the open wedge (into copper)
            n = (-d[1], d[0])
            return n if n[0] * m[0] + n[1] * m[1] < 0 else (d[1], -d[0])
        r = 0.85 * (wf / 2) / math.cos(th / 2) + DELTA * math.tan(th / 2)
        na, nb = inward(da), inward(db)
        A = (x + da[0] * r + na[0] * DELTA, y + da[1] * r + na[1] * DELTA)
        B = (x + db[0] * r + nb[0] * DELTA, y + db[1] * r + nb[1] * DELTA)
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(A[0]), pcbnew.FromMM(A[1])))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(B[0]), pcbnew.FromMM(B[1])))
        t.SetWidth(pcbnew.FromMM(wf)); t.SetLayer(b.GetLayerID(lay)); t.SetNet(nets[net])
        b.Add(t); added += 1
        log.append({"key": key, "a": A, "b": B, "net": net, "layer": lay, "len": math.dist(A, B)})
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(dst, b)
    return added


def offenders(report, log):
    import re
    bad = set()
    for blk in re.split(r"\n(?=\[)", report):
        if not re.match(r"\[(clearance|hole_clearance|shorting_items|tracks_crossing|solder_mask_bridge|unconnected_items|track_dangling|copper_edge_clearance)\]", blk):
            continue
        for x, y, net, lay, L in re.findall(r"@\(([\d.]+) mm, ([\d.]+) mm\): Track \[([^\]]+)\] on ([A-Za-z0-9_.]+), length ([\d.]+) mm", blk):
            for f in log:
                if f["net"] == net and f["layer"] == lay and abs(f["len"] - float(L)) < 0.002:
                    a, b = f["a"], f["b"]
                    t = max(0, min(1, ((float(x) - a[0]) * (b[0] - a[0]) + (float(y) - a[1]) * (b[1] - a[1])) / max(1e-12, f["len"] ** 2)))
                    if math.dist((float(x), float(y)), (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))) < 0.05:
                        bad.add(f["key"])
    return bad


def drc_text(board):
    import subprocess, tempfile
    rpt = tempfile.mktemp(suffix=".rpt")
    subprocess.run([sys.executable, "-c", "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "pcbnew.WriteDRCReport(b, sys.argv[2], pcbnew.EDA_UNITS_MILLIMETRES, True)", board, rpt],
                   check=True, capture_output=True)
    t = open(rpt).read(); os.remove(rpt)
    return t


def main():
    import shutil, tempfile
    board = sys.argv[1]
    tmp = tempfile.mkdtemp()
    skip = {}
    for attempt in range(10):
        log = []; cur = board
        for k in range(4):
            out = os.path.join(tmp, f"p{k}.kicad_pcb")
            n = one_pass(cur, out, skip, log); cur = out
            if n == 0:
                break
        bad = offenders(drc_text(cur), log)
        print(f"attempt {attempt}: {len(log)} fillets, {len(bad)} cause DRC errors")
        if not bad:
            break
        for k in bad:
            skip[k] = skip.get(k, 0) + 1
    shutil.copy(cur, board)
    left = acid_traps.find(pcbnew.LoadBoard(board))
    print(json.dumps({"fillets": len(log), "notches_left": [x[:5] for x in left]}))


if __name__ == "__main__":
    main()
