#!/usr/bin/env python3
"""Run the virtual bring-up and usability experiments on ./sim and print the measurements.

    make && python3 experiments.py [--tag before|after] [--only NAME]

Results: out/<tag>/results.json and a readable summary on stdout (docs/virtual-experiments.md quotes them).
"""
import argparse
import csv
import json
import os
import random
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = "sim"


def run(scn_text, name, outdir):
    path = os.path.join(outdir, name + ".txt")
    open(path, "w").write(scn_text)
    out = subprocess.run([os.path.join(HERE, SIM), path, os.path.join(outdir, name)], capture_output=True,
                         text=True, timeout=900)
    if out.returncode:
        sys.exit(f"sim failed on {name}: {out.stderr[-500:]}")
    ev = list(csv.reader(open(os.path.join(outdir, name + ".events.csv"))))[1:]
    log = open(os.path.join(outdir, name + ".log")).read()
    return ev, log, out.stdout


def scenario(name):
    return open(os.path.join(HERE, "scenarios", name + ".txt")).read()


# ---------------- event analysis ----------------
def intervals(ev, unit, start, end):
    out, cur = [], None
    for r in ev:
        if r[1] != unit:
            continue
        if r[2] == start:
            cur = float(r[0])
        elif r[2] == end and cur is not None:
            out.append((cur, float(r[0])))
            cur = None
    return out


def planned(ev, unit):
    return [tuple(map(float, r[3:6])) for r in ev if r[1] == unit and r[2] == "squeeze_planned"]


def held_ok(scn, unit, t):
    for line in scn.splitlines():
        p = line.split("#")[0].split()
        if len(p) == 4 and p[0] == unit and p[1] == "held":
            return float(p[2]) <= t < float(p[3])
    return True


def delivery(ev, scn, frm, to, window=4.0):
    """For each planned squeeze of `frm` (while held), the first felt_start on `to` within the window."""
    felt = intervals(ev, to, "felt_start", "felt_end")
    used, res = set(), []
    for (t, dur, f) in planned(ev, frm):
        if not held_ok(scn, frm, t):
            continue
        hit = next((i for i, (a, b) in enumerate(felt) if i not in used and t - 0.05 <= a <= t + window), None)
        if hit is None:
            res.append((t, None))
        else:
            used.add(hit)
            res.append((t, felt[hit][0] - t))
    return res


def leds(ev, unit, t0=0, t1=1e9):
    out = []
    for r in ev:
        if r[1] == unit and r[2] == "led" and t0 <= float(r[0]) <= t1:
            name = r[3]
            if not out or out[-1][1] != name:
                out.append((float(r[0]), name))
    return out


def led_summary(ev, unit, t0, t1):
    """Collapse breathing/brightness changes into colour episodes: [(t_start, colour, max level)]."""
    eps = []
    for t, name in leds(ev, unit, t0, t1):
        col, _, lvl = name.partition(":")
        if eps and eps[-1][1] == col:
            continue
        eps.append((round(t, 2), col, lvl))
    return eps


def kinds(ev, unit, kind):
    return [float(r[0]) for r in ev if r[1] == unit and r[2] == kind]


def summary_mah(ev, unit):
    for r in ev:
        if r[1] == unit and r[2] == "summary":
            return float(r[3])
    return None


# ---------------- experiments ----------------
def exp_bringup(outdir, R):
    ev, log, _ = run(scenario("bringup_usb"), "bringup_usb", outdir)
    R["B1_usb"] = {
        "slept_on_usb": len(kinds(ev, "A", "sleep")) > 0,
        "selftest": [l.split(") ", 1)[1] for l in log.splitlines() if "(selftest)" in l],
        "selftest_servo_moved": any(r[1] == "A" and r[2] == "servo_power" and r[3] == "1" for r in ev),
        "sensor_errors": [l for l in log.splitlines() if " E (" in l and " A " in l][:5],
        "first_log_lines": [l.strip() for l in log.splitlines() if " A " in l][:8],
        "servo_powered": len(kinds(ev, "A", "servo_power")),
        "led": led_summary(ev, "A", 0, 20),
    }
    ev, log, _ = run(scenario("bringup_nosensor"), "bringup_nosensor", outdir)
    R["B2_no_sensor"] = {
        "errors": [l.strip() for l in log.splitlines() if " A E " in l][:5],
        "still_receives": [d for _, d in delivery(ev, scenario("bringup_nosensor"), "B", "A")],
        "led_A": led_summary(ev, "A", 0, 20),
    }
    scn = scenario("bringup_pair")
    ev, log, _ = run(scn, "bringup_pair", outdir)
    pw = [(float(r[0]), r[1], r[3]) for r in ev if r[2] == "servo_power"]
    R["B3_pair"] = {
        "A_to_B": delivery(ev, scn, "A", "B"),
        "B_to_A": delivery(ev, scn, "B", "A"),
        "servo_power_events": pw[:8],
        "doze_or_sleep_times": {u: ([float(l.split()[0]) for l in log.splitlines() if f" {u} " in l and "idle:" in l]
                                    + kinds(ev, u, "sleep"))[:2] for u in "AB"},
        "mAh": {u: summary_mah(ev, u) for u in "AB"},
    }
    ev, log, _ = run(scenario("bringup_charging"), "bringup_charging", outdir)
    R["B5_charging"] = {"led_A": led_summary(ev, "A", 0, 15), "led_B": led_summary(ev, "B", 0, 15)}


