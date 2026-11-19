#!/usr/bin/env python3
"""Brand identity for the bath monitor: name, mark, palette, and the 3-D brand features.

Everything here is a shallow DEBOSS (no epoxy, no inserts, no paint required):
  front (cup)   : logo + wordmark in the dry top band, alarm-level chevrons on both edges.
                  Nothing is cut over the electrodes, so the sensing wall stays a flat 1.2 mm.
  back (plug)   : wordmark, product line, a Qi target (concentric rings centred on the coil),
                  "charge this side" and the rating line.
Optional: wipe enamel paint into the debossed text and remove the excess (still no glue).
"""
import math
import os

import cadquery as cq

NAME = "brim"                                   # working name: "alert before it brims"
TAGLINE = "bath level monitor"
FONT_DIR = "/usr/share/fonts/opentype/inter"
FONT_BOLD = os.path.join(FONT_DIR, "Inter-SemiBold.otf")
FONT_REG = os.path.join(FONT_DIR, "Inter-Medium.otf")

# palette (used for renders, docs and colour choice of the printed parts)
PALETTE = {
    "foam": "#EEF3F6",    # cup: frosted / natural translucent white
    "tide": "#1F6FB2",    # plug + bracket accent
    "deep": "#0B2545",    # text, icons
    "aqua": "#3FC1C9",    # highlight / LED glow / water fill in the mark
}
DEBOSS = 0.35                                  # mm; front wall 1.2 -> 0.85 under text (dry band only)


# ---------------- the mark: a drop filled to the brim line ----------------
def drop_points(h, n=48):
    """Teardrop outline of total height h, centred on its circle; returns (points, r, apex_y)."""
    r = h / 2.6
    d = h - r                                   # apex distance from circle centre
    phi = math.acos(r / d)                      # tangent-point angle from the apex direction
    a0, a1 = math.pi / 2 + phi, math.pi / 2 - phi + 2 * math.pi
    pts = [(0.0, d)]
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts, r, d


def mark_solid(h, depth, stroke=0.55, level=0.15):
    """3-D logo: drop outline (stroke) + the water below the level line, extruded by `depth`.
    Origin at the circle centre; +Y is up on the device."""
    pts, r, d = drop_points(h)
    outer = cq.Workplane("XY").polyline(pts).close().extrude(depth)
    inner_pts, _, _ = drop_points(h - 2 * stroke * 1.3)
    inner = cq.Workplane("XY").polyline(inner_pts).close().extrude(depth)
    ring = outer.cut(inner)
    water_top = -r + 2 * r * (0.5 + level)      # level line a bit above the circle centre
    water = inner.intersect(cq.Workplane("XY").center(0, (water_top - r - 1) / 2)
                            .rect(4 * r, water_top + r + 1).extrude(depth))
    # gap between outline and water (reads cleaner when small)
    water = water.intersect(cq.Workplane("XY").polyline(drop_points(h - 2 * stroke * 2.6)[0]).close().extrude(depth))
    return ring.union(water)


def text_solid(txt, size, depth, font=FONT_BOLD):
    return cq.Workplane("XY").text(txt, size, depth, combine=False, fontPath=font, halign="center", valign="center")


def place_front(solid, x, y):
    """Front face is seen from -Z: mirror in X so it reads correctly, cut from Z = 0."""
    return solid.mirror("YZ").translate((x, y, 0))


def place_back(solid, x, y, z_face):
    """Back face is seen from +Z: cut downward from the outer face."""
    return solid.translate((x, y, z_face - DEBOSS))


