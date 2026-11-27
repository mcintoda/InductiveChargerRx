"""Plot the drain curves in compare.json (run compare.py first) to docs/img/sim_drain_curves.png."""
import json, os, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
here = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(here, "compare.json")))["curves"]
cols = {"v3 grooves, arm on stone": "#257de0", "v3 grooves, 1 mm tape under": "#f47230",
        "v4 comb inlet (slots to stone)": "#00b894", "cloth wick (microfiber)": "#f2a600"}
labels = {"v3 grooves, arm on stone": "grooves, no comb, arm on stone", "v3 grooves, 1 mm tape under": "grooves, 1 mm tape under arm",
          "v4 comb inlet (slots to stone)": "v4 comb inlet", "cloth wick (microfiber)": "cloth wick"}
fig, ax = plt.subplots(figsize=(10, 5.6))
for k, (t, V) in d.items():
    ax.plot(list(t) + [60], list(V) + [V[-1]], color=cols[k], lw=2, label=labels[k])
ax.set_xlim(0, 60); ax.set_ylim(0, 50); ax.grid(axis="y", color="#e6e6e6"); ax.spines[["top", "right"]].set_visible(False)
ax.set_xlabel("minutes after the shower"); ax.set_ylabel("water left on the curb (mL)")
ax.set_title('Simulated drain of a 46 mL puddle (3 mm deep over 3" x 8"), nylon wetted (45° contact angle)', fontsize=11, loc="left")
ax.legend(frameon=False, loc="upper right")
plt.tight_layout(); plt.savefig(os.path.join(here, "..", "docs", "img", "sim_drain_curves.png"), dpi=130)
