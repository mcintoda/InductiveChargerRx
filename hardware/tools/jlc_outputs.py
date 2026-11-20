#!/usr/bin/env python3
"""JLCPCB fabrication + assembly outputs.

    python3 hardware/tools/jlc_outputs.py [outdir]     (default: hardware/fab)

Writes: gerbers/ (+ drill), bath_monitor-gerbers.zip, bom_jlc.csv (with LCSC numbers from
hardware/lcsc_parts.csv) and cpl_jlc.csv (bottom-side placement).  All parts are on the BOTTOM.
Not placed by JLC: electrodes / shield tap (copper only), test pads, the battery and the Qi coil
(hand-soldered).
JLC rotations: KiCad and JLC sometimes disagree by 90/180 deg per footprint. Check the 3-D/placement
preview on the JLC order page and correct ROT_FIX below if a part shows rotated.
"""
import csv
import os
import shutil
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import gen_schematic as S  # noqa: E402

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "bath_monitor.kicad_pcb")
# Level-sensing build variant (docs/sensing-options.md). Default: FDC1004.
#   fdc    FDC1004 on PAD1/5/6/REF + shield; PAD2-4 stay on touch (PAD2 = deep-sleep wake)
#   touch  ESP32-S3 touch on all pads, no FDC1004
#   both   everything fitted (bench comparison board)
VARIANTS = {
    "fdc": ("R11", "R15", "R16", "R17", "R20"),
    "touch": ("U5", "C24", "C25", "R22", "R23", "R24", "R25", "R26"),
    "both": (),
}
_args = [a for a in sys.argv[1:] if not a.startswith("--variant=")]
VARIANT = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--variant=")), "fdc")
if VARIANT not in VARIANTS:
    sys.exit(f"unknown variant {VARIANT}: use one of {', '.join(VARIANTS)}")
DNP = set(VARIANTS[VARIANT])
OUT = _args[0] if _args else os.path.join(HW, "fab")
OX, OY = 100.0, 50.0
NOT_PLACED = ("E", "TP", "J1", "L1", "#")
ROT_FIX = {}          # e.g. {"SOT-23": 180} after checking the JLC preview
LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,Edge.Cuts"


def lcsc_map():
    with open(os.path.join(HW, "lcsc_parts.csv")) as f:
        return {r["comment"]: r for r in csv.DictReader(f)}


def main():
    os.makedirs(OUT, exist_ok=True)
    gdir = os.path.join(OUT, "gerbers")
    shutil.rmtree(gdir, ignore_errors=True); os.makedirs(gdir)
    subprocess.run(["kicad-cli", "pcb", "export", "gerbers", "--layers", LAYERS, "--subtract-soldermask",
                    "--no-x2", "-o", gdir + "/", PCB], check=True, capture_output=True)
    subprocess.run(["kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
                    "--generate-map", "--map-format", "gerberx2", "-o", gdir + "/", PCB], check=True, capture_output=True)
    shutil.make_archive(os.path.join(OUT, "bath_monitor-gerbers"), "zip", gdir)

    board = pcbnew.LoadBoard(PCB)
    parts = lcsc_map()
    groups, cpl, missing = {}, [], set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith(NOT_PLACED) or ref in DNP:
            continue
        part = next((p for p in S.PARTS if p["ref"] == ref), {"fields": {}})
        rating = part["fields"].get("Rating", "")
        val = fp.GetValue()
        comment = f"{val} {rating}".strip() if rating else val
        lib = fp.GetFPID().GetLibItemName().wx_str() if hasattr(fp.GetFPID().GetLibItemName(), "wx_str") else str(fp.GetFPID().GetLibItemName())
        groups.setdefault((comment, lib), []).append(ref)
        if comment not in parts or not parts[comment]["lcsc"]:
            missing.add(comment)
    key = lambda r: (r.rstrip("0123456789"), int("".join(c for c in r if c.isdigit()) or 0))  # noqa: E731
    with open(os.path.join(OUT, "bom_jlc.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Status"])
        for (c, lib), refs in sorted(groups.items(), key=lambda g: key(sorted(g[1], key=key)[0])):
            r = parts.get(c, {})
            w.writerow([c, ",".join(sorted(refs, key=key)), lib, r.get("lcsc", ""), r.get("status", "missing")])
    # placement from KiCad's own position export (same origin as the gerbers)
    pos_file = os.path.join(OUT, "pos.csv")
    subprocess.run(["kicad-cli", "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
                    "-o", pos_file, PCB], check=True, capture_output=True)
    with open(pos_file) as f:
        for r in csv.DictReader(f):
            if r["Ref"].startswith(NOT_PLACED) or r["Ref"] in DNP:
                continue
            rot = (float(r["Rot"]) + ROT_FIX.get(r["Package"], 0)) % 360
            cpl.append([r["Ref"], f'{float(r["PosX"]):.3f}mm', f'{float(r["PosY"]):.3f}mm',
                        "Bottom" if r["Side"] == "bottom" else "Top", f"{rot:.1f}"])
    os.remove(pos_file)
    with open(os.path.join(OUT, "cpl_jlc.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(sorted(cpl, key=lambda r: key(r[0])))
    print(f"variant {VARIANT} (not fitted: {', '.join(sorted(DNP, key=key)) or 'none'})")
    print(f"gerbers: {len(os.listdir(gdir))} files -> {os.path.relpath(OUT, HW)}; BOM lines {len(groups)}, "
          f"placed parts {len(cpl)}; LCSC still to choose: {sorted(missing) or 'none'}")


if __name__ == "__main__":
    main()
