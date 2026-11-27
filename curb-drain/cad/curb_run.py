"""Long-run curb drain (e.g. 3 ft) in drop-in dovetailed sections for JLC3DP MJF PA12.
Same cross-section as curb_drain.scad v4 (comb inlet, 2.0 mm groove pitch), swept along the curb.
Coordinates (mm): x along the curb, y across it (0 = shower-side edge, + toward the glass), z up (0 = curb top).
Usage: python3 curb_run.py [total_length_mm] [max_section_mm]
"""
import math, sys
import numpy as np, trimesh
from manifold3d import Manifold, CrossSection, FillRule

# ---- fit to the curb (same as curb_drain.scad) ----
PAD, RE, DROP = 66.0, 3.0, 40.0          # arm length, curb edge radius, leg length
# ---- section / profile ----
T, CW, CD, PITCH, RTIP = 2.6, 1.0, 1.3, 2.0, 0.15
FEATHER_LEN, FEATHER_MIN, COMB_LEN = 12.0, 1.0, 8.0
TOOTH_PITCH, TOOTH_H = 24.0, 10.0          # drip sawtooth along the leg bottom
CH = 1.4                                   # chamfer on the two outer ends
# ---- joint ----
TAB_LEN, TAB_ROOT, TAB_TIP = 6.0, 14.0, 20.0   # dovetail on the arm, in plan view
CLEAR_SIDE, CLEAR_END = 0.3, 0.5               # JLC: 0.2-0.4 mm for assembled parts; end slack for expansion
TAB_YC = (RE + PAD - FEATHER_LEN) / 2

ALPHA = math.atan((CW / 2) / CD)

def groove_strip(L, start_margin, end_margin):
    """2D outline (u along curb, v thickness 0..T) with V-grooves cut into the v=T face."""
    first = start_margin + CW / 2
    centers = list(np.arange(first, L - end_margin - CW / 2 + 1e-9, PITCH))
    top = []
    yc = (T - CD) + RTIP / math.sin(ALPHA)
    for c in reversed(centers):            # walk right-to-left along the top face
        top.append((c + CW / 2, T))
        for k in range(7):
            a = (2 * math.pi - ALPHA) - (math.pi - 2 * ALPHA) * k / 6
            top.append((c + RTIP * math.cos(a), yc + RTIP * math.sin(a)))
        top.append((c - CW / 2, T))
    pts = [(0, 0), (L, 0), (L, T)] + top + [(0, T)]
    return pts, centers

