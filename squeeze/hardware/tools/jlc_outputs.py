#!/usr/bin/env python3
"""JLCPCB order files for the squeeze main board.

    python3 squeeze/hardware/tools/jlc_outputs.py      -> squeeze/hardware/fab/

Writes:
  squeeze-gerbers.zip   upload at jlcpcb.com (4 layers, 1.0 mm)
  bom_jlc.csv           assembly BOM: Comment, Designator, Footprint, LCSC Part #
  cpl_jlc.csv           placement, all parts on Top
  hand_parts.csv        what JLC does not place (wired by hand)

Values and LCSC numbers come from parts.py (the source of truth); the board's footprint values
are synced from it first, so a value change never needs a re-route.
JLC rotations: KiCad and JLC sometimes disagree per package. Check the placement preview on the
order page; polarised parts to look at are listed in docs/ordering.md. Fix them with ROT_FIX.
"""
import csv
import os
import shutil
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import parts as PT  # noqa: E402

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "squeeze.kicad_pcb")
OUT = os.path.join(HW, "fab")
LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,Edge.Cuts"
ROT_FIX = {}          # footprint name -> degrees to add, after checking JLC's preview


def key(r):
    return (r.rstrip("0123456789"), int("".join(c for c in r if c.isdigit()) or 0))


def sync_values():
    board = pcbnew.LoadBoard(PCB)
    byref = {p["ref"]: p for p in PT.PARTS}
    changed = 0
    for fp in board.GetFootprints():
        p = byref.get(fp.GetReference())
        if p and fp.GetValue() != p["value"]:
            fp.SetValue(p["value"]); changed += 1
    if changed:
        board.Save(PCB)
    return changed


def main():
    print("values synced from parts.py:", sync_values())
    os.makedirs(OUT, exist_ok=True)
    gdir = os.path.join(OUT, "gerbers")
    shutil.rmtree(gdir, ignore_errors=True); os.makedirs(gdir)
    subprocess.run(["kicad-cli", "pcb", "export", "gerbers", "--layers", LAYERS, "--subtract-soldermask",
                    "--no-x2", "-o", gdir + "/", PCB], check=True, capture_output=True)
    subprocess.run(["kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
                    "--generate-map", "--map-format", "gerberx2", "-o", gdir + "/", PCB], check=True, capture_output=True)
    zipbase = os.path.join(OUT, "squeeze-gerbers")
    shutil.make_archive(zipbase, "zip", gdir)

    placed = [p for p in PT.PARTS if p["placed"]]
    groups = {}
    for p in placed:
        comment = f'{p["value"]} {p["rating"]}'.strip()
        groups.setdefault((comment, p["fp"].split(":")[1], p["lcsc"]), []).append(p["ref"])
    with open(os.path.join(OUT, "bom_jlc.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (c, fpn, lcsc), refs in sorted(groups.items(), key=lambda g: key(sorted(g[1], key=key)[0])):
            w.writerow([c, ",".join(sorted(refs, key=key)), fpn, lcsc])

    pos = os.path.join(OUT, "pos.csv")
    subprocess.run(["kicad-cli", "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
                    "-o", pos, PCB], check=True, capture_output=True)
    names = {p["ref"] for p in placed}
    cpl = []
    with open(pos) as f:
        for r in csv.DictReader(f):
            if r["Ref"] not in names:
                continue
            rot = (float(r["Rot"]) + ROT_FIX.get(r["Package"], 0)) % 360
            cpl.append([r["Ref"], f'{float(r["PosX"]):.3f}mm', f'{float(r["PosY"]):.3f}mm',
                        "Top" if r["Side"] == "top" else "Bottom", f"{rot:.1f}"])
    os.remove(pos)
    missing = names - {c[0] for c in cpl}
    with open(os.path.join(OUT, "cpl_jlc.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(sorted(cpl, key=lambda r: key(r[0])))
    with open(os.path.join(OUT, "hand_parts.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "What", "Notes"])
        for p in sorted((p for p in PT.PARTS if not p["placed"]), key=lambda p: key(p["ref"])):
            w.writerow([p["ref"], p["value"], p["note"]])
    nolcsc = sorted(c for (c, _, l), _r in groups.items() if not l)
    print(f"gerbers: {len(os.listdir(gdir))} files -> {os.path.relpath(zipbase, HW)}.zip")
    print(f"BOM lines {len(groups)}, placed parts {len(cpl)}" + (f", MISSING from CPL: {sorted(missing)}" if missing else ""))
    print(f"lines matched by JLC from the comment (no LCSC #): {len(nolcsc)}")


if __name__ == "__main__":
    main()
