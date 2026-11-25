#!/usr/bin/env python3
"""squeeze: one hand unit (both units are identical), CadQuery.

How it works mechanically (docs/design.md section 4)
  * A soft cast-silicone SKIN (2 mm, Shore 10A) is the whole outside except the flat base.
    Its bottom lip has an inward bead that snaps into a groove in the rigid BASE; a bead of
    RTV makes it airtight. The whole inside is then one sealed air volume.
  * SENSING: squeezing pushes the skin into a 1 mm air gap over the two PLATES; the
    air pressure rises a few kPa; the BMP280 on the main board reads it.
  * ACTUATION: an SG90 servo turns an oval CAM (8 x 5 mm semi-axes) between the two plates'
    bosses. 90 deg of cam pushes each plate out 3 mm into the palm and the fingers. A rubber band
    across the plates keeps them on the cam. Each boss slides in a tunnel in the CAM HOUSING,
    so the plates translate (no hinge).
  * Qi coil (TDK WR303050, as in brim) lies on the base floor; the main board (ESP32-C3-MINI-1U,
    hardware/tools/gen_pcb.py) sits above it on a foam pad; the battery stands beside the servo.

Coordinates: X = width (52), Y = thickness (42, palm <-> fingers, the plates move along Y),
Z = up (70), Z = 0 on the flat base.

    python3 squeeze/hardware/mech/squeeze_unit.py   ->  out/*.step, *.stl, docs/img/unit_*.png
"""
import math
import os

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
IMG = os.path.join(HERE, "..", "..", "docs", "img")

# ---------------- outer shape (mm) ----------------
A, B = 26.0, 21.0          # semi-axes of the cross-section: 52 wide x 42 thick
H_CYL = 44.0               # straight part
H_DOME = 26.0              # ellipsoidal top: overall height 70
R_FOOT = 3.0               # fillet where the side meets the flat base

SKIN = 2.0                 # silicone wall
GAP = 1.0                  # air gap between skin and plates at rest (the squeeze-sensing stroke)
PLATE = 2.0                # plate shell
Z_SKIN = 5.0               # skin covers everything above this; the base is exposed below
BASE_WALL = 1.5
BASE_TOP = 9.0
BASE_FLOOR = 1.2
BEAD_Z = (6.5, 8.0)        # skin bead / base groove
BEAD_D = 0.8               # bead depth

# ---------------- mechanism ----------------
CAM_A, CAM_B, CAM_T = 8.0, 5.0, 4.0        # cam semi-axes (lift 5 -> 8 = 3 mm per plate), thickness
SERVO = dict(w=22.8, d=12.2, h=22.7, tab_w=22.8,   # mounting tabs cut off: the cradle holds the body
             tab_t=2.5, tab_z=15.9,
             shaft_off=5.9, hump_r=5.9, hump_h=4.0, spline_r=2.4, spline_h=3.0)
Z_SERVO = 16.0                               # servo body bottom
Z_CAM = Z_SERVO + SERVO["h"] + SERVO["hump_h"] + 0.5   # cam bottom (on the horn, over the spline)
BOSS_W, BOSS_H = 10.0, 5.0                   # plate boss cross-section (x, z), cam runs in its middle
Z_BOSS = Z_CAM - 0.2
PLATE_Z = (18.0, 58.0)                       # above 58 the dome is too narrow for a 28 mm plate
PLATE_HALF_W = 14.0
PEG_X, PEG_Z, PEG_R, PEG_Y0 = 9.0, 55.0, 1.0, 9.3   # plate return pegs (O-ring band), inner tip at |y| = 9.3

# ---------------- electronics (placeholders for fit) ----------------
COIL = (30.0, 29.6, 0.9)                     # TDK WR303050-12F5-ID
PCB_A, PCB_B, PCB_T = 21.6, 16.6, 1.0       # main board: ellipse 43.2 x 33.2 x 1.0 (hardware/tools/gen_pcb.py)
Z_PCB = 3.5                                  # on a 1.4 mm foam pad over the coil
PARTS_H = 3.3                                # tallest parts: USB-C 3.26, 1 uH inductor 3.0, module 2.4
UFL = (-9.4 - 4.5, 2.6 + 5.0, 2.6)           # U.FL plug on the module (x, y in CAD frame, height above module)
BATT = (30.0, 5.0, 30.0)                     # 503030 LiPo standing: x, y (thickness), z
Z_FLOOR = (10.0, 11.5)                       # chassis floor
SCREWS = [(-19.5, 0.0), (19.5, 0.0)]         # M2 from below through the base into the columns
BATT_POS = (0.0, 6.4 + BATT[1] / 2, Z_FLOOR[1])  # against the servo's +Y face (0.3 mm foam tape)


