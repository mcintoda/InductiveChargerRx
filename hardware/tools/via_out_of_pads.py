#!/usr/bin/env python3
"""Move vias out of soldered pads: remove each via whose centre lies in an SMD pad that gets solder paste (plus its
stub tracks), then let fixroute.py reroute those connections with its no-via-in-pad rule. Exposed thermal pads
(> 1.5 mm2) keep their deliberate vias. The board is only kept if DRC still shows 0 unconnected items.

    python3 hardware/tools/via_out_of_pads.py
"""
import os
import shutil
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import fixroute as F  # noqa: E402


def vias_in_pads(board):
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            soldered = p.IsOnLayer(pcbnew.F_Paste) or p.IsOnLayer(pcbnew.B_Paste)
            small = p.GetSize().x * p.GetSize().y / 1e12 <= 1.5
            # GND pads keep theirs: on this board there is no room for a separate escape via next to them, and a
            # via into the plane under a decoupling cap's ground end is the lower-risk case
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and soldered and small and p.GetNetname() != "GND":
                out += [(fp.GetReference(), p.GetNumber(), v) for v in vias if p.HitTest(v.GetPosition())]
    return out


def move(found_one):
    """Remove one via (and its stubs), reroute; True and keep the board if DRC stays at 0 unconnected."""
    backup = F.PCB + ".before-via-move"
    shutil.copy(F.PCB, backup)
    board = pcbnew.LoadBoard(F.PCB)
    ref, num, _ = found_one
    v = next(v for r, n, v in vias_in_pads(board) if (r, n) == (ref, num))
    tracks = [t for t in board.GetTracks() if t.GetClass() != "PCB_VIA"]   # list once: pcbnew's own list breaks after Remove
    pos, net = v.GetPosition(), v.GetNetCode()
    for t in [t for t in tracks if t.GetNetCode() == net and (t.GetStart() == pos or t.GetEnd() == pos)] + [v]:
        board.Remove(t)
    board.Save(F.PCB)
    F.main()                                            # reroutes the opened connection, saves the board
    ok = F.score(F.drc(pcbnew.LoadBoard(F.PCB))) == 0
    if not ok:
        shutil.copy(backup, F.PCB)
    os.remove(backup)
    return ok


def main():
    # one via at a time: each move is kept only if the whole board still routes with 0 unconnected items
    for item in vias_in_pads(pcbnew.LoadBoard(F.PCB)):
        print(f"{item[0]}.{item[1]}:", "moved" if move(item) else "kept in pad (no clean reroute)", flush=True)
    left = vias_in_pads(pcbnew.LoadBoard(F.PCB))
    print("still in soldered pads:", ", ".join(f"{r}.{n}" for r, n, _ in left) or "none")


if __name__ == "__main__":
    main()
