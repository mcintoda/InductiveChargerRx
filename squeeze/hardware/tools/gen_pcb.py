#!/usr/bin/env python3
"""Build squeeze/hardware/kicad/squeeze.kicad_pcb from parts.py (KiCad 7 pcbnew API).

Board: 4 layers, 1.0 mm, all parts on top (one-sided JLC assembly).
  * Outline: the base pocket's ellipse (43.2 x 33.2 mm) with notches for the two base screw bosses,
    a flat for the USB-C mouth, and a break-off LED tab (mouse bites) above the top edge.
  * In1 = solid GND, F.Cu / B.Cu GND pours, In2 = signals. The Qi coil lies under the board,
    ferrite side up.
  * Placement here; routing by route.py.

    python3 squeeze/hardware/tools/gen_pcb.py
"""
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import parts as PT  # noqa: E402

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(HW, "kicad", "squeeze.kicad_pcb")
FPDIR = "/usr/share/kicad/footprints"
LOCAL = os.path.join(HW, "kicad", "Squeeze.pretty")
OX, OY = 100.0, 100.0                       # board centre on the sheet

# outline (board frame: x right, y down, mm; same X as the CAD, Y = -CAD Y)
EA, EB = 21.6, 16.6                         # base pocket ellipse 22.5 x 17.5 minus 0.9 clearance
NOTCH_X, NOTCH_R = 19.5, 2.9                # screw bosses (r 2.4) + 0.5
FLAT_Y = 13.5                               # USB-C mouth edge
TAB = (-4.0, -24.0, 4.0, -18.1)             # LED tab (x0, y0, x1, y1), joined by 2 necks with mouse bites
THICK = 1.0

TRACK, CLEAR, VIA_D, VIA_H = 0.2, 0.15, 0.5, 0.25


def mm(v):
    return int(round(v * 1e6))


