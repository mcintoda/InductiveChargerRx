#!/usr/bin/env python3
"""Rev A hand fixes. Steps 1-3 are now planned at placement (gen_pcb.py u2_fanout); kept for reference
(--legacy). The pipeline uses only --gnd and --final, after route.py.

U2 (BQ51050B) has VBAT (pin 4) between BOOT1 (pin 3) and CLAMP1 (pin 5), and COMM2 (pin 15) has to
cross the FOD / NTC exits to reach C10. The autorouters leave both open. Fixes:
  1. VBAT: one 0.45/0.2 mm via exactly between the BOOT1 and CLAMP1 lanes (y of pin 4), stub from pin 4;
     any other VBAT via in that gap is removed (route.py reconnects the via to the rest of VBAT).
  2. BOOT1: C5 pad 2 -> pin 3, straight in at the pin's y.
  3. COMM2: stub + 0.45/0.2 via straight out of pin 15; route.py takes it to C10 on an inner layer.
     C8 moves 0.4 mm right and C7 0.3 mm left to make room for the two vias; route.py re-routes
     their tracks.

    python3 squeeze/hardware/tools/hand_fixes_revA.py && python3 squeeze/hardware/tools/route.py
    python3 squeeze/hardware/tools/hand_fixes_revA.py --gnd        # after route.py: GND pad escapes (4.)

  4. --gnd: GND pads left on a top-layer pour island without a via get a short track + 0.45/0.2 via.
  5. --final: join the VBAT via to its dangling In2 ends; FOD escape via beside U2 pin 14; then route.py again.
"""
import math
import os
import sys

import pcbnew

HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(HW, "kicad", "squeeze.kicad_pcb")
OX, OY = 100.0, 100.0


def mm(v):
    return int(round(v * 1e6))


def V(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def loc(item):
    p = item.GetPosition()
    return p.x / 1e6 - OX, p.y / 1e6 - OY


def track(b, net, pts, w=0.2, layer=pcbnew.F_Cu):
    for a, c in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(V(*a)); t.SetEnd(V(*c)); t.SetWidth(mm(w)); t.SetLayer(layer); t.SetNet(b.FindNet(net))
        b.Add(t)


def via(b, net, x, y, d=0.45, drill=0.2):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(x, y)); v.SetWidth(mm(d)); v.SetDrill(mm(drill)); v.SetNet(b.FindNet(net))
    b.Add(v)


def clear_box(b, x0, y0, x1, y1, nets):
    """Delete tracks/vias of these nets with an end (or position) inside the box."""
    gone = 0
    for t in list(b.GetTracks()):
        if t.GetNetname() not in nets:
            continue
        pts = [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]
        if any(x0 <= p.x / 1e6 - OX <= x1 and y0 <= p.y / 1e6 - OY <= y1 for p in pts):
            b.Delete(t); gone += 1
    return gone


def pad_box(p):
    bb = p.GetBoundingBox()
    return (bb.GetX() / 1e6 - OX, bb.GetY() / 1e6 - OY, (bb.GetX() + bb.GetWidth()) / 1e6 - OX,
            (bb.GetY() + bb.GetHeight()) / 1e6 - OY)


def move_part(b, ref, x, y, nets):
    """Move a footprint to (x, y) (same as gen_pcb.py PLACE) and delete the tracks of `nets` that ended on its
    old pads. Idempotent: does nothing if it is already there."""
    fp = b.FindFootprintByReference(ref)
    if abs(loc(fp)[0] - x) < 1e-3 and abs(loc(fp)[1] - y) < 1e-3:
        return 0
    old = [loc(p) for p in fp.Pads()]
    fp.SetPosition(V(x, y))
    gone = 0
    for t in list(b.GetTracks()):
        if t.GetNetname() not in nets:
            continue
        pts = [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]
        if any(abs(q.x / 1e6 - OX - ox) < 0.6 and abs(q.y / 1e6 - OY - oy) < 0.6 for q in pts for ox, oy in old):
            b.Delete(t); gone += 1
    return gone


