#!/usr/bin/env python3
"""Brand identity + industrial-design features for the bath monitor (rev B).

All features are shallow debosses or grooves: no paint, inserts or glue required.
  front (cup) : bathtub mark + wordmark in the dry top band; small alarm arrows on both margins at
                the default alarm level. No scale: through the translucent cup the electrodes show as
                soft grey panels (copper under white solder mask). Nothing is cut over the electrodes.
  sides (cup) : a WATERLINE groove around both long sides at the default alarm level, and
                finger-grip grooves (front half of the wall only) in the dry top band.
  back (plug) : bathtub mark + wordmark, the Qi COIL OUTLINE (one 30 mm ring exactly over the coil),
                "Qi" / "charge this side", rating line.
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


# ---------------- the mark (rev C3): a rectangular bathtub in true isometric view ----------------
# Built as 2-D polygons (shapely) by projecting a 3-D tub: plan L x W, rounded corners, a rim on top, water
# just under the lip, two visible side walls split by a crease at the near corner, and a tap on the far end.
TUB3D = dict(L=1.0, W=0.50, H=0.30, r=0.13, rim=0.075, lip=0.06, drop=0.03)
ISO_GAP = 0.045                  # gap between parts, as a fraction of the mark width (>= 0.5 mm at 11 mm)


def iso_polys():
    """{'tub': polygons (rim + walls + feet), 'water': polygon}, normalised to width 1, centred on (0, 0), y up."""
    from shapely import affinity
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import unary_union
    T = TUB3D
    c, sn = math.cos(math.radians(30)), math.sin(math.radians(30))

    def plan(inset):                                     # rounded-rectangle outline in plan, inset by `inset`
        rr = max(T["r"] - inset, 0.01)
        return box(T["r"], T["r"], T["L"] - T["r"], T["W"] - T["r"]).buffer(rr, quad_segs=12)

    def proj(poly, z):
        return Polygon([((x - y) * c, z - (x + y) * sn) for x, y in poly.exterior.coords])

    def pt(x, y, z):
        return ((x - y) * c, z - (x + y) * sn)

    H, z_lip = T["H"], T["H"] - T["lip"]
    outer = proj(plan(0), H)
    span = outer.bounds[2] - outer.bounds[0]
    gap = ISO_GAP * span
    opening = proj(plan(T["rim"]), H)
    rim = outer.difference(opening)
    water = proj(plan(T["rim"] + 0.035), H - T["drop"]).intersection(opening.buffer(-gap))
    walls = unary_union([proj(plan(0), z_lip), proj(plan(0.03), 0.0)]).convex_hull
    walls = walls.difference(outer.buffer(gap))
    # crease along the near vertical corner, so the two visible walls read as two faces
    k = T["r"] * (1 - 1 / math.sqrt(2))
    cx, cy = T["L"] - k, T["W"] - k
    walls = walls.difference(LineString([pt(cx, cy, z_lip + 0.1), pt(cx, cy, -0.2)]).buffer(gap * 0.5))
    # tap on the far short end: a post up from the rim and a spout reaching over the water
    st = 0.055 * span
    tap_pts = [pt(0.04, T["W"] / 2, H - 0.02), pt(0.04, T["W"] / 2, H + 0.20), pt(0.17, T["W"] / 2, H + 0.20)]
    tap = LineString(tap_pts).buffer(st / 2, cap_style="round", join_style="round")
    water = water.difference(tap.buffer(gap))
    tub = unary_union([rim, walls, tap])
    allg = unary_union([tub, water])
    minx, miny, maxx, maxy = allg.bounds
    sc = 1.0 / (maxx - minx)
    move = lambda g: affinity.scale(affinity.translate(g, -(minx + maxx) / 2, -(miny + maxy) / 2), sc, sc, origin=(0, 0))  # noqa: E731
    return {"tub": move(tub), "water": move(water), "height": (maxy - miny) * sc}


def _polys(g):
    return list(g.geoms) if hasattr(g, "geoms") else [g]


def _poly_solid(poly, w, depth):
    ext = [(x * w, y * w) for x, y in list(poly.exterior.coords)[:-1]]
    sol = cq.Workplane("XY").polyline(ext).close().extrude(depth)
    for h in poly.interiors:
        sol = sol.cut(cq.Workplane("XY").polyline([(x * w, y * w) for x, y in list(h.coords)[:-1]]).close().extrude(depth))
    return sol


def iso_tub_solid(w, depth, split=False):
    P = iso_polys()
    parts = {}
    for key in ("tub", "water"):
        sol = None
        for poly in _polys(P[key]):
            if poly.is_empty or poly.area < 1e-6:
                continue
            ps = _poly_solid(poly, w, depth)
            sol = ps if sol is None else sol.union(ps)
        parts[key] = sol
    return (parts["tub"], parts["water"]) if split else parts["tub"].union(parts["water"])


def iso_svg_paths(g, ox, oy, scale):
    """Shapely polygons -> SVG path data (y flipped), one path per polygon, holes via evenodd."""
    out = []
    for poly in _polys(g):
        d = ""
        for ring in [poly.exterior] + list(poly.interiors):
            pts = list(ring.coords)[:-1]
            d += "M" + "L".join(f"{ox + x * scale:.2f} {oy - y * scale:.2f}" for x, y in pts) + "Z"
        out.append(d)
    return out


MARK = iso_tub_solid


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


# ---------------- features ----------------
def front_features(E):
    feats = []
    _, y_mark = E.pcb_to_dev(19.0, 8.0)
    _, y_word = E.pcb_to_dev(19.0, 19.5)
    feats.append(front(MARK(11.0, DEBOSS), 0, y_mark))
    feats.append(front(text_solid(NAME, 6.5, DEBOSS), 0, y_word))
    # alarm-level arrows on both front margins (outside the electrodes), tips at the default alarm line.
    # No scale: the electrodes themselves show through the translucent cup as soft grey panels
    # (copper under WHITE solder mask), which is the level graphic.
    ticks, _ = pad_levels(E)
    y_alarm = ticks[-1]
    tip = scale_geometry(E)[0]
    for side in (-1, 1):
        feats.append(cq.Workplane("XY").polyline([(side * tip, y_alarm), (side * (tip + 2.6), y_alarm + 1.5),
                                                  (side * (tip + 2.6), y_alarm - 1.5)]).close().extrude(DEBOSS))
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
    feats += grip_features(E)
    return feats


GRIP_Y = (24.0, 50.0)          # device Y band (above the bracket, below the cup top round)
GRIP_PITCH, GRIP_W, GRIP_D = 2.0, 0.8, 0.35
GRIP_Z_END = 6.1               # grooves run from just behind the front round to here: clear of the screw heads (Z 6.45-10.25)
                               # and visibly different from the full-depth waterline groove


def grip_features(E):
    """Finger-grip grooves on both long sides of the dry top band, where you pinch to lift it out."""
    feats = []
    n = int((GRIP_Y[1] - GRIP_Y[0]) / GRIP_PITCH) + 1
    for side in (-1, 1):
        for i in range(n):
            y = GRIP_Y[0] + i * GRIP_PITCH
            z0 = E.FRONT_ROUND + 0.3
            feats.append(cq.Workplane("XY").workplane(offset=z0).center(side * (E.OUT_W / 2), y)
                         .rect(2 * GRIP_D, GRIP_W).extrude(GRIP_Z_END - z0))
    return feats


def back_features(E):
    z = E.DEPTH
    feats = []
    _, y_mark = E.pcb_to_dev(19.0, 9.0)
    _, y_word = E.pcb_to_dev(19.0, 19.0)
    _, y_tag = E.pcb_to_dev(19.0, 25.0)
    feats.append(back(MARK(10.0, DEBOSS), 0, y_mark, z))
    feats.append(back(text_solid(NAME, 6.0, DEBOSS), 0, y_word, z))
    feats.append(back(text_solid(TAGLINE, 2.6, DEBOSS, FONT_SMALL), 0, y_tag, z))
    # Qi coil outline: one continuous ring at the coil's 30 mm outside diameter
    _, yc = E.pcb_to_dev(19.0, 70.0)
    ring = cq.Workplane("XY").circle(15.0 + 0.25).circle(15.0 - 0.25).extrude(DEBOSS)
    feats.append(back(ring, 0, yc, z))
    feats.append(back(text_solid("Qi", 3.2, DEBOSS), 0, yc + 1.2, z))
    feats.append(back(text_solid("charge this side", 2.4, DEBOSS, FONT_SMALL), 0, yc - 3.2, z))
    _, y_rate = E.pcb_to_dev(19.0, 106.0)
    feats.append(back(text_solid("Li-ion 3.7 V 320 mAh   IP68   rev C", 2.2, DEBOSS, FONT_SMALL), 0, y_rate, z))
    return feats


# ---------------- SVG export of the mark (from the same CAD geometry) ----------------
def shape_to_svg_paths(wp, sx, sy, scale, mirror=False):
    """Top faces of an extruded 2-D shape -> SVG path data (evenodd)."""
    paths = []
    for f in wp.faces(">Z").vals():
        d = []
        for wire in [f.outerWire()] + f.innerWires():
            # walk the wire as one ordered curve (per-edge sampling breaks on reversed edges)
            n = max(64, int(wire.Length() * scale / 1.5))
            pts = []
            for i in range(n):
                p = wire.positionAt(i / n)
                pts.append((sx + (-p.x if mirror else p.x) * scale, sy - p.y * scale))
            d.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z")
        paths.append(" ".join(d))
    return paths


def logo_svg(path, w_mm=12.0, scale=10.0, with_word=True):
    P = iso_polys()
    pad = 6 * scale / 4
    mw, mh = w_mm * scale, w_mm * P["height"] * scale
    W = mw + 2 * pad + (w_mm * 2.3 * scale if with_word else 0)
    H = max(mh, w_mm * 0.8 * scale) + 2 * pad
    cx, cy = pad + mw / 2, H / 2
    body = [f'<path fill-rule="evenodd" fill="{PALETTE["slate"]}" d="{d}"/>' for d in iso_svg_paths(P["tub"], cx, cy, mw)]
    body += [f'<path fill="{PALETTE["sea glass"]}" d="{d}"/>' for d in iso_svg_paths(P["water"], cx, cy, mw)]
    if with_word:
        fs = w_mm * 0.8 * scale * 0.78
        body.append(f'<text x="{pad + mw + pad * 0.9:.1f}" y="{cy + fs * 0.28:.1f}" font-family="Inter" font-weight="500" '
                    f'font-size="{fs:.1f}" letter-spacing="0.5" fill="{PALETTE["ink"]}">{NAME}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H:.1f}" width="{W:.0f}" height="{H:.0f}">'
           + "".join(body) + "</svg>")
    with open(path, "w") as f:
        f.write(svg)


# ---------------- compact icon (favicon / app icon): the same isometric tub polygons ----------------
def icon_svg(size=32, w=26.0, bg=None):
    P = iso_polys()
    from shapely import simplify
    c = size / 2
    tub = "".join(f'<path fill-rule="evenodd" d="{d}"/>' for d in iso_svg_paths(simplify(P["tub"], 0.002), c, c, w))
    water = "".join(f'<path d="{d}"/>' for d in iso_svg_paths(simplify(P["water"], 0.002), c, c, w))
    back = f'<rect width="{size}" height="{size}" rx="{size * 0.22:.1f}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">{back}'
            f'<g fill="{PALETTE["slate"]}">{tub}</g><g fill="{PALETTE["sea glass"]}">{water}</g></svg>')