def V(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


# ---------------------------------------------------------------- placement (x, y, rotation deg)
PLACE = {
    # ESP32 module, rotated 180: GND row faces the USB-C, GPIO row (y = -8.6) faces the top
    "U1": (-9.4, -2.6, 180),
    "C30": (-1.2, 1.0, 90), "C31": (-1.2, -1.6, 0), "R31": (-1.2, -2.6, 0), "R30": (-1.2, -4.4, 0), "C32": (-1.2, -5.4, 0),
    # top left: BMP280 over SDA/SCL (module pins at x -11.0 / -11.8), CHG pull-up, LDO
    "U4": (-11.0, -11.6, 0), "C25": (-13.6, -10.4, 90), "R6": (-8.4, -10.2, 0), "R7": (-8.4, -11.2, 0),
    "R32": (-15.0, -10.4, 90),
    "U3": (-4.4, -12.6, 90), "C14": (-6.8, -12.6, 90), "C15": (-2.0, -11.8, 90),
    # LED resistors and the LED wire pads under the tab
    "R16": (0.8, -10.2, 0), "R17": (0.8, -11.2, 0), "R18": (0.8, -12.2, 0), "J4": (0.6, -14.6, 0),
    # battery divider near GPIO0 (module pin at -4.6, -8.6)
    "R4": (-1.2, -7.2, 0), "R5": (-1.2, -8.2, 0), "C24": (-3.4, -10.0, 0),
    # Qi charger
    "L1": (6.4, -12.6, 0),
    "C1": (3.4, -9.6, 90), "C2": (5.0, -9.6, 90), "C3": (6.6, -9.6, 90), "C23": (2.2, -8.0, 90),
    "U2": (8.6, -4.2, 0),
    "C4": (9.0, -7.8, 0), "C5": (5.0, -5.8, 0), "C9": (5.0, -3.4, 0), "C7": (4.9, -4.6, 0),
    "C6": (12.4, -5.2, 180), "C10": (12.4, -2.6, 180), "C8": (12.3, -3.9, 180),
    "C11": (15.2, -5.2, 90), "C21": (17.3, -5.2, 90), "C12": (12.4, -6.2, 0), "TP7": (14.6, -10.6, 0),
    "R1": (12.4, -1.6, 0), "R2": (14.2, -1.6, 90), "R3": (7.6, -0.4, 0), "TH1": (10.0, -0.4, 0),
    "C13": (5.0, -2.2, 0), "C22": (5.0, -1.2, 0),
    # battery pads on the right, between the screw notch and the boost
    "J1": (17.6, 4.2, 90),
    # 5 V boost for the servo, bottom right
    "U5": (10.8, 7.4, 0), "L2": (6.6, 8.6, 0), "C16": (6.6, 5.4, 0),
    "C17": (13.8, 5.8, 90), "C18": (13.8, 9.4, 90), "C19": (11.0, 10.6, 0),
    "R8": (10.6, 5.4, 0), "R9": (12.2, 4.4, 90), "R10": (8.8, 5.4, 90), "TP6": (16.2, 8.2, 0),
    "R11": (2.4, 9.4, 90), "J2": (2.4, 12.0, 0),
    # USB-C, bottom left; mouth on the flat
    "J3": (-6.6, FLAT_Y - 3.65, 0), "R12": (-12.8, 6.6, 90), "R13": (-0.4, 6.6, 90),
    "R14": (-14.0, 6.6, 90), "R15": (-15.2, 6.6, 90), "TP3": (-17.2, 5.4, 0),
    # test pads, left
    "TP1": (-17.4, -8.0, 0), "TP2": (-17.8, -3.4, 0), "TP5": (-17.8, -5.6, 0),
    # LED tab
    "D1": (0.0, -22.4, 0), "J5": (0.0, -19.6, 0),
}
SILK = [  # (text, x, y, size)
    ("+", 16.4, 3.35, 0.7), ("-", 16.4, 5.85, 0.7), ("BAT", 17.6, 1.9, 0.5),
    ("5V GND SIG", 2.4, 13.6, 0.5), ("SERVO", -1.4, 12.0, 0.5), ("COIL", 6.4, -14.1, 0.5),
    ("A R G B", 0.6, -15.9, 0.45), ("A R G B", 0.0, -18.75, 0.45),
    ("squeeze rev A", -9.4, 4.4, 0.5),
]


def load(fpid):
    lib, name = fpid.split(":")
    path = LOCAL if lib == "Squeeze" else os.path.join(FPDIR, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit(f"footprint not found: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def seg(board, a, b, layer=pcbnew.Edge_Cuts, w=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(V(*a)); s.SetEnd(V(*b)); s.SetLayer(layer); s.SetWidth(mm(w))
    board.Add(s)


def y_edge(x):
    """Top edge (y < 0) of the ellipse at x."""
    return -EB * math.sqrt(max(0.0, 1 - (x / EA) ** 2))


NECK = (1.45, 2.95)                         # tab necks span |x| in this range


def ellipse_points(n=720):
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x, y = EA * math.cos(t), EB * math.sin(t)
        y = min(y, FLAT_Y)
        for sx in (-1, 1):                               # screw notches
            dx, dy = x - sx * NOTCH_X, y
            if math.hypot(dx, dy) < NOTCH_R:
                ang = math.atan2(dy, dx)
                x, y = sx * NOTCH_X + NOTCH_R * math.cos(ang), NOTCH_R * math.sin(ang)
        pts.append((x, y))
    return pts


def outline_loops():
    """Outer contour (board + LED tab joined by two necks) and the slot between the necks."""
    x0, y0, x1, y1 = TAB
    n0, n1 = NECK
    outer, slot_top, spliced = [], [], False
    for x, y in ellipse_points():
        if y < 0 and abs(x) < n1:
            if abs(x) < n0:
                slot_top.append((x, y))
            if not spliced:
                spliced = True
                outer += [(-n1, y_edge(-n1)), (-n1, y1), (x0, y1), (x0, y0), (x1, y0), (x1, y1), (n1, y1),
                          (n1, y_edge(n1))]
            continue
        outer.append((x, y))
    slot = [(-n0, y_edge(-n0)), (-n0, y1), (n0, y1), (n0, y_edge(n0))] + sorted(slot_top, reverse=True)
    return outer, slot


def add_outline(board):
    outer, slot = outline_loops()
    for loop in (outer, slot):
        for a, b in zip(loop, loop[1:] + loop[:1]):
            seg(board, a, b, w=0.05)
    return [p for p in ellipse_points()]


def add_mouse_bites(board):
    """0.5 mm non-plated holes on the board edge line across each neck: snap the tab off there."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("MB1"); fp.SetValue("mouse bites"); fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
    fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_BOARD_ONLY)
    board.Add(fp)
    fp.SetPosition(V(0, 0))
    for sx in (-1, 1):
        for x in (1.825, 2.575):                       # 0.5 mm holes, 0.25 mm apart
            pad = pcbnew.PAD(fp)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I(mm(0.5), mm(0.5))); pad.SetDrillSize(pcbnew.VECTOR2I(mm(0.5), mm(0.5)))
            pad.SetLayerSet(pad.UnplatedHoleMask())
            fp.Add(pad)
            pad.SetPos0(pcbnew.VECTOR2I(mm(sx * x), mm(y_edge(x) - 0.1)))   # relative to the footprint at (0, 0)
            pad.SetPosition(V(sx * x, y_edge(x) - 0.1))


def place(board):
    nets = {}
    for n in sorted({n for p in PT.PARTS for n in p["nets"].values() if n}):
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        nets[n] = ni
    for p in PT.PARTS:
        fp = load(p["fp"])
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        board.Add(fp)
        x, y, r = PLACE[p["ref"]]
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(r)
        for pad in fp.Pads():
            n = p["nets"].get(pad.GetName())
            if n:
                pad.SetNet(nets[n])
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.5), mm(0.5)))
        fp.Reference().SetTextThickness(mm(0.08))
        fp.Reference().SetVisible(False)                 # too dense for designators; see docs/pcb.png
        if not p["placed"]:
            fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    return nets


def zone(board, net, layer, pts, prio=0, clearance=0.2):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if net is not None:
        z.SetNet(net)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(OX + x), mm(OY + y))
    z.SetLocalClearance(mm(clearance))
    z.SetMinThickness(mm(0.2))
    z.SetAssignedPriority(prio)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)    # SMD pads solid, wire pads with reliefs
    z.SetThermalReliefGap(mm(0.25))
    z.SetThermalReliefSpokeWidth(mm(0.3))
    board.Add(z)
    return z


def thermal_vias(board, nets):
    gnd = nets["GND"]
    pts = []
    u1 = board.FindFootprintByReference("U1")
    for pad in u1.Pads():
        if pad.GetName() == "49":
            pts.append(pad.GetPosition())
    u2 = board.FindFootprintByReference("U2")
    # several pads are named 21 (the exposed pad and four corner tabs): use the big one
    ep = max((p for p in u2.Pads() if p.GetName() == "21"), key=lambda p: p.GetSize().x * p.GetSize().y).GetPosition()
    for dx, dy in ((-0.45, -0.45), (0.45, -0.45), (-0.45, 0.45), (0.45, 0.45), (0, 0)):
        pts.append(pcbnew.VECTOR2I(ep.x + mm(dx), ep.y + mm(dy)))
    for p in pts:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(p); v.SetWidth(mm(VIA_D)); v.SetDrill(mm(VIA_H)); v.SetNet(gnd)
        board.Add(v)


def setup(board):
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(THICK))
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_MinClearance = mm(CLEAR)
    ds.m_ViasMinSize = mm(0.45)
    ds.m_MinThroughDrill = mm(0.2)
    ds.m_CopperEdgeClearance = mm(0.3)
    nc = ds.m_NetSettings.m_DefaultNetClass
    nc.SetTrackWidth(mm(TRACK)); nc.SetClearance(mm(CLEAR)); nc.SetViaDiameter(mm(VIA_D)); nc.SetViaDrill(mm(VIA_H))


def main():
    # start from a fresh project file: autoroute.py adds net classes to it, and they must not pile up
    for ext in (".kicad_pro", ".kicad_prl"):
        if os.path.exists(OUT[:-len(".kicad_pcb")] + ext):
            os.remove(OUT[:-len(".kicad_pcb")] + ext)
    board = pcbnew.BOARD()
    setup(board)
    pts = add_outline(board)
    nets = place(board)
    add_mouse_bites(board)
    for t, x, y, s in SILK:
        tx = pcbnew.PCB_TEXT(board)
        tx.SetText(t); tx.SetPosition(V(x, y)); tx.SetLayer(pcbnew.F_SilkS)
        tx.SetTextSize(pcbnew.VECTOR2I(mm(s), mm(s))); tx.SetTextThickness(mm(0.1))
        board.Add(tx)
    shrink = [(x * 0.999, y * 0.999) for x, y in pts]
    for lay in (pcbnew.In1_Cu, pcbnew.F_Cu, pcbnew.B_Cu):
        zone(board, nets["GND"], lay, shrink, prio=0)
    thermal_vias(board, nets)
    board.Save(OUT)
    # zone filling is reliable only on a board loaded from disk (as brim's gen_pcb.py)
    board = pcbnew.LoadBoard(OUT)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(OUT)
    print("wrote", os.path.relpath(OUT), len(PT.PARTS), "footprints")


if __name__ == "__main__":
    main()
