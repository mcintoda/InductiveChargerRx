#!/usr/bin/env python3
"""Bath Monitor enclosure: cup + O-ring plug + tub bracket (CadQuery, no epoxy).

Sealing concept
  * The CUP is one piece: thin flat front wall (sensing face), side walls, open back.
  * The PLUG (back cover / Qi face) carries a 1.5 mm EPDM O-ring in a groove on its skirt and
    is pushed into the cup bore: a RADIAL (piston) seal. Squeeze is set by geometry, not by
    screw torque, so there is no flange and nothing to glue.
  * Four M2 A4-stainless self-tapping screws through the side walls into the plug hold it in.
    They sit OUTBOARD of the O-ring: water can reach the screw holes but stops at the O-ring.
  * The internal stack (PCB, battery, Qi coil, 0.6 mm foam) is clamped by the plug, pressing
    the electrodes flat onto the front wall (no air gap).
  * The BRACKET stays on the tub (2 suction cups); the device slides in from the top and is
    lifted out for charging.  Its side lips only overlap the outer 3 mm of the front face.

Coordinates: X = width, Y = height (device standing on the tub wall, +Y up),
Z = thickness, Z = 0 at the outer front face (water side), +Z towards the tub wall.

    python3 hardware/mech/enclosure.py   ->  hardware/mech/out/*.step, *.stl, docs/img/enclosure_*.png
"""
import math
import os

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
IMG = os.path.join(HERE, "..", "..", "docs", "img")

# ---------------- parameters (mm) ----------------
PCB_W, PCB_L, PCB_T = 38.0, 112.0, 1.0           # incl. thermal tab; top corners R5.5
CLR_SIDE, CLR_END = 0.7, 0.8                      # PCB-to-cavity clearance
CAV_W, CAV_L, CAV_R = PCB_W + 2 * CLR_SIDE, PCB_L + 2 * CLR_END, 6.0
T_FRONT, T_SIDE, T_BACK = 1.2, 2.2, 1.5           # wall thicknesses
STACK = PCB_T + 6.0 + 1.2 + 0.6                   # PCB + battery 603450 + coil + foam = 8.8
DEPTH = T_FRONT + STACK + T_BACK                  # overall thickness 11.5
OUT_W, OUT_L, OUT_R = CAV_W + 2 * T_SIDE, CAV_L + 2 * T_SIDE, CAV_R + T_SIDE
EDGE_FILLET = 1.5

# plug / radial gland (ISO 3601-style starting values for CS 1.5 mm, static radial)
ORING_CS, ORING_ID = 1.5, 88.0
PLUG_CLR = 0.10                                   # radial clearance plug skirt <-> bore
GLAND_DEPTH, GLAND_W = 1.05, 2.30                 # radial gap 1.15 mm -> ~22 % squeeze, ~70 % fill
SKIRT_T, SKIRT_Z0 = 2.2, 5.0                      # skirt from Z=5.0 to the back wall
GROOVE_Z0 = 5.9                                   # groove spans Z 5.9 .. 8.0
BORE_CHAMFER = 0.6                                # lead-in at the cup opening (protects the O-ring)

# retention screws: M2 self-tapping, axis at Z = 9.6 (outboard of the groove)
SCREW_Z, SCREW_Y = 9.6, (-30.0, 30.0)
SCREW_CLEAR, SCREW_PILOT = 2.3, 1.6

# thermal window (TMP117 on the PCB tab): front wall thinned to 0.8 mm
WIN_W, WIN_H, WIN_T = 10.0, 7.0, 0.8

# device frame: cavity centred on X=0, Y=0
CAV_TOP = CAV_L / 2


def pcb_to_dev(x, y):
    """PCB placement-study coordinates (x right, y down from top edge) -> device X, Y."""
    return x - PCB_W / 2, CAV_TOP - CLR_END - y


def rrect(w, l, r):
    return cq.Sketch().rect(w, l).vertices().fillet(r)


def oring_groove_perimeter():
    w = CAV_W - 2 * PLUG_CLR - 2 * GLAND_DEPTH
    l = CAV_L - 2 * PLUG_CLR - 2 * GLAND_DEPTH
    r = CAV_R - PLUG_CLR - GLAND_DEPTH
    return 2 * (w + l) - 8 * r + 2 * math.pi * r, r


