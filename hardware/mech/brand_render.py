#!/usr/bin/env python3
"""Brand assets: logo lockup (SVG/PNG), colour mockup of the device (front / back / bracket),
and line drawings of the real CAD faces (to check the deboss).

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
S = 4.0          # px per mm in the mockup


def rrect(cx, cy, w, h, r, **kw):
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return f'<rect x="{cx - w / 2:.1f}" y="{cy - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}" {attrs}/>'


def mark(cx, cy, h, mirror=False, fill=P["deep"], water=P["aqua"]):
    """The drop mark in SVG at device-mm size h, centred on the drop's circle (mockup px coords)."""
    pts, r, d = B.drop_points(h)
    inner, _, _ = B.drop_points(h - 2 * 0.55 * 1.3)
    wpts, _, _ = B.drop_points(h - 2 * 0.55 * 2.6)
    wt = -r + 2 * r * 0.65
    f = lambda p: f"{cx + p[0] * S:.1f},{cy - p[1] * S:.1f}"  # noqa: E731
    cid = f"c{int(cx)}{int(cy)}"
    return (f'<clipPath id="{cid}"><rect x="0" y="{cy - wt * S:.1f}" width="2000" height="2000"/></clipPath>'
            f'<path fill-rule="evenodd" fill="{fill}" d="M{" L".join(map(f, pts))} Z M{" L".join(map(f, inner))} Z"/>'
            f'<path clip-path="url(#{cid})" fill="{water}" d="M{" L".join(map(f, wpts))} Z"/>')


def text(cx, cy, s, size_mm, weight=600, fill=P["deep"]):
    return (f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" dominant-baseline="central" '
            f'font-family="Inter" font-weight="{weight}" font-size="{size_mm * S * 0.95:.1f}" fill="{fill}">{s}</text>')


def device_front(ox, oy):
    """Front of the cup (water side). Device coords: X right, Y up; mockup origin at device centre."""
    X = lambda x: ox + x * S  # noqa: E731
    Y = lambda y: oy - y * S  # noqa: E731
    g = [rrect(ox, oy, E.OUT_W * S, E.OUT_L * S, E.OUT_R * S, fill=P["foam"], stroke="#b8c4cc", stroke_width=1.5)]
    # faint electrodes seen through a translucent cup (illustrative)
    for k in range(1, 7):
        _, yc = E.pcb_to_dev(19, 46.5 + (6 - k) * 10)
        g.append(rrect(X(0), Y(yc), 30 * S, 9 * S, 2, fill="#dfe8ee"))
    _, yref = E.pcb_to_dev(19, 35)
    g.append(rrect(X(0), Y(yref), 30 * S, 6 * S, 2, fill="#e6edf2"))
    _, yl = E.pcb_to_dev(19, 7.5)
    _, yw = E.pcb_to_dev(19, 20.5)
    g.append(mark(X(0), Y(yl), 9.0))
    g.append(text(X(0), Y(yw), B.NAME, 7.5))
    _, ya = E.pcb_to_dev(19, 42)
    for side in (-1, 1):
        xt = side * (E.OUT_W / 2 - 4.6)
        g.append(f'<polygon fill="{P["tide"]}" points="{X(xt):.1f},{Y(ya):.1f} {X(xt + side * 2.6):.1f},{Y(ya + 1.6):.1f} '
                 f'{X(xt + side * 2.6):.1f},{Y(ya - 1.6):.1f}"/>')
    _, yw2 = E.pcb_to_dev(19, 107)
    g.append(rrect(X(0), Y(yw2), E.WIN_W * S, E.WIN_H * S, 4, fill="#d3dee6"))
    return "".join(g)


def device_back(ox, oy):
    X = lambda x: ox + x * S  # noqa: E731
    Y = lambda y: oy - y * S  # noqa: E731
    g = [rrect(ox, oy, E.OUT_W * S, E.OUT_L * S, E.OUT_R * S, fill=P["foam"], stroke="#b8c4cc", stroke_width=1.5),
         rrect(ox, oy, (E.CAV_W - 0.2) * S, (E.CAV_L - 0.2) * S, (E.CAV_R - 0.1) * S, fill=P["tide"])]
    white = "#F5F9FC"
    _, yl = E.pcb_to_dev(19, 10)
    _, yw = E.pcb_to_dev(19, 21)
    _, yt = E.pcb_to_dev(19, 27.5)
    g.append(mark(X(0), Y(yl), 8.0, fill=white, water=P["aqua"]))
    g.append(text(X(0), Y(yw), B.NAME, 7.0, fill=white))
    g.append(text(X(0), Y(yt), B.TAGLINE, 2.8, 500, fill=white))
    _, yc = E.pcb_to_dev(19, 70)
    for r in (4.0, 8.5, 13.0):
        g.append(f'<circle cx="{X(0):.1f}" cy="{Y(yc):.1f}" r="{r * S:.1f}" fill="none" stroke="{white}" stroke-width="{0.7 * S:.1f}"/>')
    g.append(text(X(0), Y(yc), "Qi", 3.2, fill=white))
    g.append(text(X(0), Y(yc - 17), "charge this side", 2.8, 500, fill=white))
    _, yr = E.pcb_to_dev(19, 106)
    g.append(text(X(0), Y(yr), "Li-ion 3.7 V 500 mAh   IP68   rev A", 2.2, 500, fill=white))
    for sy in E.SCREW_Y:  # screw heads on the sides (seen edge-on: small marks)
        for side in (-1, 1):
            g.append(f'<rect x="{X(side * E.OUT_W / 2) - 2:.1f}" y="{Y(sy) - 4:.1f}" width="4" height="8" fill="#9aa7b0"/>')
    return "".join(g)