# ---------------- brand features ----------------
def front_features(E):
    """Cuts for the cup front.  E is the enclosure module (for geometry)."""
    feats = []
    _, y_logo = E.pcb_to_dev(19.0, 7.5)         # over the module (dry band)
    _, y_word = E.pcb_to_dev(19.0, 20.5)
    feats.append(place_front(mark_solid(9.0, DEBOSS), 0, y_logo))
    feats.append(place_front(text_solid(NAME, 7.5, DEBOSS), 0, y_word))
    # alarm-level chevrons: tip at the top edge of pad 6, on both front margins (outside the pads)
    _, y_alarm = E.pcb_to_dev(19.0, 42.0)
    for side in (-1, 1):
        x_tip = side * (E.OUT_W / 2 - 4.6)
        tri = (cq.Workplane("XY").polyline([(x_tip, y_alarm), (x_tip + side * 2.6, y_alarm + 1.6),
                                            (x_tip + side * 2.6, y_alarm - 1.6)]).close().extrude(DEBOSS))
        feats.append(tri)
    return feats


def back_features(E):
    """Cuts for the plug's outer (Qi) face."""
    z = E.DEPTH
    feats = []
    _, y_logo = E.pcb_to_dev(19.0, 10.0)
    _, y_word = E.pcb_to_dev(19.0, 21.0)
    _, y_tag = E.pcb_to_dev(19.0, 27.5)
    feats.append(place_back(mark_solid(8.0, DEBOSS), 0, y_logo, z))
    feats.append(place_back(text_solid(NAME, 7.0, DEBOSS), 0, y_word, z))
    feats.append(place_back(text_solid(TAGLINE, 2.8, DEBOSS, FONT_REG), 0, y_tag, z))
    # Qi target: three rings centred on the coil (the graphic tells you where the charger goes)
    _, y_coil = E.pcb_to_dev(19.0, 70.0)
    for r in (4.0, 8.5, 13.0):
        ring = (cq.Workplane("XY").circle(r + 0.35).circle(r - 0.35).extrude(DEBOSS))
        feats.append(place_back(ring, 0, y_coil, z))
    feats.append(place_back(text_solid("charge this side", 2.8, DEBOSS, FONT_REG), 0, y_coil - 17.0, z))
    feats.append(place_back(text_solid("Qi", 3.2, DEBOSS), 0, y_coil, z))
    _, y_rate = E.pcb_to_dev(19.0, 106.0)
    feats.append(place_back(text_solid("Li-ion 3.7 V 500 mAh   IP68   rev A", 2.2, DEBOSS, FONT_REG), 0, y_rate, z))
    return feats


def logo_svg(path, h=64.0, with_word=True):
    """Flat logo / lockup as SVG for docs and packaging."""
    pts, r, d = drop_points(h)
    inner, _, _ = drop_points(h - 2 * 0.55 * 1.3 * h / 9.0)
    water_pts, _, _ = drop_points(h - 2 * 0.55 * 2.6 * h / 9.0)
    water_top = -r + 2 * r * 0.65
    pad = 8.0
    W = 2 * r + 2 * pad + (h * 2.6 if with_word else 0)
    H = h + 2 * pad
    ox, oy = pad + r, pad + d                    # SVG y down; circle centre
    fmt = lambda p: f"{ox + p[0]:.2f},{oy - p[1]:.2f}"  # noqa: E731
    clip = f'<clipPath id="lvl"><rect x="0" y="{oy - water_top:.2f}" width="{W}" height="{H}"/></clipPath>'
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H:.1f}" width="{W:.0f}" height="{H:.0f}">',
           f"<defs>{clip}</defs>",
           f'<path fill-rule="evenodd" fill="{PALETTE["deep"]}" d="M{" L".join(fmt(p) for p in pts)} Z '
           f'M{" L".join(fmt(p) for p in inner)} Z"/>',
           f'<path clip-path="url(#lvl)" fill="{PALETTE["aqua"]}" d="M{" L".join(fmt(p) for p in water_pts)} Z"/>']
    if with_word:
        svg.append(f'<text x="{ox + r + pad * 1.2:.1f}" y="{oy + r * 0.55:.1f}" font-family="Inter, Arial, sans-serif" '
                   f'font-weight="600" font-size="{h * 0.95:.1f}" letter-spacing="-1" fill="{PALETTE["deep"]}">{NAME}</text>')
    svg.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(svg))