def gnd_escapes(b):
    """GND SMD pads whose top-layer pour fragment holds no via: a short track to a 0.45/0.2 via into In1,
    at the nearest spot (ring search) that clears all other copper by 0.15 mm."""
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    gnd = b.FindNet("GND")
    gc = gnd.GetNetCode()
    edge = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(edge)
    edge.Deflate(mm(0.6), 16)
    zf = [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetCode() == gc and z.IsOnLayer(pcbnew.F_Cu)][0]
    frags = zf.GetFilledPolysList(pcbnew.F_Cu)
    holes = [t.GetPosition() for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gc]
    holes += [q.GetPosition() for f in b.GetFootprints() for q in f.Pads() if q.GetNetCode() == gc and q.HasHole()]

    CU = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    others = [q for f in b.GetFootprints() for q in f.Pads() if q.GetNetCode() != gc]
    hole_items = [q for f in b.GetFootprints() for q in f.Pads() if q.HasHole()]

    def free(pos, r):
        """A via of radius r (incl. clearance) at pos touches no other-net copper on any layer, no hole."""
        circ = pcbnew.SHAPE_CIRCLE(pos, int(r))
        for q in others:
            for lay in CU:
                if q.IsOnLayer(lay) and q.GetEffectiveShape(lay).Collide(circ, 0):
                    return False
        for q in hole_items:
            if (q.GetPosition() - pos).EuclideanNorm() < r + q.GetDrillSize().x / 2 + mm(0.1):
                return False
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                if (t.GetPosition() - pos).EuclideanNorm() < r + t.GetWidth() / 2 + mm(0.05):
                    return False
            elif t.GetNetCode() != gc and t.GetEffectiveShape().Collide(circ, 0):
                return False
        return edge.Contains(pos)

    added = []
    for f in b.GetFootprints():
        for q in f.Pads():
            if q.GetNetCode() != gc or q.HasHole() or not q.IsOnLayer(pcbnew.F_Cu):
                continue
            frag = None
            for o in range(frags.OutlineCount()):
                if frags.Outline(o).PointInside(q.GetPosition()):
                    frag = frags.Outline(o)
            if frag is None or any(frag.PointInside(h) for h in holes):
                continue
            c = q.GetPosition()
            done = False
            for rad in [x * 0.1 for x in range(5, 25)]:
                for k in range(24):
                    a = 2 * 3.14159265 * k / 24
                    pos = pcbnew.VECTOR2I(c.x + mm(rad * math.cos(a)), c.y + mm(rad * math.sin(a)))
                    if not free(pos, mm(0.225 + 0.15)):
                        continue
                    # the track from the pad edge to the via must clear other copper too
                    t = pcbnew.PCB_TRACK(b); t.SetStart(c); t.SetEnd(pos); t.SetWidth(mm(0.2)); t.SetLayer(pcbnew.F_Cu)
                    seg = t.GetEffectiveShape()
                    ok = all(not (o.IsOnLayer(pcbnew.F_Cu) and seg.Collide(o.GetEffectiveShape(pcbnew.F_Cu), mm(0.15)))
                             for o in [x for x in b.GetTracks() if x.GetNetCode() != gc] + others)
                    if not ok:
                        continue
                    t.SetNet(gnd); b.Add(t)
                    v = pcbnew.PCB_VIA(b); v.SetPosition(pos); v.SetWidth(mm(0.45)); v.SetDrill(mm(0.2)); v.SetNet(gnd)
                    b.Add(v); holes.append(pos)
                    added.append(f"{f.GetReference()}.{q.GetName()}"); done = True
                    break
                if done:
                    break
            if not done:
                print("  no GND escape found for", f.GetReference(), q.GetName())
    return added


def collides(b, shape, layer, net, clr=0.15):
    """Does a new copper shape on `layer` hit other-net copper (pads, tracks, vias) or a hole?"""
    nc = b.FindNet(net).GetNetCode()
    for f in b.GetFootprints():
        for q in f.Pads():
            if q.GetNetCode() != nc and q.IsOnLayer(layer) and q.GetEffectiveShape(layer).Collide(shape, mm(clr)):
                return True
            if q.HasHole() and q.GetNetCode() != nc and q.GetEffectiveHoleShape().Collide(shape, mm(0.25)):
                return True
    for t in b.GetTracks():
        if t.GetNetCode() == nc:
            continue
        if (t.GetClass() == "PCB_VIA" or t.GetLayer() == layer) and t.GetEffectiveShape(layer).Collide(shape, mm(clr)):
            return True
    return False


def escape_via(b, ref, padname, net, radii=(0.7, 0.85, 1.0, 1.2, 1.4)):
    """Stub + 0.45/0.2 via next to a pad, at the first spot whose via (all layers) and stub (F.Cu) are clear."""
    q = [p for p in b.FindFootprintByReference(ref).Pads() if p.GetName() == padname][0]
    c = q.GetPosition()
    fc = b.FindFootprintByReference(ref).GetPosition()
    base = math.atan2(c.y - fc.y, c.x - fc.x)
    edge = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(edge); edge.Deflate(mm(0.6), 16)
    for r in radii:
        for k in (0, 1, -1, 2, -2, 3, -3):
            a = base + k * math.pi / 12
            pos = pcbnew.VECTOR2I(c.x + mm(r * math.cos(a)), c.y + mm(r * math.sin(a)))
            circ = pcbnew.SHAPE_CIRCLE(pos, mm(0.225))
            seg = pcbnew.SHAPE_SEGMENT(c, pos, mm(0.2))
            if not edge.Contains(pos) or collides(b, seg, pcbnew.F_Cu, net):
                continue
            if any(collides(b, circ, lay, net) for lay in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)):
                continue
            if any(t.GetClass() == "PCB_VIA" and (t.GetPosition() - pos).EuclideanNorm() < mm(0.45 + 0.2)
                   for t in b.GetTracks()):
                continue
            t = pcbnew.PCB_TRACK(b); t.SetStart(c); t.SetEnd(pos); t.SetWidth(mm(0.2)); t.SetLayer(pcbnew.F_Cu)
            t.SetNet(b.FindNet(net)); b.Add(t)
            v = pcbnew.PCB_VIA(b); v.SetPosition(pos); v.SetWidth(mm(0.45)); v.SetDrill(mm(0.2))
            v.SetNet(b.FindNet(net)); b.Add(v)
            return (pos.x / 1e6 - OX, pos.y / 1e6 - OY)
    return None


