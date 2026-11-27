"""Stage 2: does the clip drain the puddle, and how fast?
Groove version: steady capillary/gravity flow along 14 open V-grooves
(arm -> bend -> leg -> drip tip), groove conductance from the Stokes solver.
Wick version: saturated Darcy flow in the fabric strip (capillary siphon).
"""
import numpy as np, json
from groove_flow import conductance, grid

g, rho = 9.81, 1000.0
mu = 0.8e-3                       # water ~30 C (cools on the curb)
W, D = 1.0e-3, 1.3e-3             # groove: width at surface, depth
alpha = np.arctan(W / 2 / D)      # V half-angle (21 deg)
r_tip = 0.15e-3                   # MJF rounds the bottom of the V
N = 13                            # grooves (2.0 mm pitch)
L_arm, L_arc, R_arc, L_leg = 48.8e-3, 7.8e-3, 4.95e-3, 31e-3
p_drop = 55.0                     # Pa needed to grow a drop at the tip before it falls

def v_masks(X, Y):
    inV = np.abs(X) < Y * np.tan(alpha)
    yc = r_tip / np.sin(alpha)    # rounded tip: circle tangent to both walls
    below = Y < yc
    tipcut = below & ((X**2 + (Y - yc)**2) > r_tip**2) & (Y < yc - r_tip * np.sin(alpha) + 1e-12)
    inV &= ~tipcut
    inV &= Y < D
    return inV

def G_of_p(p, theta, gamma):
    """conductance (m^4) of one groove whose liquid is at pressure p (Pa, <= 0 => suction)."""
    beta_max = np.pi / 2 - alpha - theta
    if p >= 0:
        R = np.inf; liquid_top = lambda X, Y: Y < D          # full groove, flat meniscus
        ymax = D
    else:
        if beta_max <= 0: return 0.0                          # walls not wettable enough: groove empties
        R = gamma / -p
        b_pin = W / 2
        if R * np.sin(beta_max) >= b_pin:                     # meniscus pinned at the ridges, sagging
            beta = np.arcsin(b_pin / R); yb = D
        else:                                                  # meniscus recedes into the V
            beta = beta_max; yb = R * np.sin(beta) / np.tan(alpha)
        yc = yb + R * np.cos(beta)
        liquid_top = lambda X, Y: (Y < yb) & (Y < yc - np.sqrt(np.maximum(R**2 - X**2, 0)))
        ymax = yb
        if yb < D and yb < 1.2 * r_tip / np.sin(alpha): return 0.0   # receded into the rounded tip: disconnected
    h = max(min(ymax, W) / 70, 4e-6)
    (X, Y), h = grid(-W / 2, W / 2, 0, ymax + h, h)
    inV = v_masks(X, Y)
    liquid = inV & liquid_top(X, Y)
    solid = ~v_masks(X, Y + 0) & (Y < D)                      # groove walls
    solid |= (Y < 0)
    if liquid.sum() < 30: return 0.0
    return conductance(liquid, solid, h)

def G_table(theta, gamma):
    ps = np.concatenate([[50.0, 0.0], -np.geomspace(1, 900, 28)])
    Gs = np.array([G_of_p(p, theta, gamma) for p in ps])
    order = np.argsort(ps); return ps[order], Gs[order]

def max_flow(p_in, tab):
    ps, Gs = tab
    G = lambda p: np.interp(p, ps, Gs, left=0.0, right=Gs[-1])
    # path: (length, dz/ds) segments, integrate p(s) for a trial Q
    segs = [(L_arm, 0.0), (L_arc, -R_arc / L_arc), (L_leg, -1.0)]
    def outlet_p(Q):
        p = p_in
        for L, dzds in segs:
            n = 400; ds = L / n
            for _ in range(n):
                Gp = G(p)
                if Gp <= 0: return -np.inf
                p += (-mu * Q / (N * Gp) - rho * g * dzds) * ds
                if p < ps[0] or G(p) <= 0: return -np.inf
        return p
    lo, hi = 0.0, 1e-6
    if outlet_p(1e-15) < p_drop: return 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        (lo, hi) = (mid, hi) if outlet_p(mid) >= p_drop else (lo, mid)
    return lo

