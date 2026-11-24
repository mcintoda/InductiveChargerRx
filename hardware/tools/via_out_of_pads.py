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
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and soldered and small:
                out += [(fp.GetReference(), p.GetNumber(), v) for v in vias if p.HitTest(v.GetPosition())]
    return out


def main():
    backup = F.PCB + ".before-via-move"
    shutil.copy(F.PCB, backup)
    board = pcbnew.LoadBoard(F.PCB)
    found = vias_in_pads(board)
    print("vias in soldered pads:", ", ".join(f"{r}.{n}" for r, n, _ in found) or "none")
    tracks = [t for t in board.GetTracks() if t.GetClass() != "PCB_VIA"]   # list once: pcbnew's own list breaks after Remove
    doomed = []
    for _, _, v in found:
        pos, net = v.GetPosition(), v.GetNetCode()
        doomed += [t for t in tracks if t.GetNetCode() == net and (t.GetStart() == pos or t.GetEnd() == pos)]
        doomed.append(v)
    seen = set()
    for item in doomed:
        key = item.m_Uuid.AsString()
        if key not in seen:
            seen.add(key)
            board.Remove(item)
    board.Save(F.PCB)
    F.main()                                            # reroutes the opened connections, saves the board
    board = pcbnew.LoadBoard(F.PCB)
    left, rep = vias_in_pads(board), F.drc(board)
    if F.score(rep) or left:
        shutil.copy(backup, F.PCB)
        print("NOT kept:", F.score(rep), "unconnected,", len(left), "vias still in pads; board restored")
    else:
        print("kept: 0 unconnected, no vias in soldered pads")
    os.remove(backup)


if __name__ == "__main__":
    main()
