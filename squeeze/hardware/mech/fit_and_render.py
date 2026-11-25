#!/usr/bin/env python3
"""Fit check (every pair of parts, plates at rest and at full swell), air volume, and renders.

    python3 squeeze/hardware/mech/fit_and_render.py   ->  docs/img/unit_*.png, prints a report
"""
import itertools
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402
import cadquery as cq  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import squeeze_unit as U  # noqa: E402

COLORS = dict(skin="#f08a5d", base="#d9d4cc", chassis="#8f9bb3", plate_pos="#5b7db1", plate_neg="#5b7db1",
              cam="#e8c547", coil="#b87333", pcb="#2f7d4f", parts="#333333", battery="#9aa0a6",
              servo="#3a6fd8", led="#ffffff")
# parts that are meant to touch: the cam rides on the plate bosses
TOUCH = {frozenset(("cam", "plate_pos")), frozenset(("cam", "plate_neg"))}
# at full swell the plates stretch the skin outward by design (3 mm travel - 1 mm gap = 2 mm)
STRETCH = {frozenset(("skin", "plate_pos")), frozenset(("skin", "plate_neg"))}


def vol(a, b):
    try:
        return a.intersect(b).val().Volume()
    except Exception:
        return 0.0


def fit(lift):
    p = U.all_parts(lift)
    bad = []
    for (na, a), (nb, b) in itertools.combinations(p.items(), 2):
        v = vol(a, b)
        pair = frozenset((na, nb))
        if v > 0.5 and pair not in TOUCH and not (lift > 0 and pair in STRETCH):
            bad.append((na, nb, v))
    return p, bad


def tris(wp, tol=0.15):
    verts, faces = wp.val().tessellate(tol, 0.12)
    v = np.array([(q.x, q.y, q.z) for q in verts])
    return v[np.array(faces)]


def shade(t, rgb, light=np.array([-0.4, -0.7, 0.6])):
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    k = 0.35 + 0.65 * np.clip(np.abs(n @ (light / np.linalg.norm(light))), 0, 1)
    c = np.array(matplotlib.colors.to_rgb(rgb))
    return np.clip(c[None, :] * k[:, None], 0, 1)


def draw(ax, parts, elev=18, azim=-60, lim=40, alpha=1.0):
    for name, wp in parts.items():
        t = tris(wp)
        pc = Poly3DCollection(t, facecolors=shade(t, COLORS.get(name, "#999")), edgecolors="none",
                              alpha=alpha)
        ax.add_collection3d(pc)
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-5, 2 * lim - 5)
    ax.set_box_aspect((1, 1, 1)); ax.view_init(elev=elev, azim=azim); ax.set_axis_off()


def cut(parts, keep):
    return {n: w.intersect(keep) for n, w in parts.items() if vol(w, keep) > 0.01}


def wpts(w, axes, n=240):
    pts = [w.positionAt(t) for t in np.linspace(0, 1, n)]
    return np.array([[getattr(q, a) for a in axes] for q in pts])


def section_z(parts, z, ax, title):
    """2D section at height z (the cam plane)."""
    plane = U.slab(z - 0.01, z + 0.01)
    for name, wp in parts.items():
        try:
            s = wp.intersect(plane)
            if not s.vals():
                continue
            for f in s.faces("+Z").vals():
                pts = wpts(f.outerWire(), "xy")
                ax.fill(pts[:, 0], pts[:, 1], color=COLORS.get(name, "#999"), alpha=0.85, lw=0.4, ec="k")
                for w in f.innerWires():
                    pts = wpts(w, "xy")
                    ax.fill(pts[:, 0], pts[:, 1], color="white", lw=0.4, ec="k")
        except Exception as e:  # a part that misses the plane
            print(f"  section: {name}: {e}") if "empty" not in str(e).lower() else None
    ax.set_aspect("equal"); ax.set_xlim(-28, 28); ax.set_ylim(-24, 24)
    ax.set_title(title, fontsize=9); ax.tick_params(labelsize=7)


