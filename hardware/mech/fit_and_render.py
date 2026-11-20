#!/usr/bin/env python3
"""Fit check (internal parts vs cup/plug) and renders for the enclosure study.

Internal parts are modelled as simple solids at their real positions:
  PCB 38 x 112 x 1.0 (top corners R5.5) pressed on the front wall,
  ESP32-S3-MINI-1 module 15.4 x 20.65 x 2.4 (KiCad outline) on the back of the PCB,
  Li-ion 403040 (30 x 40 x 4) behind the electrode band, Qi coil 30 x 1.2 behind the battery,
  1.2 mm (compressed) foam between coil and plug, and a 1.35 mm-tall envelope for all other
  back-side components (0805 is the tallest passive) across the electronics band.

    python3 hardware/mech/fit_and_render.py
"""
import os
import sys

import cadquery as cq
import matplotlib
import numpy as np
import trimesh

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
import enclosure as E  # noqa: E402

Z_PCB = E.T_FRONT
Z_BACK_PCB = Z_PCB + E.PCB_T


def pcb():
    x0, y0 = E.pcb_to_dev(0, 0)
    body = (cq.Workplane("XY").workplane(offset=Z_PCB).center(0, y0 - 51.0)
            .placeSketch(cq.Sketch().rect(E.PCB_W, 102.0).vertices(">Y").fillet(5.5)).extrude(E.PCB_T))
    tx, ty = E.pcb_to_dev(19.0, 107.0)
    tab = cq.Workplane("XY").workplane(offset=Z_PCB).center(tx, ty).rect(12.0, 10.0).extrude(E.PCB_T)
    return body.union(tab)


def box(cx, cy, w, l, z0, h):
    return cq.Workplane("XY").workplane(offset=z0).center(cx, cy).rect(w, l).extrude(h)


def parts():
    mx, my = E.pcb_to_dev(19.0, 20.65 / 2)          # body top on the PCB edge
    bx, by = E.pcb_to_dev(19.0, 70.0)
    batt = box(bx, by, 30.0, 40.0, Z_BACK_PCB, E.BATT_T)
    coil = cq.Workplane("XY").workplane(offset=Z_BACK_PCB + E.BATT_T).center(bx, by).circle(15.0).extrude(1.2)
    foam = cq.Workplane("XY").workplane(offset=Z_BACK_PCB + E.BATT_T + 1.2).center(bx, by).circle(15.0).extrude(1.15)
    # passives envelope: electronics band (PCB y 4.6..29.5), full width, minus the module footprint
    ex, ey = E.pcb_to_dev(19.0, (4.6 + 29.5) / 2)
    comps = box(ex, ey, E.PCB_W - 0.2, 29.5 - 4.6, Z_BACK_PCB, 1.35).cut(box(mx, my, 15.7, 20.85, Z_BACK_PCB - 0.1, 2))
    return {"pcb": pcb(), "module": box(mx, my, 15.5, 20.65, Z_BACK_PCB, 2.4), "parts": comps,
            "battery": batt, "coil": coil, "foam": foam}


def vol(a, b):
    r = a.intersect(b)
    return sum(v.Volume() for v in r.vals()) if r.vals() else 0.0


def mesh(wp):
    path = "/tmp/_part.stl"
    cq.exporters.export(wp, path, tolerance=0.05, angularTolerance=0.2)
    return trimesh.load(path)