def bracket_front(ox, oy):
    X = lambda x: ox + x * S  # noqa: E731
    Y = lambda y: oy - y * S  # noqa: E731
    iw = E.OUT_W + 2 * E.BR_GAP
    ow = iw + 2 * E.BR_WALL
    y0 = -E.OUT_L / 2 - 2.0
    g = [f'<circle cx="{X(0):.1f}" cy="{Y(ky):.1f}" r="{20 * S:.1f}" fill="#d9e3e9"/>'
         for ky in (y0 + 18.0, y0 + E.BR_L - 18.0)]           # suction cups behind the plate
    g.append(rrect(X(0), Y(y0 + E.BR_L / 2), ow * S, E.BR_L * S, 3 * S, fill=P["tide"]))
    for ky in (y0 + 18.0, y0 + E.BR_L - 18.0):
        g.append(rrect(X(0), Y(ky + E.KEY_SLIDE / 2), (E.KEY_HEAD_D + 1) * S, (E.KEY_SLIDE + E.KEY_HEAD_D + 1) * S,
                       (E.KEY_HEAD_D + 1) * S / 2, fill="#174f80"))
    for wy in (y0 + 38.0, y0 + 48.0):
        g.append(rrect(X(0), Y(wy), 35 * S, 5 * S, 2.5 * S, fill="#174f80"))
    return "".join(g)


def mockup(path):
    W, H = 760, 620
    cy = H / 2 + 10
    body = [f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
            device_front(150, cy), device_back(380, cy), bracket_front(610, cy + 0)]
    labels = [(150, "front (water side)"), (380, "back (Qi side)"), (610, "tub bracket + 40 mm cups")]
    for x, s in labels:
        body.append(f'<text x="{x}" y="28" text-anchor="middle" font-family="Inter" font-weight="500" '
                    f'font-size="15" fill="{P["deep"]}">{s}</text>')
    # palette chips
    for i, (k, v) in enumerate(P.items()):
        x = 40 + i * 120
        body.append(f'<rect x="{x}" y="{H - 34}" width="18" height="18" rx="4" fill="{v}" stroke="#cbd5dc"/>')
        body.append(f'<text x="{x + 26}" y="{H - 20}" font-family="Inter" font-size="12" fill="{P["deep"]}">{k} {v}</text>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{"".join(body)}</svg>'
    with open(path.replace(".png", ".svg"), "w") as f:
        f.write(svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=path, output_width=W * 2)


def cad_lines(path):
    """Line drawings of the real 3-D faces (deboss visible)."""
    cup, plug = E.make_cup(), E.make_plug()
    tmp = []
    for name, wp, d in (("f", cup, (0, 0, -1)), ("b", plug, (0, 0, 1))):
        svg = f"/tmp/_brand_{name}.svg"
        cq.exporters.export(wp, svg, opt={"projectionDir": d, "showHidden": False, "strokeWidth": 0.15,
                                          "width": 300, "height": 760, "marginLeft": 10, "marginTop": 10})
        png = svg.replace(".svg", ".png")
        cairosvg.svg2png(url=svg, write_to=png, output_width=300, background_color="white")
        tmp.append(png)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(6.4, 7.4))
    for a, p, t in zip(ax, tmp, ("cup, front face (CAD)", "plug, back face (CAD)")):
        a.imshow(mpimg.imread(p)); a.set_axis_off(); a.set_title(t, fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def main():
    B.logo_svg(os.path.join(IMG, "brand_logo.svg"))
    cairosvg.svg2png(url=os.path.join(IMG, "brand_logo.svg"), write_to=os.path.join(IMG, "brand_logo.png"),
                     output_width=900, background_color="white")
    mockup(os.path.join(IMG, "brand_mockup.png"))
    cad_lines(os.path.join(IMG, "brand_cad_faces.png"))
    print("wrote docs/img/brand_logo.svg/.png, brand_mockup.svg/.png, brand_cad_faces.png")


if __name__ == "__main__":
    main()
