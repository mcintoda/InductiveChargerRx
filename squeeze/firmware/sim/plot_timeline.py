#!/usr/bin/env python3
"""Before/after timeline of one scenario: squeezes, what the other person felt, and the LEDs.
    python3 plot_timeline.py child_wakes 128 146 ../../docs/img/sim_child_wakes.png"""
import csv
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

name, t0, t1, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
COL = {"blue": "#2f7fe0", "orange": "#ff8a1c", "red": "#d62f2f", "green": "#2fbf55", "white": "#bbbbbb"}
fig, axs = plt.subplots(2, 1, figsize=(11, 4.6), sharex=True)
for ax, tag in zip(axs, ("before", "after")):
    ev = list(csv.reader(open(f"out/{tag}/{name}.events.csv")))[1:]
    rows = {"child squeezes": 3, "parent feels": 2, "child LED": 1, "parent LED": 0}
    for r in ev:
        if r[2] == "squeeze_planned" and r[1] == "B":
            t, d = float(r[3]), float(r[4])
            ax.barh(3, d, left=t, height=0.6, color="#ff8a1c")
    start = None
    for r in ev:
        if r[1] == "A" and r[2] == "felt_start": start = float(r[0])
        if r[1] == "A" and r[2] == "felt_end" and start is not None:
            ax.barh(2, float(r[0]) - start, left=start, height=0.6, color="#555"); start = None
    for unit, y in (("B", 1), ("A", 0)):
        led = [(float(r[0]), r[3]) for r in ev if r[1] == unit and r[2] == "led"]
        led.append((t1, "off"))
        for (ta, s), (tb, _) in zip(led, led[1:]):
            c = s.split(":")[0]
            if c != "off" and tb > t0 and ta < t1:
                lvl = {"faint": 0.35, "dim": 0.55, "mid": 0.8, "bright": 1.0}.get(s.split(":")[1], 0.5)
                ax.barh(y, tb - ta, left=ta, height=0.6, color=COL.get(c, "#999"), alpha=lvl, linewidth=0)
    ax.set_yticks(list(rows.values())); ax.set_yticklabels(list(rows.keys()), fontsize=8)
    ax.set_xlim(t0, t1); ax.set_ylim(-0.6, 3.6); ax.grid(axis="x", lw=0.3)
    ax.set_title(f"{tag}: the child squeezes 3 times while both units sleep, then 3 times again", fontsize=9, loc="left")
axs[-1].set_xlabel("time (s)", fontsize=8)
fig.tight_layout(); fig.savefig(out, dpi=130)
print("wrote", out)
