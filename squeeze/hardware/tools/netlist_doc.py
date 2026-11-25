#!/usr/bin/env python3
"""Render parts.py as docs/schematic.md: every part with its pins, and every net with its members.

    python3 squeeze/hardware/tools/netlist_doc.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import parts as PT  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "schematic.md")


def key(r):
    return (r.rstrip("0123456789"), int("".join(c for c in r if c.isdigit()) or 0))


def pinkey(p):
    return (0, int(p)) if p.isdigit() else (1, p)


lines = ["# squeeze main board: netlist (rev A)", "",
         "Generated from `hardware/tools/parts.py` by `netlist_doc.py`: the board is built from the same data, so this",
         "is what is on the copper. The circuit blocks are explained in [design.md](design.md) section 5. The routed board:",
         "![board](img/pcb_layers.png)", "", "## Parts", "",
         "| Ref | Part | LCSC | Pins → nets | Notes |", "|---|---|---|---|---|"]
for p in sorted(PT.PARTS, key=lambda p: key(p["ref"])):
    pins = {}
    for pin, n in p["nets"].items():
        pins.setdefault(n or "—", []).append(pin)
    pin_txt = "; ".join(f'{",".join(sorted(v, key=pinkey))}: {n}' for n, v in sorted(pins.items(), key=lambda kv: pinkey(sorted(kv[1], key=pinkey)[0])))
    if len(pin_txt) > 160:
        pin_txt = pin_txt[:157] + "…"
    part = f'{p["value"]} {p["rating"]}'.strip()
    hand = "" if p["placed"] else " *(hand)*"
    lines.append(f'| {p["ref"]} | {part}{hand} | {p["lcsc"]} | {pin_txt} | {p["note"]} |')
lines += ["", "## Nets", "", "| Net | Connects |", "|---|---|"]
for n, members in sorted(PT.nets().items()):
    lines.append(f'| {n} | {" ".join(f"{r}.{q}" for r, q in sorted(members, key=lambda m: (key(m[0]), pinkey(m[1]))))} |')
open(OUT, "w").write("\n".join(lines) + "\n")
print("wrote", os.path.relpath(OUT))
