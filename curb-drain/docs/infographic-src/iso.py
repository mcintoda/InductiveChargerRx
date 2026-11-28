"""Isometric drawings of the curb drain strip, computed from the real dimensions.

Coordinates (mm): x along the curb, y across it (0 = shower-side edge, + toward the glass), z up (0 = curb top).
The viewer sits on the shower side, above, looking from the +x end, so the visible faces are
top (+z), front (-y) and end (+x). Shapes are drawn back to front (painter's order).
"""
import math

C30 = math.cos(math.radians(30))

# ---- geometry (same values as cad/curb_run.py and the measured curb) ----
T, CW, PITCH = 2.6, 1.0, 2.0
PAD, RE = 59.0, 3.0
FEATHER_Y = PAD - 12.0          # top starts tapering here
COMB_Y = PAD - 8.0              # comb slots from here to PAD
LEG_TOP = -RE
VALLEY, TIP, TIP_R = -22.0, -32.0, 1.5
SEC_L, N_SEC = 304.8, 3
TOOTH_P = SEC_L / round(SEC_L / 24.0)
TAB_LEN, TAB_ROOT, TAB_TIP, CLR_SIDE, CLR_END = 6.0, 14.0, 20.0, 0.3, 0.5
TAB_YC = (RE + PAD - 12.0) / 2
SLAB, OVERHANG, FLOOR = 19.0, 12.7, -19.0 - 44.5
GLASS_Y, GLASS_T, BEAD_W = 66.7, 10.0, 4.8


def f(v):
    return f"{v:.2f}"


def proj(p):
    x, y, z = p
    return ((x + y) * C30, (x - y) * 0.5 - z)


class Scene:
    def __init__(self, scale):
        self.s = scale
        self.items = []   # (kind, payload)

    def poly(self, pts, cls, style=""):
        self.items.append(("poly", ([proj(p) for p in pts], cls, style)))

    def line(self, a, b, cls):
        self.items.append(("line", (proj(a), proj(b), cls)))

    def polyline(self, pts, cls):
        self.items.append(("pline", ([proj(p) for p in pts], cls)))

    def drop(self, p, size=1.0):
        self.items.append(("drop", (proj(p), size)))

    def label(self, p, dx, dy, text, sub=None, anchor="start"):
        self.items.append(("label", (proj(p), dx, dy, text, sub, anchor)))

    def svg(self, aria, minw, pad=14):
        s = self.s
        xs, ys = [], []
        for kind, d in self.items:
            if kind == "poly":
                xs += [p[0] * s for p in d[0]]; ys += [p[1] * s for p in d[0]]
            elif kind in ("line",):
                xs += [d[0][0] * s, d[1][0] * s]; ys += [d[0][1] * s, d[1][1] * s]
            elif kind == "label":
                (px, py), dx, dy, text, sub, anchor = d
                tx, ty = px * s + dx, py * s + dy
                w = max(len(text), len(sub or "")) * 7.2
                x0 = tx - w if anchor == "end" else (tx - w / 2 if anchor == "middle" else tx)
                xs += [px * s, x0, x0 + w]; ys += [py * s, ty - 14, ty + (20 if sub else 6)]
        x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
        out = []
        for kind, d in self.items:
            if kind == "poly":
                pts, cls, style = d
                out.append(f'<polygon class="{cls}" points="{" ".join(f(x*s - x0)+","+f(y*s - y0) for x, y in pts)}" {style}/>')
            elif kind == "line":
                a, b, cls = d
                out.append(f'<line class="{cls}" x1="{f(a[0]*s-x0)}" y1="{f(a[1]*s-y0)}" x2="{f(b[0]*s-x0)}" y2="{f(b[1]*s-y0)}"/>')
            elif kind == "pline":
                pts, cls = d
                out.append(f'<polyline class="{cls}" points="{" ".join(f(x*s - x0)+","+f(y*s - y0) for x, y in pts)}"/>')
            elif kind == "drop":
                (px, py), k = d
                cx, cy = px * s - x0, py * s - y0
                out.append(f'<path class="drop" d="M{f(cx)},{f(cy-6*k)} q{f(4.5*k)},{f(6*k)} 0,{f(9*k)} q{f(-4.5*k)},{f(-3*k)} 0,{f(-9*k)}z"/>')
            elif kind == "label":
                (px, py), dx, dy, text, sub, anchor = d
                ax, ay = px * s - x0, py * s - y0
                tx, ty = ax + dx, ay + dy
                out.append(f'<line class="lead" x1="{f(ax)}" y1="{f(ay)}" x2="{f(tx)}" y2="{f(ty)}"/>')
                out.append(f'<circle class="leaddot" cx="{f(ax)}" cy="{f(ay)}" r="2.5"/>')
                off = 4 if anchor == "start" else (-4 if anchor == "end" else 0)
                ly = ty + 4 if dy >= 0 else ty - (14 if sub else 2)
                out.append(f'<text class="lbl" x="{f(tx+off)}" y="{f(ly)}" text-anchor="{anchor}">{text}</text>')
                if sub:
                    out.append(f'<text class="lbl small muted" x="{f(tx+off)}" y="{f(ly+16)}" text-anchor="{anchor}">{sub}</text>')
        w, h = x1 - x0, y1 - y0
        return f'<svg viewBox="0 0 {f(w)} {f(h)}" role="img" aria-label="{aria}" style="min-width:{minw}px">{"".join(out)}</svg>'


