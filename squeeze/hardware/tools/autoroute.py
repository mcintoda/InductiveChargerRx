#!/usr/bin/env python3
"""Autoroute squeeze.kicad_pcb with Freerouting (Specctra DSN in, SES out), then finish with route.py.

    python3 squeeze/hardware/tools/gen_pcb.py
    python3 squeeze/hardware/tools/autoroute.py --jar /path/to/freerouting-2.1.0.jar   # Java 21
    python3 squeeze/hardware/tools/route.py        # only if anything is left unconnected

Power and Qi AC nets get a wider net class (same widths as route.py's WIDE). The keep-outs over the
LED tab's necks are added as rule areas so Freerouting sees them too.
"""
import argparse
import os
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--passes", default="100")
    a = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    dsn, ses = os.path.join(WORK, "squeeze.dsn"), os.path.join(WORK, "squeeze.ses")
    board = pcbnew.LoadBoard(PCB)
    netclasses(board)
    neck_keepouts(board)
    board.Save(PCB)
    board = pcbnew.LoadBoard(PCB)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit("DSN export failed")
    print("DSN written; running Freerouting ...", flush=True)
    # Freerouting keeps its settings in /tmp/freerouting/freerouting.json: set "allow_telemetry": false and
    # "disable_analytics": true there before the first run (it reports usage otherwise)
    r = subprocess.run(["java", "-Djava.awt.headless=true", "-jar", a.jar, "-de", dsn, "-do", ses, "-mp", a.passes,
                        "--gui.enabled=false"], capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-1500:])
    if not os.path.exists(ses):
        sys.exit("no SES produced")
    board = pcbnew.LoadBoard(PCB)
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit("SES import failed")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    print("routed board saved", flush=True)


if __name__ == "__main__":
    main()
