#!/usr/bin/env python3
"""Board placement study: build hardware/kicad/bath_monitor.kicad_pcb with KiCad's pcbnew API.

What it does
  * 4-layer outline (38 x 102 mm body + 12 x 10 mm thermal tab for the TMP117)
  * every schematic footprint loaded, assigned its nets (from gen_schematic.PARTS) and placed
    - electrodes on F.Cu (front, faces the water through the wall)
    - all components on B.Cu (single-sided assembly at JLC), grouped by function
  * zones: driven SHIELD (F.Cu side strips + hatched In1.Cu), GND only in the electronics zone,
    antenna keep-out, thermal window copper + vias on the tab
  * mechanical context on user layers: battery, Qi coil, enclosure, water levels
It does NOT route tracks; the result is a placement / floor-plan study, ready for routing.

    python3 hardware/tools/gen_pcb.py        (needs KiCad 7 python module `pcbnew`)
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import gen_schematic as S  # noqa: E402

HW = S.HW
OUT = os.path.join(HW, "kicad", "bath_monitor.kicad_pcb")
FPDIR = "/usr/share/kicad/footprints"
PROJ_LIB = os.path.join(HW, "kicad", "BathMonitor.pretty")
OX, OY = 100.0, 50.0                      # sheet offset of the board's top-left corner
def mm(v):
    return int(round(v * 1e6))

# ---------------------------------------------------------------------------
# geometry (board frame, mm, y downwards, viewed from the FRONT / water side)
# ---------------------------------------------------------------------------
W_B, H_B = 38.0, 102.0                    # main body
ANT_Y = 5.2                               # antenna strip: no copper on any layer above this
ELEC_TOP = 29.5                           # electronics zone is y < ELEC_TOP
PAD_X0, PAD_X1 = 4.0, 34.0                # electrode width 30 mm
REF_Y = (32.0, 38.0)                      # dry reference electrode
PAD_PITCH, PAD_H, PAD6_TOP = 10.0, 9.0, 42.0
SHIELD_Y = (30.5, 101.5)
TAB = (13.0, 25.0, 102.0, 112.0)          # thermal tab x0, x1, y0, y1
NECK = (16.0, 22.0, 102.0, 104.0)         # narrow neck for thermal isolation


def pad_center_y(k):                      # k = 1 (bottom) .. 6 (top / default alarm)
    return PAD6_TOP + PAD_H / 2 + (6 - k) * PAD_PITCH


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


board = pcbnew.BOARD()
board.SetCopperLayerCount(4)
ds = board.GetDesignSettings()
ds.SetBoardThickness(mm(1.0))


def seg(layer, a, b, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(*a)); s.SetEnd(P(*b)); s.SetLayer(layer); s.SetWidth(mm(width))
    board.Add(s)


def poly_outline(layer, pts, width=0.1):
    for a, b in zip(pts, pts[1:] + pts[:1]):
        seg(layer, a, b, width)


def rect(layer, x0, y0, x1, y1, width=0.1):
    poly_outline(layer, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], width)


def circle(layer, cx, cy, r, width=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_CIRCLE)
    s.SetCenter(P(cx, cy)); s.SetEnd(P(cx + r, cy)); s.SetLayer(layer); s.SetWidth(mm(width))
    board.Add(s)


def text(layer, s, x, y, size=1.0, mirror=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s); t.SetPosition(P(x, y)); t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size))); t.SetTextThickness(mm(size * 0.15))
    t.SetMirrored(mirror)
    board.Add(t)


# --- board outline: body + thermal tab on a narrow neck --------------------
tx0, tx1, ty0, ty1 = TAB
nx0, nx1, ny0, ny1 = NECK
import math  # noqa: E402
R_TOP = 5.5   # top corners rounded so the board passes the enclosure's R6 bore (hardware/mech)


def arc_pts(cx, cy, r, a0, a1, n=10):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


poly_outline(pcbnew.Edge_Cuts, arc_pts(R_TOP, R_TOP, R_TOP, 180, 270) + arc_pts(W_B - R_TOP, R_TOP, R_TOP, 270, 360) +
             [(W_B, H_B), (nx1, H_B), (nx1, ny1), (tx1, ny1), (tx1, ty1),
              (tx0, ty1), (tx0, ny1), (nx0, ny1), (nx0, H_B), (0, H_B)], 0.1)

# --- nets --------------------------------------------------------------------
nets = {}


def net(name):
    if name not in nets:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n
    return nets[name]


# --- footprints ----------------------------------------------------------------
fps = {}


def load(ref):
    p = next(p for p in S.PARTS if p["ref"] == ref)
    lib, name = p["fp"].split(":")
    path = PROJ_LIB if lib == "BathMonitor" else os.path.join(FPDIR, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    assert fp, p["fp"]
    fp.SetReference(ref); fp.SetValue(p["value"])
    for pad in fp.Pads():
        n = p["nets"].get(pad.GetNumber())
        if n:
            pad.SetNet(net(n))
    board.Add(fp)
    fps[ref] = fp
    return fp


def place(ref, x, y, rot=0, back=True):
    fp = fps.get(ref) or load(ref)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(P(x, y))
    if back and fp.GetLayer() == pcbnew.F_Cu:
        fp.Flip(fp.GetPosition(), True)        # mirror left-right so "up" stays up
    return fp


def size(ref, rot=0):
    """Courtyard size (w, h) in mm at the given rotation (pads + 0.5 mm if no courtyard)."""
    fp = fps.get(ref) or load(ref)
    fp.SetOrientationDegrees(rot)
    xs, ys = [], []
    items = [g for g in fp.GraphicalItems() if g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd)]
    for it in items or fp.Pads():
        b = it.GetBoundingBox()
        xs += [b.GetLeft(), b.GetRight()]; ys += [b.GetTop(), b.GetBottom()]
    pad = 0 if items else 0.5
    return (max(xs) - min(xs)) / 1e6 + pad, (max(ys) - min(ys)) / 1e6 + pad


def pack(refs, x0, y0, x1, y1, gap=0.35, rot=0):
    """Place parts left-to-right in rows inside a rectangle (front-view coordinates)."""
    x, y, row_h = x0, y0, 0.0
    for ref in refs:
        w, h = size(ref, rot)
        if x + w > x1 + 1e-6:
            x, y, row_h = x0, y + row_h + gap, 0.0
        assert y + h <= y1 + 1e-6, f"region full at {ref}"
        place(ref, x + w / 2, y + h / 2, rot)
        x += w + gap
        row_h = max(row_h, h)


# ESP32-S3 module: antenna flush with the top edge, centred
place("U1", W_B / 2, 10.35)            # S3 body top (-10.35 in the footprint) on the board edge
# Qi receiver/charger column (left), next to the coil pads
place("U2", 5.6, 12.6)
pack(["C7", "C9", "C5", "C8", "C10", "C6"], 0.6, 5.6, 10.9, 10.4)
pack(["C1", "C2", "C3", "C4", "C11", "C21", "C12", "C13", "C22", "R1", "R2", "R3"], 0.6, 15.5, 10.9, 25.2, gap=0.25)
# power / housekeeping column (right)
place("U4", 32.3, 7.6)
pack(["C14", "C15", "C17", "C18", "R9", "C19", "Q1", "R4", "R5", "R6", "R7", "R8", "C16",
      "R18", "R19", "R10", "D1"], 27.2, 9.9, 37.4, 24.5)
# touch series resistors directly below the module's GPIO pads
pack(["R11", "R12", "R13", "R14", "R15", "R16", "R20", "R17"], 11.4, 21.2, 26.6, 23.8, gap=0.75, rot=90)
# wire pads (coil left / battery right) and pogo test pads (centre)
place("L1", 5.6, 27.0)
place("J1", 36.4, 27.0)
# battery thermistor on the back, under the top of the cell (thermal pad / foam presses it on)
place("TH1", 19.0, 52.5)
pack([f"TP{i}" for i in range(1, 9)], 7.4, 23.9, 26.3, 29.4, gap=0.2)
# thermal tab
place("U3", 19.0, 107.0, 90)
place("C20", 19.0, 110.3)
# electrodes on the FRONT copper
for k in range(1, 7):
    place(f"E{k}", (PAD_X0 + PAD_X1) / 2, pad_center_y(k), back=False)
place("E8", (PAD_X0 + PAD_X1) / 2, sum(REF_Y) / 2, back=False)
place("E7", 1.5, 31.2, back=False)        # shield tap via in the left shield strip

# TMP117 exposed pad -> GND for the thermal path
for pad in fps["U3"].Pads():
    if pad.GetNumber() not in [str(i) for i in range(1, 7)]:
        pad.SetNet(net("GND"))


# --- zones -----------------------------------------------------------------------
def zone(layer, netname, pts, hatch=None, prio=0, clearance=0.3, min_w=0.2):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if netname:
        z.SetNet(net(netname))
    o = z.Outline(); o.NewOutline()
    for x, y in pts:
        o.Append(mm(OX + x), mm(OY + y))
    z.SetLocalClearance(mm(clearance)); z.SetMinThickness(mm(min_w)); z.SetAssignedPriority(prio)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    if hatch:
        z.SetFillMode(pcbnew.ZONE_FILL_MODE_HATCH_PATTERN)
        z.SetHatchThickness(mm(hatch[0])); z.SetHatchGap(mm(hatch[1]))
    board.Add(z)
    return z


def box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


elec = box(0.4, ANT_Y + 0.4, W_B - 0.4, ELEC_TOP)
for layer in (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
    zone(layer, "GND", elec)
zone(pcbnew.In1_Cu, "GND", elec)
# driven shield: side strips on F.Cu, hatched plane on In1.Cu behind every electrode
zone(pcbnew.F_Cu, "SHIELD", box(0.4, SHIELD_Y[0], 2.5, SHIELD_Y[1]))
zone(pcbnew.F_Cu, "SHIELD", box(W_B - 2.5, SHIELD_Y[0], W_B - 0.4, SHIELD_Y[1]))
zone(pcbnew.In1_Cu, "SHIELD", box(0.4, SHIELD_Y[0], W_B - 0.4, SHIELD_Y[1]), hatch=(0.3, 0.7))
# thermal window on the tab: F.Cu + B.Cu GND copper stitched with vias
zone(pcbnew.F_Cu, "GND", box(tx0 + 0.6, ny1 + 0.4, tx1 - 0.6, ty1 - 0.6), clearance=0.2)
zone(pcbnew.B_Cu, "GND", box(tx0 + 0.6, ny1 + 0.4, tx1 - 0.6, ty1 - 0.6), clearance=0.2)
for vx in (16.0, 22.0):
    for vy in (105.5, 108.0, 110.5):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(P(vx, vy)); v.SetDrill(mm(0.3)); v.SetWidth(mm(0.6)); v.SetNet(net("GND"))
        board.Add(v)
# antenna keep-out across the whole width (matches the module's own rule area)
ka = pcbnew.ZONE(board)
ka.SetIsRuleArea(True)
ka.SetDoNotAllowCopperPour(True); ka.SetDoNotAllowTracks(True); ka.SetDoNotAllowVias(True)
ka.SetDoNotAllowPads(True); ka.SetDoNotAllowFootprints(False)
ls = pcbnew.LSET(); [ls.AddLayer(l) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)]
ka.SetLayerSet(ls)
o = ka.Outline(); o.NewOutline()
for x, y in box(0, 0, W_B, ANT_Y):
    o.Append(mm(OX + x), mm(OY + y))
board.Add(ka)

# --- mechanical context on user layers ---------------------------------------------
U = pcbnew.Dwgs_User
rect(U, 4.0, 50.0, 34.0, 90.0, 0.2); text(U, "Li-ion 403040, 500 mAh (behind PCB, B side)", 19, 60, 1.0)
circle(pcbnew.Cmts_User, 19.0, 70.0, 15.0, 0.2); text(pcbnew.Cmts_User, "Qi Rx coil 30 mm (against back wall)", 19, 88.5, 1.0)
rect(pcbnew.Eco1_User, -2.6, -3.0, W_B + 2.6, ty1 + 2.6, 0.2); text(pcbnew.Eco1_User, "enclosure inner wall", 19, ty1 + 1.6, 1.0)
for y, label in [(PAD6_TOP, "default alarm level (top of pad 6)"),
                 (pad_center_y(1) + PAD_H / 2, "wake: water reaches pad 1"),
                 (ANT_Y, "antenna above here: must stay dry")]:
    seg(pcbnew.Eco2_User, (-6, y), (W_B + 6, y), 0.15)
    text(pcbnew.Eco2_User, label, 19, y - 1.0, 0.9)

board.Save(OUT)
# zone filling is reliable only on a board loaded from disk (in-memory boards lack project settings)
board = pcbnew.LoadBoard(OUT)
board.BuildConnectivity()
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(OUT)
fps = {f.GetReference(): f for f in board.GetFootprints()}

# --- placement checks ---------------------------------------------------------------
issues = []
B = {r: f.GetBoundingBox(False, False) for r, f in fps.items()}
refs = [r for r in fps if not r.startswith("E")]
for i, a in enumerate(refs):
    for b in refs[i + 1:]:
        if fps[a].GetLayer() == fps[b].GetLayer():
            ca, cb = fps[a].GetCourtyard(fps[a].GetLayer() == pcbnew.B_Cu and pcbnew.B_CrtYd or pcbnew.F_CrtYd), \
                fps[b].GetCourtyard(fps[b].GetLayer() == pcbnew.B_Cu and pcbnew.B_CrtYd or pcbnew.F_CrtYd)
            if ca.OutlineCount() and cb.OutlineCount() and ca.Collide(cb):
                issues.append(f"courtyard overlap {a} / {b}")
edge = board.GetBoardEdgesBoundingBox()
for r, f in fps.items():
    if r in ("U1",):
        continue
    cy = f.GetCourtyard(pcbnew.B_CrtYd if f.GetLayer() == pcbnew.B_Cu else pcbnew.F_CrtYd)
    if cy.OutlineCount() and not edge.Contains(cy.BBox()):
        issues.append(f"{r} outside board bbox")
print(f"wrote {OUT}: {len(fps)} footprints, {len(nets)} nets")
print("placement issues:", issues or "none")