# ---- strip helpers ----
def sec_start(x):
    return math.floor(x / SEC_L + 1e-9) * SEC_L


def tooth_z(x, rounded=True):
    local = (x - sec_start(x)) % TOOTH_P
    frac = local / TOOTH_P
    z = TIP + (VALLEY - TIP) * abs(frac - 0.5) * 2
    if rounded:
        dx = local - TOOTH_P / 2
        phi = math.atan((TOOTH_P / 2) / (VALLEY - TIP))
        zc = TIP + TIP_R / math.sin(phi)
        if abs(dx) < TIP_R:
            z = max(z, zc - math.sqrt(TIP_R ** 2 - dx ** 2))
    return z


def top_z(y):
    if y <= FEATHER_Y:
        return T
    return T - (T - 1.0) * (y - FEATHER_Y) / (PAD - FEATHER_Y)


def groove_centers(x0, x1):
    out = []
    for k in range(N_SEC):
        a = k * SEC_L
        first = a + (2.6 if k == 0 else 1.5) + CW / 2
        c = first
        while c <= a + SEC_L - (2.6 if k == N_SEC - 1 else 1.5) - CW / 2 + 1e-9:
            if x0 <= c <= x1:
                out.append(c)
            c += PITCH
    return out


BEND = [math.radians(90 + 90 * i / 6) for i in range(7)]


def bend_pt(a, r=RE + T):
    return (RE + r * math.cos(a), -RE + r * math.sin(a))