def main():
    cup, plug, br = E.make_cup(), E.make_plug(), E.make_bracket()
    inner = parts()
    print("Interference check [mm3] (must be 0):")
    bad = False
    for name, p in inner.items():
        for shell_name, shell in (("cup", cup), ("plug", plug)):
            v = vol(p, shell)
            bad |= v > 1e-3
            print(f"  {name:8s} vs {shell_name:5s}: {v:.3f}")
    # clamping: gap between the stack and the plug back wall / posts
    print("PCB pressed on front wall: PCB front face Z =", Z_PCB, "(front wall inner face Z =", E.T_FRONT, ")")
    print(f"Stack back face Z = {Z_BACK_PCB + E.BATT_T + 1.2 + 1.15:.2f}, plug inner face Z = {E.DEPTH - E.T_BACK:.2f}")

    # ---- cross-section through the battery/coil (Y = battery centre) ----
    bx, by = E.pcb_to_dev(19.0, 70.0)
    _, ywin = E.pcb_to_dev(19.0, 107.0)
    fig, axes = plt.subplots(2, 1, figsize=(9, 6.2))
    colors = {"cup": "#9bb7d4", "plug": "#3b6fb6", "pcb": "#2e7d32", "module": "#666", "battery": "#d4a017",
              "coil": "#b45309", "foam": "#e5e7eb", "parts": "#a3a3a3"}
    for ax, (yy, title) in zip(axes, ((by, "Section across the electrode band (battery + coil)"),
                                      (E.pcb_to_dev(19, 12.0)[1], "Section across the electronics band (module + clamp posts)"))):
        for name, wp in [("cup", cup), ("plug", plug)] + list(inner.items()):
            m = mesh(wp)
            sec = m.section(plane_origin=[0, yy, 0], plane_normal=[0, 1, 0])
            if sec is None:
                continue
            for ent in sec.discrete:
                ax.fill(ent[:, 0], ent[:, 2], color=colors[name], ec="k", lw=0.4, alpha=0.95)
        ax.set_aspect("equal"); ax.invert_yaxis()
        ax.set_title(title, fontsize=9); ax.set_xlabel("X [mm]", fontsize=8); ax.set_ylabel("Z [mm]\n(water side up)", fontsize=8)
        ax.tick_params(labelsize=7)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colors.values()]
    fig.legend(handles, list(colors), ncol=7, fontsize=7, loc="lower center", frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(os.path.join(E.IMG, "enclosure_section.png"), dpi=150); plt.close(fig)

    # ---- O-ring gland close-up ----
    fig, ax = plt.subplots(figsize=(5, 3.6))
    for name, wp in (("cup", cup), ("plug", plug)):
        sec = mesh(wp).section(plane_origin=[0, 0, 0], plane_normal=[0, 1, 0])
        for ent in sec.discrete:
            ax.fill(ent[:, 0], ent[:, 2], color=colors[name], ec="k", lw=0.5)
    gx = -(E.CAV_W / 2 - E.PLUG_CLR - E.GLAND_DEPTH)
    cs = E.ORING_CS * 0.98
    ax.add_patch(plt.Circle((gx - (E.GLAND_DEPTH + E.PLUG_CLR) / 2, E.GROOVE_Z0 + E.GLAND_W / 2), cs / 2,
                            color="k", alpha=0.85))
    ax.text(gx + 1.2, E.GROOVE_Z0 + 1.2, "EPDM O-ring 90 x 1.5\n(shown uncompressed;\n22 % squeeze when fitted)", fontsize=7)
    ax.annotate("M2 screw axis\n(outboard of seal)", xy=(-E.OUT_W / 2, E.SCREW_Z), xytext=(-E.OUT_W / 2 - 7, E.SCREW_Z + 2.8),
                fontsize=7, arrowprops=dict(arrowstyle="->", lw=0.6))
    ax.set_xlim(-E.OUT_W / 2 - 9, -E.OUT_W / 2 + 9); ax.set_ylim(E.DEPTH + 1, -1)
    ax.set_aspect("equal"); ax.set_title("Radial O-ring gland (section, left wall)", fontsize=9)
    ax.set_xlabel("X [mm]", fontsize=8); ax.set_ylabel("Z [mm]", fontsize=8); ax.tick_params(labelsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(E.IMG, "enclosure_gland.png"), dpi=170); plt.close(fig)

    # ---- isometric line drawings of the three printed parts ----
    import cairosvg
    views = [("cup", cup, (1, -1, -1.2)), ("plug", plug, (-1, -1, 1.4)), ("bracket", br, (-1, -1, -1.2))]
    for name, wp, d in views:
        svg = f"/tmp/_{name}.svg"
        cq.exporters.export(wp, svg, opt={"projectionDir": d, "showHidden": False, "strokeWidth": 0.25,
                                          "width": 420, "height": 520, "marginLeft": 20, "marginTop": 20})
        cairosvg.svg2png(url=svg, write_to=f"/tmp/_{name}.png", output_width=420, background_color="white")
    import matplotlib.image as mpimg
    fig, axes = plt.subplots(1, 3, figsize=(10, 4.6))
    for ax, (name, _, _) in zip(axes, views):
        ax.imshow(mpimg.imread(f"/tmp/_{name}.png")); ax.set_axis_off()
        ax.set_title({"cup": "Cup (front wall = sensing face)", "plug": "Plug with O-ring groove (Qi face)",
                      "bracket": "Tub bracket (2 suction cups)"}[name], fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(E.IMG, "enclosure_parts.png"), dpi=140); plt.close(fig)
    print("renders written to docs/img/enclosure_*.png")
    return not bad


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