def pebble(t=0.0, foot=True):
    """The outer shape shrunk by t on every side (semi-axes minus t: within ~0.1 mm of a true
    offset for these proportions)."""
    a, b = A - t, B - t
    # seams on the X = 0 plane (ellipse drawn rotated, sphere turned 90 deg): the mold parts on Y = 0,
    # and OCC booleans fail silently when a seam lies in the cutting plane
    body = cq.Workplane("XY").workplane(offset=t).ellipse(b, a, rotation_angle=90).extrude(H_CYL - t)
    if foot and t < R_FOOT:
        body = body.faces("<Z").edges().fillet(R_FOOT - t)
    dome = cq.Solid.makeSphere(1.0, angleDegrees1=0, angleDegrees2=90).rotate(
        cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 90).transformGeometry(
        cq.Matrix([[a, 0, 0, 0], [0, b, 0, 0], [0, 0, H_DOME - t, H_CYL]]))
    return body.union(cq.Workplane().add(dome)).clean()


def slab(z0, z1, big=200.0):
    return cq.Workplane("XY").box(big, big, z1 - z0, centered=(True, True, False)).translate((0, 0, z0))


def half_y(sign, big=200.0):
    return cq.Workplane("XY").box(big, big / 2, big, centered=(True, False, True)).translate(
        (0, 0 if sign > 0 else -big / 2, 0))


def box(cx, cy, cz, w, d, h):
    """Box with its bottom face centred at (cx, cy, cz)."""
    return cq.Workplane("XY").box(w, d, h, centered=(True, True, False)).translate((cx, cy, cz))


# ---------------- parts ----------------
def skin():
    bead = pebble(SKIN).intersect(slab(*BEAD_Z)).cut(pebble(SKIN + BEAD_D))
    return pebble(0).cut(pebble(SKIN)).intersect(slab(Z_SKIN, 100)).union(bead)


def base():
    outer = pebble(0).intersect(slab(0, Z_SKIN)).union(pebble(SKIN).intersect(slab(Z_SKIN, BASE_TOP)))
    inner = cq.Workplane("XY").ellipse(A - SKIN - BASE_WALL, B - SKIN - BASE_WALL) \
        .extrude(BASE_TOP + 1 - BASE_FLOOR).translate((0, 0, BASE_FLOOR))
    groove = pebble(SKIN).intersect(slab(*BEAD_Z)).cut(pebble(SKIN + BEAD_D))
    b = outer.cut(inner).cut(groove)
    # 2 screw bosses: M2 from below, through the chassis floor into the two columns
    for (x, y) in SCREWS:
        b = b.union(cq.Workplane("XY").center(x, y).circle(2.4).extrude(BASE_TOP - 0.5)
                    .intersect(pebble(SKIN + 0.5))).cut(
            cq.Workplane("XY").center(x, y).circle(1.0).extrude(BASE_TOP + 1))
    return b


def servo_body():
    s = SERVO
    cx = -s["shaft_off"]                      # shaft on the Z axis
    body = box(cx, 0, Z_SERVO, s["w"], s["d"], s["h"])
    tabs = box(cx, 0, Z_SERVO + s["tab_z"], s["tab_w"], s["d"], s["tab_t"])
    hump = cq.Workplane("XY").circle(s["hump_r"]).extrude(s["hump_h"]).translate((0, 0, Z_SERVO + s["h"]))
    spline = cq.Workplane("XY").circle(s["spline_r"]).extrude(s["spline_h"]).translate(
        (0, 0, Z_SERVO + s["h"] + s["hump_h"]))
    return body.union(tabs).union(hump).union(spline)