def strip(sc, x0, x1, lift=0.0, detail=True, end_face=True, socket=False, tab=False, notch_for=None):
    z0 = lift
    # top surface (flat + feather), with an optional dovetail socket notched out of the flat part
    if socket:
        a, d = x0, TAB_LEN + CLR_END
        wr, wt = TAB_ROOT / 2 + CLR_SIDE, TAB_TIP / 2 + CLR_SIDE + (TAB_TIP - TAB_ROOT) / TAB_LEN / 2 * CLR_END
        flat = [(x0, RE), (x1, RE), (x1, FEATHER_Y), (x0, FEATHER_Y), (x0, TAB_YC + wr), (a + d, TAB_YC + wt), (a + d, TAB_YC - wt), (x0, TAB_YC - wr)]
        # what you see down the socket: the opening, then its inner wall, then the top surface around it
        notch = [(x0, TAB_YC - wr), (a + d, TAB_YC - wt), (a + d, TAB_YC + wt), (x0, TAB_YC + wr)]
        sc.poly([(x, y, z0) for x, y in notch], "slotcut")
        sc.poly([(x0, TAB_YC + wr, z0), (a + d, TAB_YC + wt, z0), (a + d, TAB_YC + wt, T + z0), (x0, TAB_YC + wr, T + z0)], "n-front")
        sc.poly([(x, y, T + z0) for x, y in flat], "n-top")
    else:
        sc.poly([(x0, RE, T + z0), (x1, RE, T + z0), (x1, FEATHER_Y, T + z0), (x0, FEATHER_Y, T + z0)], "n-top")
    sc.poly([(x0, FEATHER_Y, T + z0), (x1, FEATHER_Y, T + z0), (x1, PAD, 1.0 + z0), (x0, PAD, 1.0 + z0)], "n-top")
    cs = groove_centers(x0 + 0.01, x1 - 0.01)
    if detail:
        for c in cs:   # comb slots: open to whatever is below
            pts = [(c - CW / 2, COMB_Y), (c + CW / 2, COMB_Y), (c + CW / 2, PAD), (c - CW / 2, PAD)]
            sc.poly([(x, y, top_z(y) + z0) for x, y in pts], "slotcut")
    else:
        sc.poly([(x0, COMB_Y, top_z(COMB_Y) + z0), (x1, COMB_Y, top_z(COMB_Y) + z0), (x1, PAD, 1.0 + z0), (x0, PAD, 1.0 + z0)], "combtone")
    # groove lines on the arm
    for c in cs:
        if socket and c < x0 + TAB_LEN + CLR_END + 0.2:
            ys = [(RE, TAB_YC - TAB_TIP / 2 - 0.6), (TAB_YC + TAB_TIP / 2 + 0.6, COMB_Y)]
        else:
            ys = [(RE, COMB_Y)]
        for ya, yb in ys:
            pts = [(c, ya, top_z(ya) + z0), (c, min(yb, FEATHER_Y), T + z0)]
            if yb > FEATHER_Y:
                pts.append((c, yb, top_z(yb) + z0))
            sc.polyline(pts, "gline" if detail else "gline thin")
    # bend facets
    for i in range(6):
        a, b = BEND[i], BEND[i + 1]
        (ya, za), (yb, zb) = bend_pt(a), bend_pt(b)
        cls = ("n-top", "n-top", "n-mid", "n-mid", "n-front", "n-front")[i]
        sc.poly([(x0, ya, za + z0), (x1, ya, za + z0), (x1, yb, zb + z0), (x0, yb, zb + z0)], cls)
    for c in cs:
        sc.polyline([(c, y, z + z0) for y, z in (bend_pt(a) for a in BEND)], "gline" if detail else "gline thin")
    # leg front with the sawtooth bottom
    step = 0.25 if detail else 1.0
    n = max(2, int((x1 - x0) / step))
    bottom = [(x1 - (x1 - x0) * i / n, -T, tooth_z(x1 - (x1 - x0) * i / n, detail) + z0) for i in range(n + 1)]
    sc.poly([(x0, -T, LEG_TOP + z0), (x1, -T, LEG_TOP + z0)] + bottom, "n-front")
    for c in cs:
        sc.line((c, -T, LEG_TOP + z0), (c, -T, tooth_z(c, detail) + 0.6 + z0), "gline" if detail else "gline thin")
    # end face (+x)
    if end_face:
        prof = [(PAD, 1.0), (FEATHER_Y, T), (RE, T)]
        prof += [bend_pt(a) for a in BEND]
        prof += [(-T, tooth_z(x1 - 0.01, detail)), (0, tooth_z(x1 - 0.01, detail)), (0, -RE)]
        prof += [bend_pt(a, RE) for a in reversed(BEND)]
        prof += [(PAD, 0)]
        sc.poly([(x1, y, z + z0) for y, z in prof], "n-end")
    # dovetail tab sticking out of the +x end
    if tab:
        r0, r1 = TAB_ROOT / 2, TAB_TIP / 2
        x2 = x1 + TAB_LEN
        sc.poly([(x1, TAB_YC - r0, T + z0), (x2, TAB_YC - r1, T + z0), (x2, TAB_YC + r1, T + z0), (x1, TAB_YC + r0, T + z0)], "n-top")
        sc.poly([(x1, TAB_YC - r0, z0), (x2, TAB_YC - r1, z0), (x2, TAB_YC - r1, T + z0), (x1, TAB_YC - r0, T + z0)], "n-front")
        sc.poly([(x2, TAB_YC - r1, z0), (x2, TAB_YC + r1, z0), (x2, TAB_YC + r1, T + z0), (x2, TAB_YC - r1, T + z0)], "n-end")
    return cs