def puddle_drain(Qfun, h0, h_rec, area, hours=48):
    """pinned puddle thins to the receding depth, then shrinks at that depth toward the clip."""
    V = area * h0; t = 0.0; dt = 30.0; out = [(0, V)]
    while V > 1e-9 and t < hours * 3600:
        h = max(min(V / area, h0), h_rec) if V / area > h_rec else h_rec
        Q = Qfun(h); 
        if Q <= 0: break
        V -= Q * dt; t += dt; out.append((t, max(V, 0)))
    return np.array(out)

if __name__ == "__main__":
    area, h0, h_rec = 0.076 * 0.200, 3.0e-3, 1.6e-3      # 3" x 8" puddle, 3 mm deep -> 46 mL
    results = {"puddle_mL": area * h0 * 1e6, "grooves": {}, "wick": {}}
    cases = [("soapy film", np.radians(25), 0.032), ("well wetted", np.radians(45), 0.060),
             ("borderline", np.radians(62), 0.072), ("as-printed nylon", np.radians(78), 0.072)]
    for tape in (0.0, 1.0e-3):
        z_floor, z_top = 1.3e-3 + tape, 2.6e-3 + tape
        for name, th, gam in cases:
            tab = G_table(th, gam)
            def Qg(h, tab=tab, th=th):
                wettable = th < np.pi / 2 - alpha
                if h < (z_floor + 0.1e-3 if wettable else z_top): return 0.0
                return max_flow(rho * g * (h - z_top), tab)
            curve = puddle_drain(Qg, h0, h_rec, area)
            left = curve[-1, 1]
            key = f"{name} (theta {np.degrees(th):.0f} deg), tape {tape*1e3:.0f} mm"
            results["grooves"][key] = dict(
                rate_full_mL_h=Qg(h0) * 3.6e9, rate_receding_mL_h=Qg(h_rec) * 3.6e9,
                hours=curve[-1, 0] / 3600, left_mL=left * 1e6,
                t=(curve[::20, 0] / 3600).tolist(), V=(curve[::20, 1] * 1e6).tolist())
            print(f"GROOVES {key:45s} {Qg(h0)*3.6e9:7.2f} mL/h  ->  {left*1e6:5.1f} mL left after {curve[-1,0]/3600:5.1f} h")
    # fabric wick: saturated capillary siphon, Darcy flow
    L_w = 0.015 + 0.057 + 0.008 + 0.040 + 0.010
    for k, label in ((3e-11, "dense microfiber (low)"), (1e-10, "microfiber (typical)"), (4e-10, "felt / capillary mat")):
        for t_w in (1.2e-3, 2.5e-3):
            A = 0.012 * t_w
            Qw = lambda h: k * A * rho * g * (0.050 + h) / (mu * L_w) if h > 0.15e-3 else 0.0
            curve = puddle_drain(Qw, h0, 0.15e-3, area)     # fabric on the stone pulls the puddle down to a film
            key = f"{label}, {t_w*1e3:.1f} mm thick"
            results["wick"][key] = dict(rate_mL_h=Qw(h0) * 3.6e9, hours=curve[-1, 0] / 3600, left_mL=curve[-1, 1] * 1e6,
                                        t=(curve[::20, 0] / 3600).tolist(), V=(curve[::20, 1] * 1e6).tolist())
            print(f"WICK    {key:45s} {Qw(h0)*3.6e9:7.2f} mL/h  ->  {curve[-1,1]*1e6:5.1f} mL left after {curve[-1,0]/3600:5.1f} h")
    json.dump(results, open("results.json", "w"))
