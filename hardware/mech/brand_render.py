#!/usr/bin/env python3
"""Brand assets (rev B): logo lockup, colour mockup (front / back / side / bracket) and line
drawings of the real CAD faces.  Marks are drawn from the same CadQuery geometry as the deboss.

    python3 hardware/mech/brand_render.py
"""
import os
import sys

import cadquery as cq
import cairosvg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand as B  # noqa: E402
import enclosure as E  # noqa: E402

IMG = E.IMG
P = B.PALETTE
S = 4.0                                            # px per mm
EDGE = "#b9c2c6"
DEB_FRONT = "#9AA6A8"      # unpainted deboss on mist: reads as a soft shadow
DEB_BACK = "#8FA3B1"       # unpainted deboss on slate


def rrect(cx, cy, w, h, r, **kw):
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return f'<rect x="{cx - w / 2:.1f}" y="{cy - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}" {attrs}/>'


def solid_paths(wp, ox, oy, fill, mirror=False):
    return "".join(f'<path fill-rule="evenodd" fill="{fill}" d="{d}"/>'
                   for d in B.shape_to_svg_paths(wp, ox, oy, S, mirror))


def text(cx, cy, s, size_mm, fill, weight=500):
    return (f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" dominant-baseline="central" font-family="Inter" '
            f'font-weight="{weight}" font-size="{size_mm * S * 0.95:.1f}" fill="{fill}">{s}</text>')


def front_view(ox, oy):
    """Seen from the front (water side): device +X is on the viewer's LEFT."""
    X = lambda x: ox - x * S  # noqa: E731
    Y = lambda y: oy - y * S  # noqa: E731
    g = [rrect(ox, oy, E.OUT_W * S, E.OUT_L * S, E.OUT_R * S, fill=P["mist"], stroke=EDGE, stroke_width=1.5)]
    for k in range(1, 7):                          # electrodes faintly visible through translucent PP
        _, yc = E.pcb_to_dev(19, 46.5 + (6 - k) * 10)
        g.append(rrect(X(0), Y(yc), 30 * S, 9 * S, 3, fill="#dde3e1"))
    _, yref = E.pcb_to_dev(19, 35)
    g.append(rrect(X(0), Y(yref), 30 * S, 6 * S, 3, fill="#e2e7e5"))
    for f in B.front_features(E):                  # every debossed feature, from the CAD solids
        bb = f.val().BoundingBox()
        if bb.zmax <= B.DEBOSS + 1e-6:
            g.append(solid_paths(f, ox, oy, DEB_FRONT, mirror=True))
    _, yw = E.pcb_to_dev(19, 107)
    g.append(rrect(X(0), Y(yw), E.WIN_W * S, E.WIN_H * S, 4, fill="#d5ddda"))
    return "".join(g)


def back_view(ox, oy):
    X = lambda x: ox + x * S  # noqa: E731
    g = [rrect(ox, oy, E.OUT_W * S, E.OUT_L * S, E.OUT_R * S, fill=P["mist"], stroke=EDGE, stroke_width=1.5),
         rrect(ox, oy, (E.CAV_W - 0.2) * S, (E.CAV_L - 0.2) * S, (E.CAV_R - 0.1) * S, fill=P["slate"])]
    light = DEB_BACK
    for f in B.back_features(E):
        g.append(solid_paths(f, ox, oy, light))
    g.append(f'<rect x="{X(-4):.1f}" y="{oy - E.OUT_L / 2 * S:.1f}" width="{8 * S:.1f}" height="{2.6 * S:.1f}" fill="{P["mist"]}"/>')
    return "".join(g)


def side_view(ox, oy):
    """Long side, showing the waterline groove and the screws."""
    Y = lambda y: oy - y * S  # noqa: E731
    Z = lambda z: ox + (z - E.DEPTH / 2) * S  # noqa: E731
    g = [rrect(ox, oy, E.DEPTH * S, E.OUT_L * S, 2.5 * S, fill=P["mist"], stroke=EDGE, stroke_width=1.5),
         f'<rect x="{Z(E.DEPTH - E.T_BACK):.1f}" y="{Y(E.OUT_L / 2 - 2):.1f}" width="{E.T_BACK * S:.1f}" '
         f'height="{(E.OUT_L - 4) * S:.1f}" fill="{P["slate"]}"/>']
    _, ya = E.pcb_to_dev(19, 42)
    g.append(f'<rect x="{Z(E.FRONT_ROUND + 0.3):.1f}" y="{Y(ya) - 0.4 * S:.1f}" width="{(E.DEPTH - 0.9 - E.FRONT_ROUND - 0.3) * S:.1f}" '
             f'height="{0.8 * S:.1f}" fill="{DEB_FRONT}"/>')
    for sy in E.SCREW_Y:
        g.append(f'<circle cx="{Z(E.SCREW_Z):.1f}" cy="{Y(sy):.1f}" r="{1.9 * S:.1f}" fill="#a4adb2"/>')
    return "".join(g)


