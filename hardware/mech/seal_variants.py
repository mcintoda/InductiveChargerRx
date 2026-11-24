#!/usr/bin/env python3
"""Plug variants that bracket the O-ring squeeze, for the first prints.

SLA/MJF parts come out about +-0.1-0.2 mm, which moves the O-ring squeeze by up to ~10 points. Print the nominal plug
and these two with each cup, fit whichever seals with a firm push (leak test, docs/enclosure.md 2.5), then set
GLAND_DEPTH in enclosure.py to that value.

    python3 hardware/mech/seal_variants.py   ->  hardware/mech/out/plug_tight.stl, plug_loose.stl
"""
import os

import cadquery as cq

import enclosure as E

VARIANTS = {"tight": E.GLAND_DEPTH - 0.10, "loose": E.GLAND_DEPTH + 0.10}

if __name__ == "__main__":
    nominal = E.GLAND_DEPTH
    for name, depth in VARIANTS.items():
        E.GLAND_DEPTH = depth                      # make_plug() reads the module value when it runs
        squeeze = (E.ORING_CS - (depth + E.PLUG_CLR)) / E.ORING_CS
        path = os.path.join(E.OUT, f"plug_{name}.stl")
        cq.exporters.export(E.make_plug(), path, tolerance=0.02, angularTolerance=0.1)
        print(f"{path}: groove depth {depth:.2f} mm, squeeze {100 * squeeze:.0f} % (nominal {nominal:.2f} mm)")
    E.GLAND_DEPTH = nominal
