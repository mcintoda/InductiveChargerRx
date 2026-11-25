#!/usr/bin/env python3
"""DRC summary for squeeze.kicad_pcb (KiCad 7 has no `kicad-cli pcb drc`).

    python3 squeeze/hardware/tools/drc.py [--list kind ...]
"""
import collections
import os
import re
import sys

import pcbnew

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "squeeze.kicad_pcb")
RPT = os.path.join(HW, "kicad", "drc.rpt")


def run(path=PCB, rpt=RPT):
    b = pcbnew.LoadBoard(path)
    pcbnew.WriteDRCReport(b, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    txt = open(rpt).read()
    kinds = collections.Counter(re.findall(r"^\[(\w+)\]", txt, re.M))
    m = re.search(r"Found (\d+) unconnected pads", txt)
    return kinds, int(m.group(1)) if m else 0, txt


if __name__ == "__main__":
    kinds, unc, txt = run()
    print("unconnected:", unc, dict(kinds))
    want = sys.argv[2:] if len(sys.argv) > 2 and sys.argv[1] == "--list" else []
    for block in re.split(r"\n(?=\[)", txt):
        k = re.match(r"\[(\w+)\]", block)
        if k and k.group(1) in want:
            print(block.strip()[:400]); print("--")