def exp_usability(outdir, R, seeds=5):
    # U1 the game from sleep
    rows = []
    for s in range(seeds):
        scn = scenario("game_from_sleep") + f"\nseed {s + 1}\n"
        ev, _, _ = run(scn, f"game_{s}", outdir)
        ab, ba = delivery(ev, scn, "A", "B"), delivery(ev, scn, "B", "A")
        rows.append({"parent_to_child": ab, "child_to_parent": ba,
                     "patterns_sent": len([r for r in ev if r[2] == "pattern_sent"]),
                     "replies": len([r for r in ev if r[2] == "reply_planned"])})
    R["U1_game"] = rows
    # U2 the child starts from sleep
    scn = scenario("child_wakes")
    ev, _, _ = run(scn, "child_wakes", outdir)
    R["U2_child_wakes"] = {"delivered": delivery(ev, scn, "B", "A"), "led_B": led_summary(ev, "B", 125, 160),
                           "led_A": led_summary(ev, "A", 125, 160), "wake_A": [t for t in kinds(ev, "A", "wake") if t > 125][:3]}
    # U3 partner not holding
    scn = scenario("not_holding")
    ev, _, _ = run(scn, "not_holding", outdir)
    R["U3_not_holding"] = {"led_A": led_summary(ev, "A", 125, 200), "led_B": led_summary(ev, "B", 125, 200),
                           "A_reply_delivered": delivery(ev, scn, "A", "B")}
    # U4 quick squeeze while asleep: how often does a 0.25 s squeeze wake the unit?
    rnd = random.Random(7)
    woke, n = 0, 30
    for i in range(n):
        t = 110 + rnd.random() * 20
        scn = f"duration {t + 6:.2f}\nseed {i + 3}\nA start 0\nB start 0.4\nB squeeze {t:.3f} 0.25 8\n"
        ev, _, _ = run(scn, f"quick_{i}", outdir)
        # woke by the squeeze = the unit started calling (transmitted WAKE, type 3) within 3 s
        if any(r[1] == "B" and r[2] == "tx" and r[3] == "3" and t <= float(r[0]) <= t + 3 for r in ev):
            woke += 1
    R["U4_quick_squeeze_wakes"] = {"woke": woke, "of": n}
    # U5 overlap
    scn = scenario("overlap")
    ev, _, _ = run(scn, "overlap", outdir)
    R["U5_overlap"] = {"A_to_B": delivery(ev, scn, "A", "B"), "B_to_A": delivery(ev, scn, "B", "A")}
    # U6 out of range
    scn = scenario("out_of_range")
    ev, _, _ = run(scn, "out_of_range", outdir)
    R["U6_out_of_range"] = {"led_B": led_summary(ev, "B", 25, 60), "delivered": delivery(ev, scn, "B", "A")}
    # U7 low battery
    scn = scenario("low_battery")
    ev, log, _ = run(scn, "low_battery", outdir)
    R["U7_low_battery"] = {"A_to_B": delivery(ev, scn, "A", "B"), "led_B": led_summary(ev, "B", 0, 30),
                           "led_A": led_summary(ev, "A", 0, 30)}
    # U9 gentle squeezes (a 6-year-old): smallest force that is detected, asleep and awake
    sweep = {}
    for f in (2, 3, 4, 6, 8, 10):
        scn = f"duration 140\nA start 0\nB start 0.4\nB squeeze 120 0.4 {f}\nB squeeze 130 0.4 {f}\n"
        ev, _, _ = run(scn, f"gentle_{f}", outdir)
        d = delivery(ev, scn, "B", "A")
        sweep[f] = [x is not None for _, x in d]       # [from asleep, awake]
    R["U9_gentle_force"] = {"N: [delivered from asleep, delivered when awake]": sweep,
                            "model": "80 Pa per newton of grip (CAD: 0.6-2.2 kPa for light-firm squeezes)"}
    # U10 a long hug squeeze (6 s): the plates relax after the 4 s hold limit
    scn = "duration 30\nA start 0\nB start 0.4\nA squeeze 10 6.0 20\n"
    ev, _, _ = run(scn, "hug", outdir)
    R["U10_hug"] = {"felt_on_B": [(round(a, 2), round(b, 2)) for a, b in intervals(ev, "B", "felt_start", "felt_end")]}
    # U11 false wake-ups: held for an hour, warming, nobody squeezing (lower wake threshold must not call)
    scn = "duration 3700\nA start 0\nB start 0.4\nB held 100 1e9\n"
    ev, _, _ = run(scn, "false_wake", outdir)
    calls = sorted({round(float(r[0])) for r in ev if r[1] == "B" and r[2] == "tx" and r[3] == "3" and float(r[0]) > 100})
    R["U11_false_wakes"] = {"calls_in_1h_held_idle": len(calls), "at_s": calls[:10]}
    # U8 battery: standby current (a quiet hour, both dozing) and the cost of one 5-minute play session
    base = "A start 0\nB start 0.4\n"
    ev1, _, _ = run("duration 300\n" + base, "standby_300", outdir)
    ev2, _, _ = run("duration 3900\n" + base, "standby_3900", outdir)
    standby_ma = {u: (summary_mah(ev2, u) - summary_mah(ev1, u)) / 1.0 for u in "AB"}
    play = "".join(f"A squeeze {300 + k * 10} 0.5 20\nB squeeze {304 + k * 10} 0.5 8\n" for k in range(30))
    ev3, _, _ = run("duration 900\n" + base + play, "session", outdir)
    ev4, _, _ = run("duration 900\n" + base, "nosession", outdir)
    sess = {u: summary_mah(ev3, u) - summary_mah(ev4, u) for u in "AB"}
    day = {u: 24 * standby_ma[u] + 3 * sess[u] for u in "AB"}
    R["U8_battery"] = {"standby_mA": {u: round(v, 2) for u, v in standby_ma.items()},
                       "session_5min_mAh": {u: round(v, 2) for u, v in sess.items()},
                       "per_day_3_sessions_mAh": {u: round(v, 1) for u, v in day.items()},
                       "days_on_400mAh": {u: round(400 / day[u], 1) for u in "AB"}}


