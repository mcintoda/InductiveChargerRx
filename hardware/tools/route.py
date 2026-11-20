#!/usr/bin/env python3
"""Routing for the bath-monitor PCB (run after gen_pcb.py).

  python3 hardware/tools/route.py prep     # hand-routed lanes + vias, writes route/bath_monitor.dsn
  <autoroute route/bath_monitor.dsn -> route/bath_monitor.ses>   (Freerouting, see docs/pcb-routing.md)
  python3 hardware/tools/route.py finish   # import SES, GND stitching, refill zones, DRC report

Hand-routed (deterministic, because the geometry matters):
  * every electrode: a via inside the pad, then a straight B.Cu lane up to the electronics band.
    B.Cu sits behind the hatched In1 SHIELD, so the lanes never "see" the water.
  * TMP117 bus (SDA, SCL, SENSE_3V3, GND) and the battery NTC: straight B.Cu lanes through the
    electrode band, through the 6 mm neck to the thermal tab.
  * thermal vias in the BQ51050B and ESP32 module ground pads.
Autorouter constraints (written into the DSN only):
  * keep-out on every layer across the electrode band (only the hand lanes live there)
  * In1.Cu is not used for routing (solid GND / SHIELD plane); In2.Cu is a third routing layer, GND pour refilled
"""
import os
import re
import sys

import pcbnew

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "bath_monitor.kicad_pcb")
RDIR = os.path.join(HW, "kicad", "route")
DSN = os.path.join(RDIR, "bath_monitor.dsn")
SES = os.path.join(RDIR, "bath_monitor.ses")
OX, OY = 100.0, 50.0
TRACK = 0.2
BAND = (36.0, 101.5)          # electrode band (board y): autorouter keep-out on B.Cu / vias
FRONT_BAND = (30.5, 101.5)    # front copper keep-out starts at the shield strips / REF pad
# flash tab geometry (must match gen_pcb.py FTAB / FSLOTS)
W_B, FTAB_X0, FTAB_Y, FSLOTS = 38.0, 39.5, (9.5, 21.5), [(11.5, 14.0), (17.0, 19.5)]
LANE_TOP = 29.8               # lanes end here; the autorouter takes over above


def mm(v):
    return int(round(v * 1e6))


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def bxy(p):
    return (p.x / 1e6 - OX, p.y / 1e6 - OY)


def track(board, net, a, b, layer=pcbnew.B_Cu, w=TRACK):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(P(*a)); t.SetEnd(P(*b)); t.SetLayer(layer); t.SetWidth(mm(w)); t.SetNet(net)
    t.SetLocked(True)                     # exported as (type protect): the autorouter keeps it
    board.Add(t)


def via(board, net, xy, d=0.6, drill=0.3):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(*xy)); v.SetWidth(mm(d)); v.SetDrill(mm(drill)); v.SetNet(net)
    v.SetLocked(True)
    board.Add(v)


def pads(fp):
    return {p.GetNumber(): p for p in fp.Pads() if p.GetNumber()}


def prep():
    import subprocess
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "gen_pcb.py")], check=True)
    board = pcbnew.LoadBoard(PCB)
    # always starts from a fresh placement: gen_pcb.py rebuilds the board without any routing
    # rules: KiCad defaults (0.2 mm track / 0.2 mm clearance / 0.6-0.3 mm via) suit JLC 4-layer
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    net = lambda n: board.FindNet(n)  # noqa: E731

    # --- electrodes: via in each pad, lane up on B.Cu ---
    lanes = {"E8": 12.4, "E6": 13.0, "E5": 13.6, "E4": 14.2, "E3": 14.8, "E2": 15.4, "E1": 16.0}
    for ref, x in lanes.items():
        p = pads(fps[ref])["1"]
        _, y = bxy(p.GetPosition())
        via(board, p.GetNet(), (x, y))
        track(board, p.GetNet(), (x, y), (x, LANE_TOP))

    # --- battery NTC (TH1 on B.Cu): NTC pad up, GND pad over to the GND lane ---
    th = pads(fps["TH1"])
    ntc, gnd = th["1"], th["2"]
    nx, ny = bxy(ntc.GetPosition()); gx, gy = bxy(gnd.GetPosition())
    # TMP117 bus lanes (bottom end just above the neck)
    tmp_lanes = {"SDA": 17.6, "SCL": 18.4, "SENSE_3V3": 19.2, "GND": 20.6}
    for n, x in tmp_lanes.items():
        track(board, net(n), (x, BAND[1] + 0.6), (x, LANE_TOP))   # both ends outside the keep-outs
    # the GND lane is tied straight into the pours: via to In1/In2 GND at the top, into the tab pour at the bottom
    gx_l = tmp_lanes["GND"]
    track(board, net("GND"), (gx_l, LANE_TOP), (gx_l, 28.6)); via(board, net("GND"), (gx_l, 28.6))
    track(board, net("GND"), (gx_l, BAND[1] + 0.6), (gx_l, 104.8))
    # NTC: from its pad straight right then up on its own lane (x = 22.2)
    track(board, ntc.GetNet(), (nx, ny), (22.2, ny)); track(board, ntc.GetNet(), (22.2, ny), (22.2, LANE_TOP))
    # TH1 GND pad joins the GND lane through a short stub downwards then across (stays clear of the NTC stub)
    track(board, gnd.GetNet(), (gx, gy), (gx, gy + 1.2)); track(board, gnd.GetNet(), (gx, gy + 1.2), (tmp_lanes["GND"], gy + 1.2))

    # --- thermal vias: BQ51050B exposed pad (2 x 2) and the ESP32 module ground pad (3 x 3 grid corners) ---
    u2 = pads(fps["U2"]).get("21")
    if u2:
        cx, cy = bxy(u2.GetPosition())
        for dx in (-0.6, 0.6):
            for dy in (-0.6, 0.6):
                via(board, u2.GetNet(), (cx + dx, cy + dy))
    gnd_module = [p for p in fps["U1"].Pads() if p.GetNetname() == "GND" and p.GetSize().x > mm(0.8)]
    if gnd_module:
        xs = [bxy(p.GetPosition())[0] for p in gnd_module]; ys = [bxy(p.GetPosition())[1] for p in gnd_module]
        mcx, mcy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        for dx in (-0.6, 0.6):
            for dy in (-0.6, 0.6):
                via(board, gnd_module[0].GetNet(), (mcx + dx, mcy + dy))

    board.Save(PCB)
    os.makedirs(RDIR, exist_ok=True)
    assert pcbnew.ExportSpecctraDSN(board, DSN), "DSN export failed"
    constrain_dsn()
    print(f"prep done: {len(board.GetTracks())} hand-routed items, DSN -> {os.path.relpath(DSN, HW)}")