def tips_between(x0, x1):
    out = []
    for k in range(N_SEC):
        for j in range(round(SEC_L / TOOTH_P)):
            t = k * SEC_L + (j + 0.5) * TOOTH_P
            if x0 < t < x1:
                out.append(t)
    return out


def curb(sc, x0, x1, y_far=152.0, glass_h=120.0, cut_end=False, fy0=-110.0):
    # tile floor in front of the curb, then the curb body, the slab, the glass
    sc.poly([(x0, fy0, FLOOR), (x1 + 0.0, fy0, FLOOR), (x1, OVERHANG, FLOOR), (x0, OVERHANG, FLOOR)], "tile")
    t = 50.8
    xx = math.ceil(x0 / t) * t
    while xx < x1:
        sc.line((xx, fy0, FLOOR), (xx, OVERHANG, FLOOR), "tileline"); xx += t
    yy = OVERHANG - t
    while yy > fy0:
        sc.line((x0, yy, FLOOR), (x1, yy, FLOOR), "tileline"); yy -= t
    sc.poly([(x0, OVERHANG, FLOOR), (x1, OVERHANG, FLOOR), (x1, OVERHANG, -SLAB), (x0, OVERHANG, -SLAB)], "s-front")
    sc.poly([(x1, OVERHANG, FLOOR), (x1, y_far, FLOOR), (x1, y_far, -SLAB), (x1, OVERHANG, -SLAB)], "s-end" + (" cutface" if cut_end else ""))
    sc.poly([(x0, 0, 0), (x1, 0, 0), (x1, y_far, 0), (x0, y_far, 0)], "s-top")
    sc.poly([(x0, 0, -SLAB), (x1, 0, -SLAB), (x1, 0, 0), (x0, 0, 0)], "s-front")
    sc.poly([(x1, 0, -SLAB), (x1, y_far, -SLAB), (x1, y_far, 0), (x1, 0, 0)], "s-end" + (" cutface" if cut_end else ""))
    # thin water film in the gap before the bead, the bead, then the glass
    sc.poly([(x0, PAD, 0.05), (x1, PAD, 0.05), (x1, GLASS_Y - BEAD_W, 0.05), (x0, GLASS_Y - BEAD_W, 0.05)], "water")
    sc.poly([(x0, GLASS_Y - BEAD_W, 0), (x1, GLASS_Y - BEAD_W, 0), (x1, GLASS_Y, 5.0), (x0, GLASS_Y, 5.0)], "bead")
    sc.poly([(x0, GLASS_Y, glass_h), (x1, GLASS_Y, glass_h), (x1, GLASS_Y + GLASS_T, glass_h), (x0, GLASS_Y + GLASS_T, glass_h)], "glass")
    sc.poly([(x1, GLASS_Y, 0), (x1, GLASS_Y + GLASS_T, 0), (x1, GLASS_Y + GLASS_T, glass_h), (x1, GLASS_Y, glass_h)], "glass")
    sc.poly([(x0, GLASS_Y, 0), (x1, GLASS_Y, 0), (x1, GLASS_Y, glass_h), (x0, GLASS_Y, glass_h)], "glass", 'style="opacity:.55"')


