#!/usr/bin/env python3
"""Export the schematic netlist with kicad-cli and check it against the intended
pin->net map in gen_schematic.py.  Exit code 1 on any difference."""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import gen_schematic as g  # noqa: E402
from sexp import find, parse  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, "bm.net")
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", out, g.OUT], check=True, capture_output=True)
    tree = parse(open(out).read())

drawn = {}
for n in find(find(tree, "nets")[0], "net"):
    nodes = frozenset(f"{find(x, 'ref')[0][1]}.{find(x, 'pin')[0][1]}" for x in find(n, "node"))
    drawn[nodes] = find(n, "name")[0][1]

intended = {}
for p in g.PARTS:
    if p["ref"].startswith("#"):
        continue
    for num in g.pins_of(g.load_symbol(p["lib"])):
        intended.setdefault(p["nets"].get(num) or f"NC:{p['ref']}.{num}", set()).add(f"{p['ref']}.{num}")
want = {frozenset(v): k for k, v in intended.items()}

ok = True
for nodes, name in want.items():
    if nodes not in drawn:
        ok = False
        hits = {drawn[d] for d in drawn if d & nodes}
        print(f"MISMATCH {name}: intended {sorted(nodes)} drawn as {sorted(hits)}")
for nodes, name in drawn.items():
    if nodes not in want:
        ok = False
        print(f"UNEXPECTED drawn net {name}: {sorted(nodes)}")
named = sum(1 for k in want.values() if not k.startswith("NC:"))
print(f"{named} intended nets, {len(drawn)} drawn nets (incl. unconnected pins): {'MATCH' if ok else 'DIFFERENT'}")
sys.exit(0 if ok else 1)