def again():
    """Second autorouter pass from the current routing: hand-routed / stitching copper stays protected
    (locked), the first pass's wires may be ripped up and moved to finish the last connections."""
    board = pcbnew.LoadBoard(PCB)
    assert pcbnew.ExportSpecctraDSN(board, DSN), "DSN export failed"
    constrain_dsn(protect_all=False)
    n = sum(1 for t in board.GetTracks() if not t.IsLocked())
    print(f"DSN with {n} movable autorouted items -> {os.path.relpath(DSN, HW)}; run the autorouter, then finish")


def constrain_dsn(protect_all=True):
    """Autorouter-only constraints: inner layers not routable, keep-out over the electrode band."""
    s = open(DSN).read()
    s = re.sub(r"\(layer In1\.Cu\s*\(type signal\)", "(layer In1.Cu (type power)", s)
    # In2 stays a signal layer: the third routing layer in the crowded electronics band. Its GND pour is
    # refilled around the traces afterwards; In1 remains the solid GND reference under everything.
    # DSN coordinates are in um with y up (KiCad exports y negated)
    x0, x1 = (OX - 1) * 1000, (OX + 39) * 1000
    y0, y1 = -(OY + BAND[1]) * 1000, -(OY + BAND[0]) * 1000
    fy0, fy1 = -(OY + FRONT_BAND[1]) * 1000, -(OY + FRONT_BAND[0]) * 1000
    ko = f"\n    (keepout \"\" (rect F.Cu {x0:.0f} {fy0:.0f} {x1:.0f} {fy1:.0f}))"
    ko += f"\n    (keepout \"\" (rect B.Cu {x0:.0f} {y0:.0f} {x1:.0f} {y1:.0f}))"
    ko += f"\n    (via_keepout \"\" (rect signal {x0:.0f} {y0:.0f} {x1:.0f} {y1:.0f}))"
    # flash tab: copper crosses only the middle bridge; 0.5 mm edge clearance round the slots and outer bridges
    for ya, yb in [(FTAB_Y[0] - 0.5, FSLOTS[0][1] + 0.5), (FSLOTS[1][0] - 0.5, FTAB_Y[1] + 0.5)]:
        for lay in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
            ko += (f"\n    (keepout \"\" (rect {lay} {(OX + W_B - 0.5) * 1000:.0f} {-(OY + yb) * 1000:.0f} "
                   f"{(OX + FTAB_X0 + 0.5) * 1000:.0f} {-(OY + ya) * 1000:.0f}))")
    i = s.index("    (boundary")                 # after the layer definitions
    s = s[:i] + ko.lstrip("\n") + "\n" + s[i:]
    # hand-routed wires and vias are fixed: the autorouter must not move or rip them up
    if protect_all:
        s = s.replace("(type route)", "(type protect)")
    open(DSN, "w").write(s)


def finish():
    board = pcbnew.LoadBoard(PCB)
    assert os.path.exists(SES), f"missing {SES}: run the autorouter first"
    # the session holds every autorouted wire (a second pass re-emits the first pass's too): start clean
    for t in list(board.GetTracks()):
        if not t.IsLocked():
            board.Remove(t)
    import_ses(board, SES)
    board.Save(PCB)
    board = pcbnew.LoadBoard(PCB)
    stitch(board)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    rep = os.path.join(RDIR, "drc.rpt")
    pcbnew.WriteDRCReport(board, rep, pcbnew.EDA_UNITS_MILLIMETRES, True)
    print(open(rep).read()[-600:])