# ---------------- cup ----------------
def make_cup():
    body = cq.Workplane("XY").placeSketch(rrect(OUT_W, OUT_L, OUT_R)).extrude(DEPTH)
    body = body.faces("<Z").edges().fillet(EDGE_FILLET).faces(">Z").edges().fillet(0.6)
    cavity = cq.Workplane("XY").workplane(offset=T_FRONT).placeSketch(rrect(CAV_W, CAV_L, CAV_R)).extrude(DEPTH)
    cup = body.cut(cavity)
    # lead-in chamfer at the bore entry
    lead = (cq.Workplane("XY").workplane(offset=DEPTH - BORE_CHAMFER)
            .placeSketch(rrect(CAV_W, CAV_L, CAV_R)).extrude(BORE_CHAMFER, taper=-45))
    cup = cup.cut(lead)
    # thermal window pocket (from inside) behind the TMP117 tab
    wx, wy = pcb_to_dev(19.0, 107.0)
    pocket = (cq.Workplane("XY").workplane(offset=WIN_T).center(wx, wy)
              .placeSketch(rrect(WIN_W, WIN_H, 1.0)).extrude(T_FRONT - WIN_T))
    cup = cup.cut(pocket)
    # retention screw clearance holes through both long side walls (countersunk outside)
    for sy in SCREW_Y:
        for side in (-1, 1):
            hole = (cq.Workplane("YZ").workplane(offset=side * (OUT_W / 2 + 1))
                    .center(sy, SCREW_Z).circle(SCREW_CLEAR / 2).extrude(-side * (T_SIDE + 2)))
            csk = (cq.Workplane("YZ").workplane(offset=side * OUT_W / 2)
                   .center(sy, SCREW_Z).circle(2.0).extrude(-side * 1.0, taper=45))
            cup = cup.cut(hole).cut(csk)
    return cup


# ---------------- plug (back cover, Qi face) ----------------
def make_plug():
    pw, pl, pr = CAV_W - 2 * PLUG_CLR, CAV_L - 2 * PLUG_CLR, CAV_R - PLUG_CLR
    back = (cq.Workplane("XY").workplane(offset=DEPTH - T_BACK)
            .placeSketch(rrect(pw, pl, pr)).extrude(T_BACK))
    ring_out = cq.Workplane("XY").workplane(offset=SKIRT_Z0).placeSketch(rrect(pw, pl, pr)).extrude(DEPTH - T_BACK - SKIRT_Z0)
    ring_in = (cq.Workplane("XY").workplane(offset=SKIRT_Z0)
               .placeSketch(rrect(pw - 2 * SKIRT_T, pl - 2 * SKIRT_T, pr - SKIRT_T)).extrude(DEPTH))
    skirt = ring_out.cut(ring_in)
    plug = back.union(skirt)
    # O-ring groove
    g_out = cq.Workplane("XY").workplane(offset=GROOVE_Z0).placeSketch(rrect(pw + 2, pl + 2, pr + 1)).extrude(GLAND_W)
    g_in = (cq.Workplane("XY").workplane(offset=GROOVE_Z0)
            .placeSketch(rrect(pw - 2 * GLAND_DEPTH, pl - 2 * GLAND_DEPTH, pr - GLAND_DEPTH)).extrude(GLAND_W))
    plug = plug.cut(g_out.cut(g_in))
    # pilot holes for the M2 self-tapping screws
    for sy in SCREW_Y:
        for side in (-1, 1):
            pil = (cq.Workplane("YZ").workplane(offset=side * (pw / 2 + 0.5))
                   .center(sy, SCREW_Z).circle(SCREW_PILOT / 2).extrude(-side * 4.5))
            plug = plug.cut(pil)
    # two posts that press the PCB (on the module can) in the electronics band
    for px in (-5.0, 5.0):
        mx, my = pcb_to_dev(19.0 + px, 12.0)
        post = (cq.Workplane("XY").workplane(offset=T_FRONT + PCB_T + 2.4 + 0.2)
                .center(mx, my).circle(1.5).extrude(DEPTH - T_BACK - (T_FRONT + PCB_T + 2.4 + 0.2)))
        plug = plug.union(post)
    # pry notch at the top edge for opening (outside the seal)
    notch = (cq.Workplane("XY").workplane(offset=DEPTH - 0.8).center(0, pl / 2 - 0.5)
             .rect(8.0, 2.0).extrude(1.0))
    plug = plug.cut(notch)
    return plug


# ---------------- bracket (stays on the tub) ----------------
BR_L, BR_T, BR_WALL, BR_LIP, BR_GAP = 80.0, 2.5, 2.0, 3.0, 0.3