def join_dangling(b, net, via_xy, layer=pcbnew.In2_Cu, reach=2.0):
    """Connect a via to dangling track ends of its net on `layer` within `reach` mm, where the link is clear."""
    vpos = V(*via_xy)
    ends = {}
    for t in b.GetTracks():
        if t.GetNetname() == net and t.GetClass() != "PCB_VIA" and t.GetLayer() == layer:
            for e in (t.GetStart(), t.GetEnd()):
                ends[(e.x, e.y)] = ends.get((e.x, e.y), 0) + 1
    joined = 0
    for (x, y), n in ends.items():
        e = pcbnew.VECTOR2I(x, y)
        if n != 1 or (e - vpos).EuclideanNorm() > mm(reach) or (e - vpos).EuclideanNorm() < mm(0.05):
            continue
        if any(t.GetClass() == "PCB_VIA" and t.GetNetname() == net and (t.GetPosition() - e).EuclideanNorm() < mm(0.1)
               for t in b.GetTracks()):
            continue
        seg = pcbnew.SHAPE_SEGMENT(vpos, e, mm(0.25))
        if collides(b, seg, layer, net):
            continue
        t = pcbnew.PCB_TRACK(b); t.SetStart(vpos); t.SetEnd(e); t.SetWidth(mm(0.25)); t.SetLayer(layer)
        t.SetNet(b.FindNet(net)); b.Add(t); joined += 1
    return joined


def main():
    b = pcbnew.LoadBoard(PCB)
    if not {"--final", "--gnd", "--legacy"} & set(sys.argv):
        sys.exit("usage: hand_fixes_revA.py --gnd | --final   (--legacy: the old post-route steps 1-3)")
    if "--final" in sys.argv:                            # after route.py: VBAT via links, FOD escape via
        j = join_dangling(b, "VBAT", (6.25, -4.95))
        fod = escape_via(b, "U2", "14", "FOD")
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(PCB)
        print(f"final: VBAT links {j}, FOD escape via {fod}")
        return
    if "--gnd" in sys.argv:                              # after route.py: only the GND escapes
        esc = gnd_escapes(b)
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(PCB)
        print(f"GND escapes: {esc}")
        return
    u2 = b.FindFootprintByReference("U2")
    pads = {p.GetName(): p for p in u2.Pads() if p.GetName().isdigit() and int(p.GetName()) <= 20}
    pin = {n: loc(p) for n, p in pads.items()}
    c5 = {p.GetName(): loc(p) for p in b.FindFootprintByReference("C5").Pads()}
    (x3, y3), (x4, y4), (x15, y15) = pin["3"], pin["4"], pin["15"]
    left_end = pad_box(pads["4"])[0]                    # outer end of the left pin row
    right_end = pad_box(pads["15"])[2]                  # outer end of the right pin row
    VIA_R, CLR = 0.225, 0.15

    # C8 (CLAMP2) 0.4 mm right, so a via fits straight out of pin 15; C7 (CLAMP1) 0.3 mm left, away from
    # the VBAT via. Their tracks (and FOD copper where C8 lands) are deleted and re-routed by route.py.
    n = move_part(b, "C8", 12.7, -3.9, {"CLAMP2", "AC2"})
    n += move_part(b, "C7", 4.6, -4.6, {"CLAMP1", "AC1"})
    c8box = pad_box(b.FindFootprintByReference("C8").Pads()[0])
    n += clear_box(b, c8box[0] - 1.6, c8box[1] - 0.6, c8box[2] + 0.6, c8box[3] + 0.6, {"FOD"})

    # clear the left gap and the pin-15 exit of the nets we rebuild
    n += clear_box(b, c5["2"][0] - 0.05, y3 - 0.5, x3, y4 + 0.3, {"VBAT", "BOOT1"})
    n += clear_box(b, x15, y15 - 0.3, x15 + 1.4, y15 + 0.3, {"COMM2"})

    # 1. VBAT via between the BOOT1 and CLAMP1 lanes, stub from pin 4
    vx = left_end - CLR - VIA_R - 0.025
    track(b, "VBAT", [(x4, y4), (vx, y4)])
    via(b, "VBAT", vx, y4)
    # 2. BOOT1 straight in at the pin's y
    cx, cy = c5["2"]
    track(b, "BOOT1", [(cx, cy), (cx + abs(cy - y3), y3), (x3, y3)])
    # 3. COMM2 out of pin 15 to a via
    cvx = right_end + CLR + VIA_R + 0.025
    track(b, "COMM2", [(x15, y15), (cvx, y15)])
    via(b, "COMM2", cvx, y15)

    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(PCB)
    print(f"hand fixes: C8 +0.4, C7 -0.3 mm, removed {n} old items; vias VBAT ({vx:.2f}, {y4:.2f}) COMM2 ({cvx:.2f}, {y15:.2f})")


if __name__ == "__main__":
    main()