def section(L, left_end, right_end):
    """left_end/right_end: 'outer' (chamfered end of the run) or 'joint'."""
    m_l = 1.5 if left_end == "joint" else 2.6
    m_r = 1.5 if right_end == "joint" else 2.6
    pts, centers = groove_strip(L, m_l, m_r)
    cs = CrossSection([pts], FillRule.EvenOdd)
    eps = 0.02
    arm = Manifold.extrude(cs, PAD - RE + eps).rotate((90, 0, 0)).translate((0, PAD, 0))
    cs_t = CrossSection([[(RE + v, u) for u, v in pts]], FillRule.EvenOdd)
    arc = Manifold.revolve(cs_t, 96, 90).transform(np.array([[0, 0, 1, 0], [0, -1, 0, RE], [1, 0, 0, -RE]], float))
    leg = Manifold.extrude(cs, DROP - RE + eps).rotate((180, 0, 0)).translate((0, 0, -RE + eps))
    body = arm + arc + leg

    big = 1000.0
    # feathered leading edge
    wedge = CrossSection([[(PAD - FEATHER_LEN, T), (PAD, FEATHER_MIN), (PAD + 5, FEATHER_MIN), (PAD + 5, T + 5), (PAD - FEATHER_LEN, T + 5)]], FillRule.EvenOdd)
    body -= Manifold.extrude(wedge, big).rotate((90, 0, 90)).translate((-10, 0, 0))
    # comb inlet: slots through to the stone
    slots = CrossSection([[(c - CW / 2, PAD - COMB_LEN), (c + CW / 2, PAD - COMB_LEN), (c + CW / 2, PAD + 1), (c - CW / 2, PAD + 1)] for c in centers], FillRule.EvenOdd)
    body -= Manifold.extrude(slots, T + 2).translate((0, 0, -1))
    # sawtooth drip edge on the leg
    n_t = max(1, round(L / TOOTH_PITCH)); P = L / n_t
    saw = [(-50, 50)]
    for k in range(n_t):
        saw += [(k * P, -DROP + TOOTH_H), ((k + 0.5) * P, -DROP)]
    saw += [(L, -DROP + TOOTH_H), (L + 50, -DROP + TOOTH_H), (L + 50, 50)]
    keep = Manifold.extrude(CrossSection([saw], FillRule.EvenOdd), big).rotate((90, 0, 0)).translate((0, big / 2, 0))
    body = body ^ keep
    # chamfers on the top edges of the arm at the outer ends of the run
    for end in ("l", "r"):
        if (left_end if end == "l" else right_end) != "outer": continue
        x, sgn = (0.0, 1) if end == "l" else (L, -1)
        tri = CrossSection([[(x - sgn, T - CH - 1), (x - sgn, T + 2), (x + sgn * (CH + 3), T + 2)]], FillRule.EvenOdd)
        body -= Manifold.extrude(tri, PAD - RE).rotate((90, 0, 0)).translate((0, PAD, 0))
    # dovetail tab on the right, socket on the left (plan view, full arm thickness)
    def trap(x0, depth, w_root, w_tip):
        return [(x0, TAB_YC - w_root / 2), (x0 + depth, TAB_YC - w_tip / 2), (x0 + depth, TAB_YC + w_tip / 2), (x0, TAB_YC + w_root / 2)]
    if right_end == "joint":
        tab = Manifold.extrude(CrossSection([trap(L - 0.01, TAB_LEN, TAB_ROOT, TAB_TIP)], FillRule.EvenOdd), T)
        body += tab
    if left_end == "joint":
        d = TAB_LEN + CLEAR_END
        wr = TAB_ROOT + 2 * CLEAR_SIDE; wt = TAB_TIP + 2 * CLEAR_SIDE + (TAB_TIP - TAB_ROOT) / TAB_LEN * CLEAR_END
        sock = CrossSection([[(-1, TAB_YC - wr / 2 - (TAB_ROOT - TAB_TIP) / TAB_LEN / 2), (d, TAB_YC - wt / 2), (d, TAB_YC + wt / 2), (-1, TAB_YC + wr / 2 + (TAB_ROOT - TAB_TIP) / TAB_LEN / 2)]], FillRule.EvenOdd)
        body -= Manifold.extrude(sock, T + 2).translate((0, 0, -1))
    return body

def to_stl(man, path):
    mesh = man.to_mesh()
    tm = trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts), process=True)
    tm.export(path)
    return tm

if __name__ == "__main__":
    total = float(sys.argv[1]) if len(sys.argv) > 1 else 914.4
    max_sec = float(sys.argv[2]) if len(sys.argv) > 2 else 350.0
    n = math.ceil(total / max_sec); L = total / n
    kinds = {"start": ("outer", "joint"), "middle": ("joint", "joint"), "end": ("joint", "outer")}
    plan = ["start"] + ["middle"] * (n - 2) + ["end"] if n > 1 else []
    print(f"{total:.1f} mm run -> {n} sections of {L:.1f} mm: {plan}")
    for kind in dict.fromkeys(plan):
        tm = to_stl(section(L, *kinds[kind]), f"curb_run_{kind}.stl")
        print(f"{kind:7s} watertight={tm.is_watertight} vol={tm.volume/1000:.1f} cm3 bbox={np.round(tm.bounds,2).tolist()}")