def iso_run():
    L = SEC_L * N_SEC
    sc = Scene(0.80)
    curb(sc, 0, L)
    for k in range(N_SEC):
        a, b = k * SEC_L, (k + 1) * SEC_L
        strip(sc, a, b, detail=False, end_face=(k == N_SEC - 1))
    for k in range(1, N_SEC):   # joint lines and the dovetail outline seen on top
        x = k * SEC_L
        sc.polyline([(x, PAD, 1.0), (x, FEATHER_Y, T), (x, TAB_YC + TAB_ROOT / 2, T), (x + TAB_LEN, TAB_YC + TAB_TIP / 2, T),
                     (x + TAB_LEN, TAB_YC - TAB_TIP / 2, T), (x, TAB_YC - TAB_ROOT / 2, T), (x, RE, T)]
                    + [(x, y, z) for y, z in (bend_pt(a) for a in BEND)] + [(x, -T, tooth_z(x - 0.01))], "jointline")
    for t in tips_between(0, L):
        sc.drop((t, -T - 0.5, TIP - 6), 0.8)
    # dimension along the front edge of the floor
    fy = -110.0
    sc.line((0, fy, FLOOR), (L, fy, FLOOR), "dim")
    for x in (0, SEC_L, 2 * SEC_L, L):
        sc.line((x, fy - 4, FLOOR), (x, fy + 4, FLOOR), "dim")
    for k, name in enumerate(("start", "middle", "end")):
        sc.label(((k + 0.5) * SEC_L, 30, T), 0, -70 - 18 * (k % 2), f"{name} section", "304.8 mm", "middle")
    sc.label((2 * SEC_L + 3, TAB_YC, T), 40, -150, "dovetail joints", "every 304.8 mm")
    sc.label((L, GLASS_Y + 5, 90), 30, -10, "fixed glass panel", "2⅝ in from the curb edge")
    sc.label((L, 20, -9), 40, 10, "¾ in granite slab", "½ in overhang")
    sc.label((L - 0.5 * TOOTH_P, -T, TIP), 30, 34, "rounded drip teeth", "a drop point every 23 mm")
    sc.label((0.25 * L, -60, FLOOR), -10, 46, "tile floor", "1¾ in below the overhang", "end")
    sc.label((0.5 * L, fy, FLOOR), 0, 40, "914 mm (3 ft) run", None, "middle")
    return sc.svg("Isometric view of the whole 3 ft drain strip on the curb", 680)


def iso_joint():
    x0, xj, x1, lift = 282.0, SEC_L, 328.0, 22.0
    sc = Scene(7.0)
    curb(sc, x0, x1, y_far=GLASS_Y + GLASS_T, glass_h=26.0, cut_end=True, fy0=-14.0)
    strip(sc, x0, xj, detail=True, end_face=True, tab=True)
    for t in tips_between(x0, xj):
        sc.drop((t, -T - 0.4, TIP - 3.0), 1.0)
    # the next section, lifted to show the socket
    strip(sc, xj, x1, lift=lift, detail=True, end_face=True, socket=True)
    for t in tips_between(xj, x1):
        sc.drop((t, -T - 0.4, TIP + lift - 3.0), 1.0)
    # drop-in arrow
    ax, ay = xj + 3.0, TAB_YC
    sc.line((ax, ay, lift + T + 9), (ax, ay, T + 3.5), "arrow")
    sc.poly([(ax - 1.2, ay - 1.2, T + 5.5), (ax + 1.2, ay + 1.2, T + 5.5), (ax, ay, T + 3.2)], "arrowhead")
    sc.label((xj + TAB_LEN, TAB_YC - TAB_TIP / 2 + 2, T), 170, 70, "dovetail tab", "6 mm, on the end of the start section")
    sc.label((xj + 3, TAB_YC + 8.5, lift + T), -230, -40, "socket in the next section", "drops straight down onto the tab", "end")
    sc.label((x0 + 6, 30, T), -30, -60, "V-grooves", "1 mm wide, 2 mm apart", "end")
    sc.label((x0 + 9, PAD - 4, top_z(PAD - 4)), -40, -70, "comb slots", "open to the stone", "end")
    sc.label((tips_between(x0, xj)[0], -T, TIP + 0.6), -30, 50, "rounded drip teeth", "1.5 mm tip radius", "end")
    sc.label((x1, 45, -40), 40, 30, "curb (cut away)", None)
    sc.label((x1, GLASS_Y - BEAD_W / 2, 2.5), 40, -10, "silicone bead", "2.9 mm clear of the strip")
    return sc.svg("Isometric close-up of a joint between two sections", 560)


