#!/usr/bin/env python3
"""Run tidy_tracks.py on the board, then DRC; any net that gains a clearance error or loses a connection
steps down a level (4 -> ... -> 0 untouched) for that net on that layer until the board is as clean as the original.

    tidy_board.py kicad/bath_monitor.kicad_pcb
"""
import json, os, re, subprocess, sys, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
BAD = ("clearance", "hole_clearance", "shorting_items", "tracks_crossing", "unconnected_items", "copper_edge_clearance")

def drc(board):
    rpt = tempfile.mktemp(suffix=".rpt")
    subprocess.run([sys.executable, "-c",
        "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); pcbnew.WriteDRCReport(b, sys.argv[2], pcbnew.EDA_UNITS_MILLIMETRES, True)",
        board, rpt], check=True, capture_output=True)
    t = open(rpt).read(); os.remove(rpt)
    out = []
    for blk in re.split(r"\n(?=\[)", t):
        m = re.match(r"\[(\w+)\]", blk)
        if not m:
            continue
        # blame tracks (the only thing tidy moves); fall back to every item for unconnected nets
        nets = {f"{n}@{l}" for n, l in re.findall(r"^\s+@.*?: Track \[([^\]]+)\] on ([A-Za-z0-9_.]+?),?\s", blk, re.M)}
        if not nets:      # unconnected pad-to-pad: step the whole net
            nets = set(re.findall(r"^\s+@.*?\[([^\]]+)\]", blk, re.M))
        out.append((m.group(1), nets, blk))
    return out

def main():
    board = sys.argv[1]
    base = [x for x in drc(board) if x[0] in BAD]
    print("original errors:", len(base))
    levels = {}
    tmp = tempfile.mkdtemp()
    lv_file, out = os.path.join(tmp, "lv.json"), os.path.join(tmp, "out.kicad_pcb")
    for rnd in range(20):
        json.dump(levels, open(lv_file, "w"))
        r = subprocess.run([sys.executable, os.path.join(HERE, "tidy_tracks.py"), board, out, "--levels", lv_file],
                           check=True, capture_output=True, text=True)
        r.stdout = r.stdout or ""
        stats = [l for l in r.stdout.splitlines() if l.startswith("{")][-1]
        errs = [x for x in drc(out) if x[0] in BAD]
        print(f"round {rnd}: {len(errs)} errors  {stats}")
        if len(errs) <= len(base):
            break
        blamed = set()
        for kind, nets, blk in errs:
            blamed |= nets
        for n in blamed:                 # one step per round, however many errors the net has
            levels[n] = max(0, levels.get(n, 4) - 1)
        print("   stepped down:", {k: v for k, v in levels.items()})
    if len(errs) > len(base):
        sys.exit("could not get back to the original error count; board left unchanged")
    shutil.copy(out, board)
    print("levels:", levels)

main()