def make_bracket():
    iw = OUT_W + 2 * BR_GAP
    ow = iw + 2 * BR_WALL
    z_back = DEPTH + BR_GAP                       # bracket back plate sits behind the device
    y0 = -OUT_L / 2 - 2.0                         # bottom of the bracket (bottom stops)
    plate = (cq.Workplane("XY").workplane(offset=z_back).center(0, y0 + BR_L / 2)
             .rect(ow, BR_L).extrude(BR_T).edges("|Z").fillet(3.0))
    walls = cq.Workplane("XY")
    for side in (-1, 1):
        wall = (cq.Workplane("XY").workplane(offset=-1.2).center(side * (iw / 2 + BR_WALL / 2), y0 + BR_L / 2)
                .rect(BR_WALL, BR_L).extrude(z_back + 1.2))
        lip = (cq.Workplane("XY").workplane(offset=-1.2).center(side * (iw / 2 - BR_LIP / 2 + BR_WALL / 2), y0 + BR_L / 2)
               .rect(BR_LIP + BR_WALL, BR_L).extrude(1.2))
        plate = plate.union(wall).union(lip)
    # bottom stops at the two corners only (leave the thermal window and centre open)
    for side in (-1, 1):
        stop = (cq.Workplane("XY").workplane(offset=-1.2).center(side * (iw / 2 - 4.0), y0 + 1.0)
                .rect(8.0, 2.0).extrude(z_back + 1.2))
        plate = plate.union(stop)
    # keyhole slots for 2 x 40 mm suction cups with mushroom heads (head ~10 mm, neck ~5 mm)
    for ky in (y0 + 18.0, y0 + BR_L - 18.0):
        kh = (cq.Workplane("XY").workplane(offset=z_back - 1).center(0, ky).circle(5.4).extrude(BR_T + 2))
        sl = (cq.Workplane("XY").workplane(offset=z_back - 1).center(0, ky + 4.0).slot2D(8.0, 5.6, 90).extrude(BR_T + 2))
        plate = plate.cut(kh).cut(sl)
    # drain / flow windows in the back plate
    for wy in (y0 + 38.0, y0 + 48.0):
        plate = plate.cut(cq.Workplane("XY").workplane(offset=z_back - 1).center(0, wy).slot2D(30.0, 5.0).extrude(BR_T + 2))
    return plate


def section_svg(shape, path, plane_y=0.0):
    """Export a cross-section (cut by the plane Y = plane_y) as SVG viewed along -Y."""
    big = cq.Workplane("XZ").workplane(offset=-plane_y).rect(200, 100).extrude(0.05)
    sec = shape.intersect(big)
    cq.exporters.export(sec, path, opt={"projectionDir": (0, -1, 0), "showHidden": False, "strokeWidth": 0.15,
                                        "width": 900, "height": 400, "marginLeft": 10, "marginTop": 10})


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(IMG, exist_ok=True)
    cup, plug, br = make_cup(), make_plug(), make_bracket()
    for name, part in (("cup", cup), ("plug", plug), ("bracket", br)):
        cq.exporters.export(part, os.path.join(OUT, f"{name}.step"))
        cq.exporters.export(part, os.path.join(OUT, f"{name}.stl"), tolerance=0.02, angularTolerance=0.1)
    assy = (cq.Assembly()
            .add(cup, name="cup", color=cq.Color(0.85, 0.9, 1.0, 0.6))
            .add(plug, name="plug", color=cq.Color(0.3, 0.5, 0.9))
            .add(br, name="bracket", color=cq.Color(0.6, 0.6, 0.6)))
    assy.save(os.path.join(OUT, "assembly.step"))

    # interference check: plug must not collide with the cup (O-ring is a separate part)
    inter = cup.intersect(plug).val().Volume() if cup.intersect(plug).vals() else 0.0
    per, gr = oring_groove_perimeter()
    stretch = per / (math.pi * ORING_ID) - 1
    cs = ORING_CS * (1 - 0.5 * stretch)          # cross-section shrinks ~half the stretch
    squeeze = (cs - (GLAND_DEPTH + PLUG_CLR)) / cs  # nominal (plug centred)
    sq_lo = (cs - (GLAND_DEPTH + 2 * PLUG_CLR)) / cs
    sq_hi = (cs - GLAND_DEPTH) / cs
    fill = (math.pi / 4 * cs ** 2) / ((GLAND_DEPTH + PLUG_CLR) * GLAND_W)
    vol = OUT_W * OUT_L * DEPTH / 1000
    print(f"outside: {OUT_W:.1f} x {OUT_L:.1f} x {DEPTH:.1f} mm, cavity {CAV_W:.1f} x {CAV_L:.1f} x {DEPTH - T_FRONT - T_BACK:.1f} mm")
    print(f"cup volume {cup.val().Volume()/1000:.1f} cm3, plug {plug.val().Volume()/1000:.1f} cm3, bracket {br.val().Volume()/1000:.1f} cm3")
    print(f"displaced volume ~{vol:.0f} cm3 -> floats if total mass < ~{vol:.0f} g")
    print(f"cup/plug interference volume: {inter:.3f} mm3")
    print(f"O-ring {ORING_ID} x {ORING_CS}: groove-bottom perimeter {per:.1f} mm, corner radius {gr:.1f} mm "
          f"(min ~{3*ORING_CS:.1f}), installed stretch {100*stretch:.1f} %, squeeze {100*squeeze:.0f} % nominal ({100*sq_lo:.0f}-{100*sq_hi:.0f} % with plug off-centre), groove fill {100*fill:.0f} %")
    return cup, plug, br


if __name__ == "__main__":
    main()
