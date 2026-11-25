#!/usr/bin/env python3
"""Autoroute squeeze.kicad_pcb with Freerouting (Specctra DSN in, SES out), then finish with route.py.

    python3 squeeze/hardware/tools/gen_pcb.py
    python3 squeeze/hardware/tools/autoroute.py --jar /path/to/freerouting-1.9.0.jar --passes 60   # Java 17+
    python3 squeeze/hardware/tools/route.py        # only if anything is left unconnected

Power and Qi AC nets get a wider net class (same widths as route.py's WIDE). The keep-outs over the
LED tab's necks are added as rule areas so Freerouting sees them too.
"""
import argparse
import os
import re
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
from route import WIDE  # noqa: E402

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "squeeze.kicad_pcb")
WORK = os.path.join(HW, "kicad", "route")


def mm(v):
    return int(round(v * 1e6))


def netclasses(board):
    ds = board.GetDesignSettings()
    ns = ds.m_NetSettings
    made = {}
    for name, w in WIDE.items():
        key = f"W{int(round(w * 100)):02d}"
        if key not in made:
            nc = pcbnew.NETCLASS(key)
            nc.SetTrackWidth(mm(w)); nc.SetClearance(mm(0.15)); nc.SetViaDiameter(mm(0.6)); nc.SetViaDrill(mm(0.3))
            ns.m_NetClasses[key] = nc
            made[key] = nc
        net = board.FindNet(name)
        if net:
            net.SetNetClass(made[key])
            ns.m_NetClassPatternAssignments.append((pcbnew.EDA_COMBINED_MATCHER(name, pcbnew.CTX_NETCLASS), key)) \
                if hasattr(pcbnew, "EDA_COMBINED_MATCHER") else None


def neck_keepouts(board):
    for x0, x1 in ((-3.0, -1.4), (1.4, 3.0)):
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True); z.SetDoNotAllowCopperPour(False)
        z.SetDoNotAllowPads(False); z.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET(); [ls.AddLayer(l) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)]
        z.SetLayerSet(ls)
        ol = z.Outline(); ol.NewOutline()
        for x, y in ((x0, -18.2), (x1, -18.2), (x1, -15.6), (x0, -15.6)):
            ol.Append(mm(100 + x), mm(100 + y))
        board.Add(z)


def import_ses(board, path):
    """Add the autorouter's wires and vias (KiCad 7's ImportSpecctraSES only works inside the GUI)."""
    import sexp
    ses = sexp.parse(open(path).read())
    routes = sexp.find(ses, "routes")[0]
    res = sexp.find(routes, "resolution")[0]
    scale = {"um": 1e-3, "mm": 1.0, "mil": 0.0254, "inch": 25.4}[res[1]] / float(res[2])   # -> mm
    xy = lambda x, y: pcbnew.VECTOR2I(pcbnew.FromMM(float(x) * scale), pcbnew.FromMM(-float(y) * scale))  # noqa: E731
    layers = {board.GetLayerName(l): l for l in range(pcbnew.PCB_LAYER_ID_COUNT)}
    stacks = {}
    for lib in sexp.find(routes, "library_out"):
        for ps in sexp.find(lib, "padstack"):
            m = re.search(r"_(\d+):(\d+)_um", ps[1])
            if m: stacks[ps[1]] = (int(m.group(1)) / 1000, int(m.group(2)) / 1000)
    n_w = n_v = 0
    for net in sexp.find(sexp.find(routes, "network_out")[0], "net"):
        kn = board.FindNet(net[1])
        for w in sexp.find(net, "wire"):
            if sexp.find(w, "type"):                  # protected: the hand-routed copper already on the board
                continue
            path = sexp.find(w, "path")[0]
            lay, width, pts = layers[path[1]], float(path[2]) * scale, path[3:]
            for i in range(0, len(pts) - 2, 2):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(xy(pts[i], pts[i + 1])); t.SetEnd(xy(pts[i + 2], pts[i + 3]))
                t.SetWidth(pcbnew.FromMM(width)); t.SetLayer(lay); t.SetNet(kn)
                board.Add(t); n_w += 1
        for v in sexp.find(net, "via"):
            if sexp.find(v, "type"):
                continue
            dia, drill = stacks.get(v[1], (0.6, 0.3))
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(xy(v[2], v[3])); via.SetWidth(pcbnew.FromMM(dia)); via.SetDrill(pcbnew.FromMM(drill))
            via.SetNet(kn)
            board.Add(via); n_v += 1
    print(f"imported {n_w} track segments, {n_v} vias")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar")
    ap.add_argument("--passes", default="100")
    ap.add_argument("--import-only", action="store_true", help="skip routing, import route/squeeze.ses")
    a = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    dsn, ses = os.path.join(WORK, "squeeze.dsn"), os.path.join(WORK, "squeeze.ses")
    if a.import_only:
        board = pcbnew.LoadBoard(PCB)
        import_ses(board, ses)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.Save(PCB)
        print("routed board saved", flush=True)
        return
    board = pcbnew.LoadBoard(PCB)
    netclasses(board)
    neck_keepouts(board)
    board.Save(PCB)
    board = pcbnew.LoadBoard(PCB)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit("DSN export failed")
    print("DSN written; running Freerouting ...", flush=True)
    # Freerouting keeps its settings in /tmp/freerouting/freerouting.json: set "allow_telemetry": false and
    # "disable_analytics": true there before the first run (it reports usage otherwise). Freerouting 2.1 takes the
    # pass limit from that file too (router.max_passes; -mp is ignored): 60 is plenty here
    if "-2." in os.path.basename(a.jar):
        cmd = ["java", "-Djava.awt.headless=true", "-jar", a.jar, "-de", dsn, "-do", ses, "-mp", a.passes,
               "--gui.enabled=false"]
    else:   # 1.9.0 (used for rev A) opens a window even in batch mode: give it a virtual display
        cmd = ["xvfb-run", "-a", "java", "-jar", a.jar, "-de", dsn, "-do", ses, "-mp", a.passes]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-1500:])
    if not os.path.exists(ses):
        sys.exit("no SES produced")
    board = pcbnew.LoadBoard(PCB)
    import_ses(board, ses)       # KiCad 7's ImportSpecctraSES only works inside the GUI (brim route.py)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    print("routed board saved", flush=True)


if __name__ == "__main__":
    main()
