#!/usr/bin/env python3
"""Brand identity + industrial-design features for the bath monitor (rev B).

All features are shallow debosses or grooves: no paint, inserts or glue required.
  front (cup) : ripple mark + wordmark in the dry top band; a GRADUATED SCALE on both front
                margins (tick at every electrode boundary over the 60 mm range, pad numbers 1-6,
                alarm chevron at the default alarm level). Nothing is cut over the electrodes.
  sides (cup) : a WATERLINE groove around both long sides at the default alarm level.
  back (plug) : ripple mark + wordmark, the Qi COIL OUTLINE (dashed 30 mm circle + 4 alignment
                ticks, exactly over the coil), "charge this side", rating line.
The same 2-D geometry drives the CAD and the SVG logo, so they always match.
"""
import math
import os

import cadquery as cq

NAME = "brim"                                   # working name: "alert before it brims"
TAGLINE = "bath level monitor"
FONT_DIR = "/usr/share/fonts/opentype/inter"
FONT_WORD = os.path.join(FONT_DIR, "Inter-Medium.otf")
FONT_SMALL = os.path.join(FONT_DIR, "Inter-Medium.otf")

# muted palette
PALETTE = {
    "mist": "#E8ECEA",        # cup: soft warm white / natural translucent PP
    "slate": "#61798A",       # plug + bracket: muted blue-grey
    "ink": "#2F3A45",         # text, marks
    "sea glass": "#9CC3B9",   # accent: ripple centre, LED glow
}
DEBOSS = 0.35                 # mm


# ---------------- the mark: ripples from a pebble, seen at a low angle ----------------
def ripple_solid(w, depth):
    a, k = w / 2.0, 0.40
    parts = []
    # centre plop
    parts.append(cq.Workplane("XY").ellipse(a * 0.21, a * 0.21 * k).extrude(depth))
    # inner ring
    for f, st, gap in ((0.56, 0.062 * w, 0.0), (1.00, 0.046 * w, 0.30 * w)):
        rx, ry = a * f, a * f * k
        ring = (cq.Workplane("XY").ellipse(rx, ry).extrude(depth)
                .cut(cq.Workplane("XY").ellipse(rx - st, ry - st * k * 1.6).extrude(depth)))
        if gap:   # break the outer ring at both sides: ripples fading out
            for side in (-1, 1):
                ring = ring.cut(cq.Workplane("XY").center(side * rx, 0).rect(gap * 0.55, 2 * ry).extrude(depth))
        parts.append(ring)
    # splash droplet above the centre
    parts.append(cq.Workplane("XY").center(0, a * 0.62).circle(0.055 * w).extrude(depth))
    s = parts[0]
    for p in parts[1:]:
        s = s.union(p)
    return s


def text_solid(txt, size, depth, font=FONT_WORD):
    return cq.Workplane("XY").text(txt, size, depth, combine=False, fontPath=font, halign="center", valign="center")


def front(solid, x, y):          # front is seen from -Z: mirror so it reads correctly
    return solid.mirror("YZ").translate((x, y, 0))


def back(solid, x, y, z_face):   # back is seen from +Z
    return solid.translate((x, y, z_face - DEBOSS))


# ---------------- geometry helpers tied to the electrodes ----------------
def pad_levels(E):
    """Device Y of: tick positions (pad boundaries, bottom..top) and pad centres (pad 1..6)."""
    ticks = [E.pcb_to_dev(19, 101.0)[1]] + [E.pcb_to_dev(19, 91.5 - 10 * j)[1] for j in range(5)] + \
            [E.pcb_to_dev(19, 42.0)[1]]
    centres = [E.pcb_to_dev(19, 46.5 + (6 - k) * 10)[1] for k in range(1, 7)]
    return ticks, centres


def scale_geometry(E):
    """Front-margin scale layout (device X positions)."""
    x_in = 15.9                                  # just outside the 30 mm electrodes (|x| <= 15)
    x_out = E.OUT_W / 2 - 2.9                    # stop before the 2.5 mm front-edge round
    return x_in, x_out


def tick(x0, x1, y, w, depth, drop=0.5):
    """Tick from x0 to x1 (|x1| > |x0|), falling by `drop` mm towards the outer edge so water drains."""
    pts = [(x0, y + w / 2), (x1, y + w / 2 - drop), (x1, y - w / 2 - drop), (x0, y - w / 2)]
    return cq.Workplane("XY").polyline(pts).close().extrude(depth)


# ---------------- features ----------------
def front_features(E):
    feats = []
    _, y_mark = E.pcb_to_dev(19.0, 8.0)
    _, y_word = E.pcb_to_dev(19.0, 19.5)
    feats.append(front(ripple_solid(13.0, DEBOSS), 0, y_mark))
    feats.append(front(text_solid(NAME, 6.5, DEBOSS), 0, y_word))
    ticks, centres = pad_levels(E)
    x_in, x_out = scale_geometry(E)
    for i, y in enumerate(ticks):
        major = i in (0, len(ticks) - 1)
        for side in (-1, 1):
            if side == -1 and i == len(ticks) - 1:
                continue                         # alarm chevron instead (below)
            x1 = x_out if major else x_in + 0.62 * (x_out - x_in)
            feats.append(tick(side * x_in, side * x1, y, 0.5, DEBOSS))
    # pad numbers on the viewer's left margin (seen from the front, device +X is on the viewer's left)
    for k, y in enumerate(centres, 1):
        feats.append(front(text_solid(str(k), 2.4, DEBOSS, FONT_SMALL), (x_in + x_out) / 2, y))
    # default alarm chevron on the viewer's right, tip at the alarm line
    y_alarm = ticks[-1]
    tip = x_in
    feats.append(cq.Workplane("XY").polyline([(-tip, y_alarm), (-(tip + 2.6), y_alarm + 1.5),
                                              (-(tip + 2.6), y_alarm - 1.5)]).close().extrude(DEBOSS))
    return feats