def main():
    os.makedirs(U.IMG, exist_ok=True)
    print("fit check ...")
    rest, bad0 = fit(0.0)
    full, bad1 = fit(U.CAM_A - U.CAM_B)
    for tag, bad in (("rest", bad0), ("full swell", bad1)):
        print(f"  {tag}: " + ("no interferences" if not bad else
                              "; ".join(f"{a}/{b} {v:.1f} mm^3" for a, b, v in bad)))

    # air volume inside the skin and base, and the squeeze stroke
    inside = U.pebble(U.SKIN)
    solids = sum(vol(inside, w) for n, w in rest.items() if n not in ("skin",))
    air = inside.val().Volume() - solids
    plate_area = 2 * 2 * U.PLATE_HALF_W * (U.PLATE_Z[1] - U.PLATE_Z[0]) * 0.85   # both plates, curved
    print(f"  air inside: {air / 1000:.1f} cm^3; plate area {plate_area / 100:.0f} cm^2")
    for depth, frac in ((0.3, 0.5), (0.6, 0.5), (0.9, 0.6)):
        dv = plate_area * frac * depth
        print(f"  skin pressed {depth} mm over {frac:.0%} of the plates: dV {dv / 1000:.2f} cm^3 "
              f"-> +{101325 * dv / (air - dv) / 1000:.1f} kPa")

    # renders
    fig = plt.figure(figsize=(12, 4.4))
    ax = fig.add_subplot(1, 3, 1, projection="3d")
    draw(ax, {"skin": rest["skin"], "base": rest["base"]}); ax.set_title("outside", fontsize=10)
    ax = fig.add_subplot(1, 3, 2, projection="3d")
    inner = {n: w for n, w in rest.items() if n != "skin"}
    draw(ax, cut(inner, U.box(0, 0, -50, 200, 200, 200).translate((100, 0, 0)).union(
        U.box(0, 0, -50, 200, 200, 200).translate((0, -100, 0)))), azim=-50)
    ax.set_title("inside (skin off, quarter cut)", fontsize=10)
    ax = fig.add_subplot(1, 3, 3, projection="3d")
    ex = {}
    for n, w in rest.items():
        dz = dict(skin=45, chassis=12, plate_pos=12, plate_neg=12, cam=12, servo=12, battery=12, led=12).get(n, 0)
        dy = dict(plate_pos=18, plate_neg=-18, skin=0).get(n, 0)
        ex[n] = w.translate((0, dy, dz))
    draw(ax, ex, lim=55, elev=12, azim=-35); ax.set_title("exploded", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(U.IMG, "unit_views.png"), dpi=150); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(9, 4.2))
    zc = U.Z_CAM + U.CAM_T / 2
    section_z(rest, zc, axs[0], f"rest (section at cam, z = {zc:.1f})")
    section_z(full, zc, axs[1], "full swell: cam 90 deg, plates +3 mm")
    fig.tight_layout(); fig.savefig(os.path.join(U.IMG, "unit_cam_section.png"), dpi=150); plt.close(fig)

    fig = plt.figure(figsize=(5, 5))
    ax = fig.add_subplot(1, 1, 1)
    for name, wp in rest.items():
        try:
            s = wp.intersect(U.box(0, 0, -10, 0.02, 200, 200))
            for f in s.faces("+X").vals():
                pts = wpts(f.outerWire(), "yz", 400)
                ax.fill(pts[:, 0], pts[:, 1], color=COLORS.get(name, "#999"), alpha=0.85, lw=0.4, ec="k")
                for w in f.innerWires():
                    pts = wpts(w, "yz")
                    ax.fill(pts[:, 0], pts[:, 1], color="white", lw=0.4, ec="k")
        except Exception as e:  # a part that misses the plane
            print(f"  section: {name}: {e}") if "empty" not in str(e).lower() else None
    ax.set_aspect("equal"); ax.set_title("section x = 0 (palm on the left, fingers on the right)", fontsize=9)
    ax.tick_params(labelsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(U.IMG, "unit_section_x0.png"), dpi=150); plt.close(fig)

    m1, m2, core = U.mold()
    fig, ax = plt.subplots(figsize=(4.6, 5.2))
    cutp = U.box(0, 0.5, -20, 200, 0.02, 200)
    for name, w, c in (("mold", m1.union(m2), "#c9c3b8"), ("core", core, "#7aa2c8"), ("skin", rest["skin"], COLORS["skin"])):
        for f in w.intersect(cutp).faces("+Y").vals():
            pts = wpts(f.outerWire(), "xz", 400)
            ax.fill(pts[:, 0], pts[:, 1], color=c, lw=0.4, ec="k", label=name)
            for iw in f.innerWires():
                pts = wpts(iw, "xz")
                ax.fill(pts[:, 0], pts[:, 1], color="white", lw=0.4, ec="k")
    h, l = ax.get_legend_handles_labels()
    keep = {lab: hh for hh, lab in zip(h, l)}
    ax.legend(keep.values(), ["outer mold (2 halves)", "core plug", "skin (silicone)"], fontsize=7, loc="upper right")
    ax.set_aspect("equal"); ax.tick_params(labelsize=7)
    ax.set_title("skin mold, section on the parting plane (shown dome-up)", fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(U.IMG, "unit_mold.png"), dpi=150); plt.close(fig)
    print("renders written to squeeze/docs/img/unit_*.png")
    return 1 if (bad0 or bad1) else 0


if __name__ == "__main__":
    sys.exit(main())
