#!/usr/bin/env python3
"""Placement picture: outline, courtyards, pads, references -> /tmp-free path given as argv[1]."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pcbnew
from gen_pcb import OUT, OX, OY

b = pcbnew.LoadBoard(OUT)
fig, ax = plt.subplots(figsize=(11, 10))
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        ax.plot([d.GetStart().x / 1e6 - OX, d.GetEnd().x / 1e6 - OX], [d.GetStart().y / 1e6 - OY, d.GetEnd().y / 1e6 - OY], "k-", lw=0.8)
for fp in b.GetFootprints():
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)
    x0, y0 = bb.GetX() / 1e6 - OX, bb.GetY() / 1e6 - OY
    ax.add_patch(plt.Rectangle((x0, y0), bb.GetWidth() / 1e6, bb.GetHeight() / 1e6, fill=False, ec="#c33", lw=0.5))
    for p in fp.Pads():
        pb = p.GetBoundingBox()
        ax.add_patch(plt.Rectangle((pb.GetX() / 1e6 - OX, pb.GetY() / 1e6 - OY), pb.GetWidth() / 1e6, pb.GetHeight() / 1e6,
                                   color="#d9a400" if p.GetNetname() != "GND" else "#888", lw=0))
    ax.text(fp.GetPosition().x / 1e6 - OX, fp.GetPosition().y / 1e6 - OY, fp.GetReference(), fontsize=6, ha="center", va="center", color="b")
ax.set_aspect("equal"); ax.invert_yaxis(); ax.grid(True, lw=0.2); ax.set_xticks(range(-22, 23, 2)); ax.set_yticks(range(-25, 17, 2))
ax.tick_params(labelsize=6)
fig.tight_layout(); fig.savefig(sys.argv[1], dpi=110)