def import_ses(board, path):
    """Add the autorouter's wires and vias (KiCad 7's ImportSpecctraSES only works inside the GUI)."""
    import sexp
    ses = sexp.parse(open(path).read())
    routes = sexp.find(ses, "routes")[0]
    res = sexp.find(routes, "resolution")[0]
    scale = {"um": 1e-3, "mm": 1.0, "mil": 0.0254, "inch": 25.4}[res[1]] / float(res[2])   # -> mm
    xy = lambda x, y: pcbnew.VECTOR2I(pcbnew.FromMM(float(x) * scale), pcbnew.FromMM(-float(y) * scale))  # noqa: E731
    layers = {board.GetLayerName(l): l for l in range(pcbnew.PCB_LAYER_ID_COUNT)}
    stacks = {}
    for lib in sexp.find(routes, "library_out"):
        for ps in sexp.find(lib, "padstack"):
            m = re.search(r"_(\d+):(\d+)_um", ps[1])
            if m: stacks[ps[1]] = (int(m.group(1)) / 1000, int(m.group(2)) / 1000)
    n_w = n_v = 0
    for net in sexp.find(sexp.find(routes, "network_out")[0], "net"):
        kn = board.FindNet(net[1])
        for w in sexp.find(net, "wire"):
            if sexp.find(w, "type"):                  # protected: the hand-routed copper already on the board
                continue
            path = sexp.find(w, "path")[0]
            lay, width, pts = layers[path[1]], float(path[2]) * scale, path[3:]
            for i in range(0, len(pts) - 2, 2):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(xy(pts[i], pts[i + 1])); t.SetEnd(xy(pts[i + 2], pts[i + 3]))
                t.SetWidth(pcbnew.FromMM(width)); t.SetLayer(lay); t.SetNet(kn)
                board.Add(t); n_w += 1
        for v in sexp.find(net, "via"):
            if sexp.find(v, "type"):
                continue
            dia, drill = stacks.get(v[1], (0.6, 0.3))
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(xy(v[2], v[3])); via.SetWidth(pcbnew.FromMM(dia)); via.SetDrill(pcbnew.FromMM(drill))
            via.SetNet(kn)
            board.Add(via); n_v += 1
    print(f"imported {n_w} track segments, {n_v} vias")


def stitch(board, pitch=2.5):
    """GND stitching vias on a grid in the electronics band, wherever they clear everything."""
    gnd = board.FindNet("GND")
    placed = 0
    y = 6.0
    while y < 29.0:
        x = 1.2
        while x < 37.0:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(P(x, y)); v.SetWidth(mm(0.6)); v.SetDrill(mm(0.3)); v.SetNet(gnd)
            if clear(board, v):
                v.SetLocked(True); board.Add(v); placed += 1
            x += pitch
        y += pitch
    print(f"stitching vias: {placed} on the grid, {island_vias(board, gnd)} into GND islands")


def island_vias(board, gnd, step=0.4):
    """Every filled GND island on an outer layer gets at least one via to the inner GND planes."""
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    added = 0
    for z in board.Zones():
        if z.GetNetname() != "GND" or z.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
            continue
        polys = z.GetFilledPolysList(z.GetLayer())
        for i in range(polys.OutlineCount()):
            outline = polys.Outline(i)
            bb = outline.BBox()
            done = False
            # an island already holding a GND via or a GND through-hole is connected
            for t in board.GetTracks():
                if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gnd.GetNetCode() and outline.PointInside(t.GetPosition()):
                    done = True; break
            y = bb.GetY() + mm(0.4)
            while not done and y < bb.GetBottom():
                x = bb.GetX() + mm(0.4)
                while x < bb.GetRight():
                    pos = pcbnew.VECTOR2I(int(x), int(y))
                    if outline.PointInside(pos):
                        v = pcbnew.PCB_VIA(board)
                        v.SetPosition(pos); v.SetWidth(mm(0.6)); v.SetDrill(mm(0.3)); v.SetNet(gnd)
                        if clear(board, v, margin=0.2) and inside_gnd_planes(board, pos):
                            v.SetLocked(True); board.Add(v); added += 1; done = True; break
                    x += mm(step)
                y += mm(step)
    return added


def inside_gnd_planes(board, pos):
    for z in board.Zones():
        if z.GetNetname() == "GND" and z.GetLayer() in (pcbnew.In1_Cu, pcbnew.In2_Cu) and z.Outline().Contains(pos):
            return True
    return False


def clear(board, v, margin=0.25):
    pos, r = v.GetPosition(), v.GetWidth() / 2 + mm(margin)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetBoundingBox().Inflate(int(r)).Contains(pos):
                return False
        cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.GetLayer() == pcbnew.B_Cu else pcbnew.F_CrtYd)
        if fp.GetLayer() == pcbnew.B_Cu and cy.OutlineCount() and cy.Contains(pos):
            return False
    for t in board.GetTracks():
        if t.HitTest(pos, int(r)):
            return False
    return True


if __name__ == "__main__":
    {"prep": prep, "finish": finish, "again": again}[sys.argv[1]]()
