"""Stage 3: compare designs and sensitivity to the unknowns (nylon wetting, granite pinning)."""
import numpy as np, json
from drain_model import G_table, max_flow, puddle_drain, rho, g, mu

area, h0 = 0.076 * 0.200, 3.0e-3                     # 3" x 8" puddle, 3 mm deep = 46 mL
designs = {
    "v3 grooves, arm on stone":   dict(z_floor=1.3e-3, z_top=2.6e-3),
    "v3 grooves, 1 mm tape under": dict(z_floor=2.3e-3, z_top=3.6e-3),
    "v4 comb inlet (slots to stone)": dict(z_floor=0.0, z_top=1.0e-3),
}
wettings = {"soapy (25 deg)": (25, 0.032), "wetted (45 deg)": (45, 0.060),
            "borderline (62 deg)": (62, 0.072), "as-printed (78 deg)": (78, 0.072)}
alpha_crit = 90 - np.degrees(np.arctan(0.5 / 1.3))
tabs = {k: G_table(np.radians(t), gm) for k, (t, gm) in wettings.items()}
out = {"table": [], "curves": {}}
for h_rec, pin in ((1.6e-3, "granite releases at 1.6 mm"), (1.0e-3, "granite pins down to 1.0 mm")):
    for dn, d in designs.items():
        for wn, (th, gm) in wettings.items():
            wettable = th < alpha_crit
            def Q(h):
                if wettable and h < d["z_floor"] + 0.15e-3: return 0.0
                if not wettable and h < d["z_top"]: return 0.0
                return max_flow(rho * g * (h - d["z_top"]), tabs[wn])
            c = puddle_drain(Q, h0, h_rec, area, hours=24)
            row = dict(pinning=pin, design=dn, wetting=wn, rate_mL_h=round(Q(h0) * 3.6e9),
                       left_mL=round(c[-1, 1] * 1e6, 1), minutes=round(c[-1, 0] / 60))
            out["table"].append(row); print(row)
            if wn == "wetted (45 deg)" and pin.startswith("granite releases"):
                out["curves"][dn] = [(c[:, 0] / 60).tolist(), (c[:, 1] * 1e6).tolist()]
# cloth wick, typical microfiber 2.5 mm, drains the puddle to a film regardless of pinning
k, A, Lw = 1e-10, 0.012 * 2.5e-3, 0.13
Qw = lambda h: k * A * rho * g * (0.050 + h) / (mu * Lw) if h > 0.15e-3 else 0.0
c = puddle_drain(Qw, h0, 0.15e-3, area, hours=24)
out["curves"]["cloth wick (microfiber)"] = [(c[:, 0] / 60).tolist(), (c[:, 1] * 1e6).tolist()]
print("wick", Qw(h0) * 3.6e9, c[-1, 1] * 1e6, c[-1, 0] / 60)
json.dump(out, open("compare.json", "w"))