def bracket_view(ox, oy):
    X = lambda x: ox + x * S  # noqa: E731
    Y = lambda y: oy - y * S  # noqa: E731
    iw = E.OUT_W + 2 * E.BR_GAP
    ow = iw + 2 * E.BR_WALL
    y0 = -E.OUT_L / 2 - 2.0
    g = [f'<circle cx="{X(0):.1f}" cy="{Y(ky):.1f}" r="{20 * S:.1f}" fill="#dfe4e2"/>' for ky in (y0 + 18.0, y0 + E.BR_L - 18.0)]
    g.append(rrect(X(0), Y(y0 + E.BR_L / 2), ow * S, E.BR_L * S, 3 * S, fill=P["slate"]))
    for ky in (y0 + 18.0, y0 + E.BR_L - 18.0):
        g.append(rrect(X(0), Y(ky + E.KEY_SLIDE / 2), (E.KEY_HEAD_D + 1) * S, (E.KEY_SLIDE + E.KEY_HEAD_D + 1) * S,
                       (E.KEY_HEAD_D + 1) * S / 2, fill="#4f6474"))
    for wy in (y0 + 38.0, y0 + 48.0):
        g.append(rrect(X(0), Y(wy), 35 * S, 5 * S, 2.5 * S, fill="#4f6474"))
    return "".join(g)


def mockup(path):
    W, H = 900, 640
    cy = H / 2 + 6
    body = [f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
            front_view(130, cy), back_view(345, cy), side_view(520, cy), bracket_view(720, cy)]
    for x, s in [(130, "front"), (345, "back (Qi side)"), (520, "side"), (720, "bracket + 40 mm cups")]:
        body.append(f'<text x="{x}" y="26" text-anchor="middle" font-family="Inter" font-weight="500" '
                    f'font-size="15" fill="{P["ink"]}">{s}</text>')
    for i, (k, v) in enumerate(P.items()):
        x = 40 + i * 150
        body.append(f'<rect x="{x}" y="{H - 32}" width="18" height="18" rx="4" fill="{v}" stroke="#cbd2d0"/>')
        body.append(f'<text x="{x + 26}" y="{H - 18}" font-family="Inter" font-size="12" fill="{P["ink"]}">{k} {v}</text>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{"".join(body)}</svg>'
    with open(path.replace(".png", ".svg"), "w") as f:
        f.write(svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=path, output_width=W * 2)


def cad_lines(path):
    cup, plug = E.make_cup(), E.make_plug()
    tmp = []
    for name, wp, d in (("f", cup, (0, 0, -1)), ("b", plug, (0, 0, 1))):
        svg = f"/tmp/_brand_{name}.svg"
        cq.exporters.export(wp, svg, opt={"projectionDir": d, "showHidden": False, "strokeWidth": 0.12,
                                          "width": 340, "height": 860, "marginLeft": 10, "marginTop": 10})
        png = svg.replace(".svg", ".png")
        cairosvg.svg2png(url=svg, write_to=png, output_width=340, background_color="white")
        tmp.append(png)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(6.6, 8.2))
    for a, p, t in zip(ax, tmp, ("cup, front face (CAD)", "plug, back face (CAD)")):
        a.imshow(mpimg.imread(p)); a.set_axis_off(); a.set_title(t, fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)


def main():
    B.logo_svg(os.path.join(IMG, "brand_logo.svg"))
    cairosvg.svg2png(url=os.path.join(IMG, "brand_logo.svg"), write_to=os.path.join(IMG, "brand_logo.png"),
                     output_width=900, background_color="white")
    mockup(os.path.join(IMG, "brand_mockup.png"))
    cad_lines(os.path.join(IMG, "brand_cad_faces.png"))
    print("wrote docs/img/brand_logo.*, brand_mockup.*, brand_cad_faces.png")


if __name__ == "__main__":
    main()