def cam(angle_deg=0.0):
    """angle 0 = rest: minor axis along Y (on the plates)."""
    c = cq.Workplane("XY").ellipse(CAM_A, CAM_B).extrude(CAM_T).faces(">Z").workplane() \
        .hole(5.0).translate((0, 0, Z_CAM))   # over the spline; glue to the stock horn
    return c.rotate((0, 0, 0), (0, 0, 1), angle_deg)


def plate(sign, lift=0.0):
    """sign +1: +Y plate. lift = 0 (rest) .. 3 mm (full)."""
    shell = pebble(SKIN + GAP).cut(pebble(SKIN + GAP + PLATE)).intersect(half_y(sign)) \
        .intersect(slab(*PLATE_Z)).intersect(box(0, 0, -100, 2 * PLATE_HALF_W, 200, 300))
    y0 = sign * CAM_B
    boss_len = (B - SKIN - GAP - PLATE / 2) - CAM_B
    boss = box(0, y0 + sign * boss_len / 2, Z_BOSS, BOSS_W, boss_len, BOSS_H)
    # return pegs: an O-ring (10 mm ID x 1.5) stretched across to the other plate's peg at each x keeps
    # both plates on the cam (above the cam housing, clear of the LED post)
    for px in (-PEG_X, PEG_X):
        peg = cq.Workplane("XZ").center(px, PEG_Z).circle(PEG_R).extrude(-20 * sign if sign > 0 else 20) \
            .translate((0, sign * PEG_Y0, 0)).intersect(pebble(SKIN + GAP + 0.5))
        head = cq.Workplane("XZ").center(px, PEG_Z).circle(PEG_R + 0.6).extrude(0.6 if sign > 0 else -0.6) \
            .translate((0, sign * PEG_Y0, 0))
        shell = shell.union(peg).union(head)
    return shell.union(boss).translate((0, sign * lift, 0))


def chassis():
    fl = pebble(SKIN + BASE_WALL + 0.3, foot=False).intersect(slab(*Z_FLOOR))
    for (x, y) in SCREWS:
        fl = fl.cut(cq.Workplane("XY").center(x, y).circle(1.1).extrude(30))
    s = SERVO
    cx = -s["shaft_off"]
    pedestal = box(cx, 0, Z_FLOOR[1], s["w"], s["d"], Z_SERVO - Z_FLOOR[1])
    # cradle: walls on -Y and both ends (the battery is the +Y wall)
    cradle = box(cx, -s["d"] / 2 - 0.6, Z_FLOOR[1], s["w"] + 2.4, 1.2, 14) \
        .union(box(cx - s["w"] / 2 - 0.6, -0.6, Z_FLOOR[1], 1.2, s["d"] + 1.2, 14)) \
        .union(box(cx + s["w"] / 2 + 0.6, -0.6, Z_FLOOR[1], 1.2, s["d"] + 1.2, 14))
    # columns carrying the cam housing
    cols = box(-19.5, 0, Z_FLOOR[1], 3.5, 8, Z_BOSS + BOSS_H + 1.5 - Z_FLOOR[1]) \
        .union(box(19.5, 0, Z_FLOOR[1], 3.5, 8, Z_BOSS + BOSS_H + 1.5 - Z_FLOOR[1]))
    # cam housing: a plate over the cam, side walls, arms to the columns, tunnels for the bosses
    zb, zt = Z_BOSS - 0.25, Z_BOSS + BOSS_H + 1.5   # tunnels open at the bottom (no thin sliver)
    housing = box(0, 0, zb, 21, 24, zt - zb)
    housing = housing.cut(cq.Workplane("XY").circle(CAM_A + 0.6).extrude(zt - zb - 1.2).translate((0, 0, zb)))
    housing = housing.cut(box(0, 0, Z_BOSS - 0.25, BOSS_W + 0.5, 30, BOSS_H + 0.5))      # tunnels
    housing = housing.cut(cq.Workplane("XY").circle(SERVO["hump_r"] + 0.6).extrude(3).translate((0, 0, zb - 1)))
    arms = box(-15, 0, zt - 3, 12, 8, 3).union(box(15, 0, zt - 3, 12, 8, 3))
    # LED post to the dome (the LED tab and the FPC antenna live up here)
    post = box(0, 0, zt, 6, 6, 63.5 - zt)
    c = fl.union(pedestal).union(cradle).union(cols).union(housing).union(arms).union(post)
    return c.intersect(pebble(SKIN + GAP + 0.2, foot=False))


