#!/usr/bin/env python3
"""Write the project footprints into Squeeze.pretty (KiCad 7 format).

ESP32-C3-MINI-1U:

Pad geometry is taken from Espressif's official KiCad library (github.com/espressif/kicad-libraries,
footprints/Espressif.pretty/ESP32-C3-MINI-1U.kicad_mod, which is KiCad 10 format and does not load in 7).
The numbers below are copied from that file; the module body is 13.2 x 12.5 mm.

Wire_1xN_*: through-hole pads for hand-soldered wires (coil, battery, servo, LED).

    python3 squeeze/hardware/tools/make_footprints.py
"""
import os

LIB = os.path.join(os.path.dirname(__file__), "..", "kicad", "Squeeze.pretty")
OUT = os.path.join(LIB, "ESP32-C3-MINI-1U.kicad_mod")

pads = []
for i in range(11):                                   # 1..11 left, 25..35 right (0.4 x 0.8, rotated)
    pads.append((str(1 + i), -5.9, -3.3 + 0.8 * i, 0.8, 0.4))
    pads.append((str(25 + i), 5.9, 4.7 - 0.8 * i, 0.8, 0.4))
for i in range(13):                                   # 12..24 bottom, 36..48 top
    pads.append((str(12 + i), -4.8 + 0.8 * i, 5.6, 0.4, 0.8))
    pads.append((str(36 + i), 4.8 - 0.8 * i, -4.2, 0.4, 0.8))
for x in (-1.975, 0.0, 1.975):                        # 49: 3 x 3 grid of 1.45 mm GND pads
    for y in (-1.275, 0.7, 2.675):
        pads.append(("49", x, y, 1.45, 1.45))
for n, x, y in (("50", 5.95, -4.25), ("51", 5.95, 5.65), ("52", -5.95, 5.65), ("53", -5.95, -4.25)):
    pads.append((n, x, y, 0.7, 0.7))


def line(x0, y0, x1, y1, layer, w):
    return f'  (fp_line (start {x0} {y0}) (end {x1} {y1}) (stroke (width {w}) (type solid)) (layer "{layer}"))\n'


def rect(x0, y0, x1, y1, layer, w):
    return "".join(line(*a, layer, w) for a in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)))


s = ['(footprint "ESP32-C3-MINI-1U" (version 20221018) (generator pcbnew)\n  (layer "F.Cu")\n',
     '  (descr "ESP32-C3-MINI-1U, external antenna (U.FL), 13.2 x 12.5 mm; pads from Espressif kicad-libraries")\n',
     '  (attr smd)\n',
     '  (fp_text reference "REF**" (at 0 -7.4) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))\n',
     '  (fp_text value "ESP32-C3-MINI-1U" (at 0 7.4) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))\n',
     rect(-6.6, -6.2, 6.6, 6.3, "F.Fab", 0.1), rect(-6.85, -6.45, 6.85, 6.55, "F.CrtYd", 0.05),
     line(-6.7, -6.3, -6.7, -5.0, "F.SilkS", 0.12), line(-6.7, -6.3, -5.4, -6.3, "F.SilkS", 0.12),
     '  (fp_circle (center -6.9 -3.3) (end -6.75 -3.3) (stroke (width 0.3) (type solid)) (fill solid) (layer "F.SilkS"))\n']
for n, x, y, w, h in pads:
    s.append(f'  (pad "{n}" smd rect (at {x:.4g} {y:.4g}) (size {w} {h}) (layers "F.Cu" "F.Paste" "F.Mask"))\n')
s.append(")\n")
open(OUT, "w").write("".join(s))
print("wrote", os.path.relpath(OUT), len(pads), "pads")


WIRES = [  # (name, pins, pitch, drill, pad)
    ("Wire_1x02_P3.6mm_D0.5mm", 2, 3.6, 0.5, 1.1),    # Qi coil leads
    ("Wire_1x02_P2.5mm_D0.8mm", 2, 2.5, 0.8, 1.6),    # battery
    ("Wire_1x03_P2.0mm_D0.7mm", 3, 2.0, 0.7, 1.4),    # servo
    ("Wire_1x04_P1.6mm_D0.5mm", 4, 1.6, 0.5, 1.1),    # LED tab
]
for name, n, pitch, drill, pad in WIRES:
    x0 = -(n - 1) * pitch / 2
    w = (n - 1) * pitch + pad
    s = [f'(footprint "{name}" (version 20221018) (generator pcbnew)\n  (layer "F.Cu")\n',
         f'  (descr "{n} through-hole pads for hand-soldered wires, pitch {pitch} mm, drill {drill} mm")\n',
         '  (attr through_hole exclude_from_pos_files exclude_from_bom)\n',
         f'  (fp_text reference "REF**" (at 0 {-pad / 2 - 0.8:.2f}) (layer "F.SilkS") hide (effects (font (size 0.5 0.5) (thickness 0.08))))\n',
         f'  (fp_text value "{name}" (at 0 {pad / 2 + 0.8:.2f}) (layer "F.Fab") (effects (font (size 0.5 0.5) (thickness 0.08))))\n',
         rect(-w / 2 - 0.25, -pad / 2 - 0.25, w / 2 + 0.25, pad / 2 + 0.25, "F.CrtYd", 0.05)]
    for i in range(n):
        shape = "rect" if i == 0 else "circle"
        s.append(f'  (pad "{i + 1}" thru_hole {shape} (at {x0 + i * pitch:.3f} 0) (size {pad} {pad}) (drill {drill}) '
                 f'(layers "*.Cu" "*.Mask"))\n')
    s.append(")\n")
    open(os.path.join(LIB, name + ".kicad_mod"), "w").write("".join(s))
print("wire pad footprints:", ", ".join(w[0] for w in WIRES))
