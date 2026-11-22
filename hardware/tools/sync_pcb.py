#!/usr/bin/env python3
"""Bring the ROUTED board in line with the schematic generator without re-generating (and so losing) the routing.

    python3 hardware/tools/sync_pcb.py

* footprints no longer in the schematic are deleted, together with copper of nets that no longer exist
  (nets in RENAME keep their copper under the new name);
* pad nets of every footprint are set from gen_schematic's intended pin -> net map;
* footprints new in the schematic are added at their NEW_PLACE position (bottom side, front-view coordinates
  relative to the board's top-left corner, like gen_pcb.py) and left unrouted for route.py / fixroute.py.
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import gen_schematic as S  # noqa: E402

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "bath_monitor.kicad_pcb")
PROJ_LIB = os.path.join(HW, "kicad", "BathMonitor.pretty")
FPDIR = "/usr/share/kicad/footprints"
OX, OY = 100.0, 50.0
RENAME = {"LED_DRV": "ACC_INT"}           # GPIO21 keeps its escape route under the new name
# rev C additions (gen_pcb.py places them the same way): x, y (mm from the top-left corner), rotation
NEW_PLACE = {
    "D1": (35.485, 20.535, 0),            # RGB LED where the green LED was
    "C31": (32.675, 20.275, 0),           # where the LED resistor R10 was
    "U9": (35.5, 23.3, 0),
    "U8": (28.6, 23.4, 0), "C30": (31.0, 23.4, 90),
    "U7": (28.0, 26.9, 0), "C28": (30.0, 26.9, 90), "C29": (28.0, 28.85, 0),
    "BZ1": (25.3, 27.9, 90), "R31": (25.0, 24.6, 90), "R32": (26.2, 24.6, 90),
}


def mm(v):
    return int(round(v * 1e6))


def main():
    board = pcbnew.LoadBoard(PCB)
    parts = {p["ref"]: p for p in S.PARTS if not p["ref"].startswith("#")}
    want_nets = {n for p in parts.values() for n in p["nets"].values() if n}
    nets = {}

    def net(name):
        if name not in nets:
            n = board.FindNet(name)
            if n is None:
                n = pcbnew.NETINFO_ITEM(board, name); board.Add(n)
            nets[name] = n
        return nets[name]

    # 1. renamed nets: move their copper over
    for old, new in RENAME.items():
        o = board.FindNet(old)
        if o is None:
            continue
        for t in board.GetTracks():
            if t.GetNetCode() == o.GetNetCode():
                t.SetNet(net(new))
    # 2. footprints that left the schematic (or must be re-made with a new footprint)
    removed = []
    for fp in list(board.GetFootprints()):
        ref = fp.GetReference()
        if ref.startswith("#"):
            continue
        p = parts.get(ref)
        if p is None or fp.GetFPID().GetLibItemName() != p["fp"].split(":")[1]:
            removed.append(ref); board.Delete(fp)
    # 3. pad nets of the remaining footprints
    for fp in board.GetFootprints():
        p = parts.get(fp.GetReference())
        if not p:
            continue
        fp.SetValue(p["value"])
        for pad in fp.Pads():
            n = p["nets"].get(pad.GetNumber())
            if n:
                pad.SetNet(net(n))
            elif pad.GetNumber() in p["nets"]:          # explicitly unconnected in the schematic
                pad.SetNetCode(0)
            # pads the schematic does not list (e.g. the TMP117 exposed pad, tied to GND by gen_pcb) keep their net
    # 4. new footprints
    added = []
    have = {fp.GetReference() for fp in board.GetFootprints()}
    for ref, p in parts.items():
        if ref in have:
            continue
        assert ref in NEW_PLACE, f"no placement for new part {ref}"
        lib, name = p["fp"].split(":")
        fp = pcbnew.FootprintLoad(PROJ_LIB if lib == "BathMonitor" else os.path.join(FPDIR, lib + ".pretty"), name)
        assert fp, p["fp"]
        fp.SetReference(ref); fp.SetValue(p["value"])
        for pad in fp.Pads():
            n = p["nets"].get(pad.GetNumber())
            if n:
                pad.SetNet(net(n))
        board.Add(fp)
        x, y, r = NEW_PLACE[ref]
        fp.SetOrientationDegrees(r)
        fp.SetPosition(pcbnew.VECTOR2I(mm(OX + x), mm(OY + y)))
        fp.Flip(fp.GetPosition(), True)               # bottom side, mirrored left-right like gen_pcb.place()
        added.append(ref)
    # 5. copper of nets that no longer exist
    dead = 0
    for t in list(board.GetTracks()):
        name = t.GetNetname()
        if name and name not in want_nets:
            board.Delete(t); dead += 1
    board.Save(PCB)
    print("removed:", removed, "| added:", added, "| dead copper deleted:", dead)


if __name__ == "__main__":
    main()