def electronics():
    coil = box(0, 0, BASE_FLOOR, COIL[0], COIL[1], COIL[2]).edges("|Z").fillet(4)
    pcb = cq.Workplane("XY").ellipse(PCB_A, PCB_B).extrude(PCB_T).translate((0, 0, Z_PCB))
    for (x, y) in SCREWS:                                  # notches for the base screw bosses (r 2.4 + 0.5)
        pcb = pcb.cut(cq.Workplane("XY").center(x, y).circle(2.9).extrude(20))
    # component envelope: everything within 2 mm of the edge stays lower (the base wall), U.FL plug on top
    comps = cq.Workplane("XY").ellipse(PCB_A - 2.0, PCB_B - 2.0).extrude(PARTS_H).translate((0, 0, Z_PCB + PCB_T))
    ufl = box(UFL[0], UFL[1], Z_PCB + PCB_T + 2.4, 3.2, 3.2, UFL[2])
    for (x, y) in SCREWS:                                  # no parts beside the bosses (gen_pcb.py placement)
        comps = comps.cut(cq.Workplane("XY").center(x, y).circle(3.4).extrude(20))
    parts_env = comps.union(ufl)
    batt = box(*BATT_POS, *BATT)
    led = box(0, 0, 63.5, 8.0, 6.0, 1.0).union(box(0, 0, 64.5, 1.6, 1.5, 0.6))   # break-off LED tab on the post
    return dict(coil=coil, pcb=pcb, parts=parts_env, battery=batt, servo=servo_body(), led=led)


def mold():
    """Skin mold: two outer halves split on Y = 0 plus a core plug (3D-print in resin for a
    smooth skin). Fill the outer mold dome-down, lower the core in, and the excess leaves through
    the vent holes over the base ring."""
    cavity = pebble(0).intersect(slab(Z_SKIN, 100))
    blk = box(0, 0, Z_SKIN, 2 * A + 12, 2 * B + 12, H_CYL + H_DOME - Z_SKIN + 6)
    outer = blk.cut(cavity)
    keys = [cq.Workplane("XY").sphere(2.5).translate((sx * (A + 3), 0, z)) for sx in (-1, 1) for z in (20, 50)]
    a, b = outer.intersect(half_y(+1)), outer.intersect(half_y(-1))
    for k in keys:
        a, b = a.union(k), b.cut(k)
    core = pebble(SKIN, foot=False).intersect(slab(Z_SKIN, 100)) \
        .cut(pebble(SKIN).intersect(slab(*BEAD_Z)).cut(pebble(SKIN + BEAD_D)))
    lid = box(0, 0, Z_SKIN - 4, 2 * A + 12, 2 * B + 12, 4)
    for i in range(8):
        t = 2 * math.pi * (i + 0.5) / 8
        lid = lid.cut(cq.Workplane("XY").center((A - SKIN / 2) * math.cos(t), (B - SKIN / 2) * math.sin(t))
                      .circle(1.6).extrude(5).translate((0, 0, Z_SKIN - 4.5)))
    return a, b, core.union(lid)


def all_parts(lift=0.0):
    p = dict(skin=skin(), base=base(), chassis=chassis(),
             plate_pos=plate(+1, lift), plate_neg=plate(-1, lift),
             cam=cam(90.0 * (lift / (CAM_A - CAM_B)) if lift else 0.0))
    p.update(electronics())
    return p


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    parts = all_parts()
    for name in ("skin", "base", "chassis", "plate_pos", "plate_neg", "cam"):
        cq.exporters.export(parts[name], os.path.join(OUT, f"{name}.step"))
        cq.exporters.export(parts[name], os.path.join(OUT, f"{name}.stl"), tolerance=0.05)
    m1, m2, core = mold()
    for name, w in (("mold_half_a", m1), ("mold_half_b", m2), ("mold_core", core)):
        cq.exporters.export(w, os.path.join(OUT, f"{name}.stl"), tolerance=0.05)
        cq.exporters.export(w, os.path.join(OUT, f"{name}.step"))
    asm = cq.Assembly()
    for name, w in parts.items():
        asm.add(w, name=name)
    asm.export(os.path.join(OUT, "assembly.step"))
    print("exported to", OUT)
