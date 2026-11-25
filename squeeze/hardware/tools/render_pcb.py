#!/usr/bin/env python3
"""Board pictures for the docs: docs/img/pcb_layers.png (F.Cu + silk, In2, B.Cu) via kicad-cli SVG export.

    python3 squeeze/hardware/tools/render_pcb.py
"""
import os
import subprocess
import tempfile

import cairosvg
import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "squeeze.kicad_pcb")
IMG = os.path.join(HW, "..", "docs", "img", "pcb_layers.png")
VIEWS = [("Top: F.Cu, silkscreen", "F.Cu,F.SilkS,F.Mask,Edge.Cuts"), ("In2.Cu (signals)", "In2.Cu,Edge.Cuts"),
         ("Bottom: B.Cu (seen through the board)", "B.Cu,Edge.Cuts")]

with tempfile.TemporaryDirectory() as tmp:
    fig, axs = plt.subplots(1, 3, figsize=(15, 6))
    for ax, (title, layers) in zip(axs, VIEWS):
        svg = os.path.join(tmp, "v.svg"); png = os.path.join(tmp, "v.png")
        subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", layers, "--exclude-drawing-sheet",
                        "--page-size-mode", "2", "-o", svg, PCB], check=True, capture_output=True)
        cairosvg.svg2png(url=svg, write_to=png, output_width=900, background_color="white")
        ax.imshow(mpimg.imread(png)); ax.set_axis_off(); ax.set_title(title, fontsize=10)
    fig.tight_layout(); fig.savefig(IMG, dpi=110); plt.close(fig)
print("wrote", os.path.relpath(IMG))