def side_features(E):
    """Waterline groove around both long side walls at the default alarm level."""
    _, y_alarm = E.pcb_to_dev(19.0, 42.0)
    z0, z1 = E.FRONT_ROUND + 0.3, E.DEPTH - 0.9
    feats = []
    for side in (-1, 1):
        g = (cq.Workplane("XY").workplane(offset=z0).center(side * (E.OUT_W / 2), y_alarm)
             .rect(2 * 0.30, 0.8).extrude(z1 - z0))
        feats.append(g)
    return feats


def back_features(E):
    z = E.DEPTH
    feats = []
    _, y_mark = E.pcb_to_dev(19.0, 9.0)
    _, y_word = E.pcb_to_dev(19.0, 19.0)
    _, y_tag = E.pcb_to_dev(19.0, 25.0)
    feats.append(back(ripple_solid(12.0, DEBOSS), 0, y_mark, z))
    feats.append(back(text_solid(NAME, 6.0, DEBOSS), 0, y_word, z))
    feats.append(back(text_solid(TAGLINE, 2.6, DEBOSS, FONT_SMALL), 0, y_tag, z))
    # Qi coil outline: dashed circle at the coil's 30 mm OD + 4 alignment ticks
    _, yc = E.pcb_to_dev(19.0, 70.0)
    r, st, n = 15.0, 0.55, 24
    for i in range(n):
        if i % 2:
            continue
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        pts = [((r + st / 2) * math.cos(a0 + (a1 - a0) * t / 6), (r + st / 2) * math.sin(a0 + (a1 - a0) * t / 6)) for t in range(7)]
        pts += [((r - st / 2) * math.cos(a1 - (a1 - a0) * t / 6), (r - st / 2) * math.sin(a1 - (a1 - a0) * t / 6)) for t in range(7)]
        feats.append(back(cq.Workplane("XY").polyline(pts).close().extrude(DEBOSS), 0, yc, z))
    for ang in (0, 90, 180, 270):
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        seg = cq.Workplane("XY").center((r + 2.3) * ca, (r + 2.3) * sa).rect(2.4 if ca else 0.55, 0.55 if ca else 2.4).extrude(DEBOSS)
        feats.append(back(seg, 0, yc, z))
    feats.append(back(text_solid("Qi", 3.2, DEBOSS), 0, yc + 1.2, z))
    feats.append(back(text_solid("charge this side", 2.4, DEBOSS, FONT_SMALL), 0, yc - 3.2, z))
    _, y_rate = E.pcb_to_dev(19.0, 106.0)
    feats.append(back(text_solid("Li-ion 3.7 V 500 mAh   IP68   rev B", 2.2, DEBOSS, FONT_SMALL), 0, y_rate, z))
    return feats


# ---------------- SVG export of the mark (from the same CAD geometry) ----------------
def shape_to_svg_paths(wp, sx, sy, scale, mirror=False):
    """Top faces of an extruded 2-D shape -> SVG path data (evenodd)."""
    paths = []
    for f in wp.faces(">Z").vals():
        d = []
        for wire in [f.outerWire()] + f.innerWires():
            pts = []
            for e in wire.Edges():
                n = 2 if e.geomType() == "LINE" else 96
                for t in [i / n for i in range(n + 1)]:
                    p = e.positionAt(t)
                    pts.append((sx + (-p.x if mirror else p.x) * scale, sy - p.y * scale))
            d.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z")
        paths.append(" ".join(d))
    return paths


def logo_svg(path, w_mm=13.0, scale=9.0, with_word=True):
    mark = ripple_solid(w_mm, 0.2)
    pad = 6 * scale / 4
    mw, mh = w_mm * scale, w_mm * 0.62 * scale
    W = mw + 2 * pad + (w_mm * 2.3 * scale if with_word else 0)
    H = mh + 2 * pad
    cx, cy = pad + mw / 2, pad + mh * 0.62
    body = [f'<path fill-rule="evenodd" fill="{PALETTE["slate"]}" d="{d}"/>' for d in shape_to_svg_paths(mark, cx, cy, scale)]
    if with_word:
        body.append(f'<text x="{pad + mw + pad * 0.9:.1f}" y="{cy + mh * 0.18:.1f}" font-family="Inter" font-weight="500" '
                    f'font-size="{mh * 0.95:.1f}" letter-spacing="0.5" fill="{PALETTE["ink"]}">{NAME}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H:.1f}" width="{W:.0f}" height="{H:.0f}">'
           + "".join(body) + "</svg>")
    with open(path, "w") as f:
        f.write(svg)