# ---- print orientation ----
def _profile_outline():
    """Closed outline of the strip's L profile in part (y, z), outer surface first."""
    prof = [(PAD, 1.0), (FEATHER_Y, T), (RE, T)]
    prof += [bend_pt(a) for a in BEND]
    prof += [(-T, VALLEY), (0, VALLEY), (0, -RE)]
    prof += [bend_pt(a, RE) for a in reversed(BEND)]
    prof += [(PAD, 0)]
    return prof


def iso_print():
    """One section standing on end on the build plate: part x (length) becomes build Z.
    World (X, Y, Z) = (part z, part y, height above the plate)."""
    H = SEC_L
    sc = Scene(1.35)
    W = lambda y, z, h: (z, y, h)
    # build plate
    sc.poly([W(-25, -45, 0), W(80, -45, 0), W(80, 20, 0), W(-25, 20, 0)], "plate")
    # visible outer faces: leg outer face, bend facets, arm top, feather (all face the viewer)
    sc.poly([W(-T, VALLEY, 0), W(-T, -RE, 0), W(-T, -RE, H), W(-T, VALLEY, H)], "n-front")
    for i in range(5, -1, -1):
        (ya, za), (yb, zb) = bend_pt(BEND[i]), bend_pt(BEND[i + 1])
        cls = ("n-top", "n-top", "n-mid", "n-mid", "n-front", "n-front")[i]
        sc.poly([W(ya, za, 0), W(yb, zb, 0), W(yb, zb, H), W(ya, za, H)], cls)
    sc.poly([W(RE, T, 0), W(FEATHER_Y, T, 0), W(FEATHER_Y, T, H), W(RE, T, H)], "n-top")
    sc.poly([W(FEATHER_Y, T, 0), W(PAD, 1.0, 0), W(PAD, 1.0, H), W(FEATHER_Y, T, H)], "n-top")
    # grooves: each one lies in a horizontal plane, exactly like the layers
    for c in groove_centers(0.0, SEC_L):
        pts = [W(-T, VALLEY + 1, c), W(-T, -RE, c)] + [W(y, z, c) for y, z in (bend_pt(a) for a in reversed(BEND))] + [W(FEATHER_Y, T, c), W(COMB_Y, top_z(COMB_Y), c)]
        sc.polyline(pts, "gline thin")
    # one layer highlighted part way up, and the top cap (the end face)
    hl = 0.62 * H
    prof = _profile_outline()
    sc.poly([W(y, z, hl) for y, z in prof], "layerhl")
    sc.poly([W(y, z, H) for y, z in prof], "n-end")
    # build direction arrow
    ay, az = 72.0, 10.0
    sc.line(W(ay, az, 0), W(ay, az, H + 25), "zarrow")
    sc.poly([W(ay - 3, az, H + 15), W(ay + 3, az, H + 15), W(ay, az, H + 30)], "zhead")
    sc.label(W(ay, az, H + 28), 16, -4, "build direction (Z)", "layers stack up")
    sc.label(W(PAD, 1.0, hl), 46, 0, "one 0.08 mm layer", "the whole L in one slice")
    sc.label(W(30, T, 0.3 * H), 60, 10, "grooves are horizontal", "parallel to the layers")
    sc.label(W(-T, -14, 0.12 * H), -24, 30, "305 mm long", "printed upright (max 360)", "end")
    return sc.svg("A section standing on end on the build plate", 520)