def show(R):
    def fmt_del(d):
        ok = [x for _, x in d if x is not None]
        return f"{len(ok)}/{len(d)} felt" + (f", latency {1000 * statistics.median(ok):.0f} ms median" if ok else "")
    for k, v in R.items():
        print(f"\n== {k}")
        if isinstance(v, list):
            for i, row in enumerate(v):
                print(f"  seed {i + 1}: parent->child {fmt_del(row['parent_to_child'])}; child->parent "
                      f"{fmt_del(row['child_to_parent'])}; patterns {row['patterns_sent']}, replies {row['replies']}")
            continue
        for kk, vv in v.items():
            if isinstance(vv, list) and vv and isinstance(vv[0], tuple) and len(vv[0]) == 2 and \
                    (vv[0][1] is None or isinstance(vv[0][1], float)):
                print(f"  {kk}: {fmt_del(vv)}  {[(round(a, 2), None if b is None else round(b, 3)) for a, b in vv]}")
            else:
                print(f"  {kk}: {vv}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="run")
    ap.add_argument("--only", choices=["bringup", "usability"])
    ap.add_argument("--sim", default="sim", help="sim (working tree) or sim_before (git HEAD)")
    a = ap.parse_args()
    global SIM
    SIM = a.sim
    outdir = os.path.join(HERE, "out", a.tag)
    os.makedirs(outdir, exist_ok=True)
    R = {}
    if a.only in (None, "bringup"):
        exp_bringup(outdir, R)
    if a.only in (None, "usability"):
        exp_usability(outdir, R)
    json.dump(R, open(os.path.join(outdir, "results.json"), "w"), indent=1, default=str)
    show(R)


if __name__ == "__main__":
    main()