def print_compare():
    """2D comparison of the bend, standing vs lying flat (layer steps exaggerated)."""
    s, gap, stepmm = 7.0, 90, 1.0          # 1.0 mm drawn steps = 0.08 mm layers exaggerated 12.5x
    out = []
    def P(ox, oy, y, z): return (ox + y * s, oy - z * s)
    def polyline(pts, cls): return f'<polyline class="{cls}" points="{" ".join(f(x)+","+f(y) for x, y in pts)}"/>'
    def polygon(pts, cls): return f'<polygon class="{cls}" points="{" ".join(f(x)+","+f(y) for x, y in pts)}"/>'
    prof = [(18, T), (RE, T)] + [bend_pt(a) for a in BEND] + [(-T, -16), (0, -16), (0, -RE)] + [bend_pt(a, RE) for a in reversed(BEND)] + [(18, 0)]
    # left: standing on end, each layer is the whole profile (seen from above)
    ox, oy = 60, 100
    out.append(polygon([P(ox, oy, y, z) for y, z in prof], "layerhl"))
    out.append(polyline([P(ox, oy, 16, T + 1.6), P(ox, oy, RE, T + 1.6)] + [P(ox, oy, *bend_pt(a, RE + T + 1.6)) for a in BEND] + [P(ox, oy, -T - 1.6, -14)], "flowpath"))
    out.append(f'<text class="h3t" x="{ox - 20}" y="24">Standing on end</text>')
    out.append(f'<text class="verdict ok" x="{ox - 20}" y="44">recommended</text>')
    out.append(f'<text class="lbl small" x="{ox - 20}" y="{oy + 18*s + 6}">One layer is the whole profile, so</text>')
    out.append(f'<text class="lbl small muted" x="{ox - 20}" y="{oy + 18*s + 22}">the bend is smooth along the flow (blue).</text>')
    # right: lying flat, horizontal layers make a staircase across the bend
    ox2 = ox + 25 * s + gap
    stairs = []
    zs = [T - k * stepmm for k in range(int((T + 16) / stepmm) + 1)]
    for z in zs:   # outer surface y at each layer, quantised
        if z >= -RE:
            ang = math.asin(max(-1, min(1, (z + RE) / (RE + T))))
            y = RE - (RE + T) * math.cos(ang)
        else:
            y = -T
        stairs.append((math.floor(y / stepmm) * stepmm, z))
    pts = [(18, T)]
    for (y, z), (y2, z2) in zip(stairs, stairs[1:]):
        pts += [(y, z), (y, z2)]
    pts += [(-T, -16), (0, -16), (0, -RE)] + [bend_pt(a, RE) for a in reversed(BEND)] + [(18, 0)]
    out.append(polygon([P(ox2, oy, y, z) for y, z in pts], "n-mid"))
    for z in zs:
        out.append(polyline([P(ox2, oy, -T - 1.5, z), P(ox2, oy, 18, z)], "layerline"))
    out.append(polyline([P(ox2, oy, 16, T + 1.6), P(ox2, oy, RE, T + 1.6)] + [P(ox2, oy, *bend_pt(a, RE + T + 1.6)) for a in BEND] + [P(ox2, oy, -T - 1.6, -14)], "flowpath"))
    out.append(f'<text class="h3t" x="{ox2 - 20}" y="24">Lying flat</text>')
    out.append(f'<text class="verdict bad" x="{ox2 - 20}" y="44">works, but not ideal</text>')
    out.append(f'<text class="lbl small" x="{ox2 - 20}" y="{oy + 18*s + 6}">Horizontal layers turn the bend into a</text>')
    out.append(f'<text class="lbl small muted" x="{ox2 - 20}" y="{oy + 18*s + 22}">staircase across the flow (steps shown 12× too big).</text>')
    w, h = ox2 + 25 * s + 150, oy + 18 * s + 34
    return f'<svg viewBox="0 0 {f(w)} {f(h)}" role="img" aria-label="Bend printed standing on end versus lying flat" style="min-width:560px; max-width:760px">{"".join(out)}</svg>'
