import math
f = lambda v: f"{v:.2f}"

# ---------- geometry (mm), same numbers as curb_drain.scad ----------
T, CW, CD, PITCH, WIDTH = 2.6, 1.0, 1.3, 2.0, 30.0
N = 13; X0 = (WIDTH - (N - 1) * PITCH) / 2
ALPHA = math.atan(0.5 / 1.3); RTIP = 0.15
CH = 1.4  # side chamfer

def poly(pts, cls, extra=""):
    return f'<polygon class="{cls}" points="{" ".join(f(x)+","+f(y) for x,y in pts)}" {extra}/>'
def line(x1,y1,x2,y2,cls="dim",extra=""):
    return f'<line class="{cls}" x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" {extra}/>'
def text(x,y,s,cls="lbl",anchor="start",extra=""):
    return f'<text class="{cls}" x="{f(x)}" y="{f(y)}" text-anchor="{anchor}" {extra}>{s}</text>'
def dimh(x1,x2,y,label,above=True):   # horizontal dimension with ticks
    o = [line(x1,y,x2,y,"dim"), line(x1,y-5,x1,y+5,"dim"), line(x2,y-5,x2,y+5,"dim")]
    o.append(text((x1+x2)/2, y-7 if above else y+16, label, "dimt","middle"))
    return "".join(o)
def dimv(x,y1,y2,label,side="right"):
    o = [line(x,y1,x,y2,"dim"), line(x-5,y1,x+5,y1,"dim"), line(x-5,y2,x+5,y2,"dim")]
    o.append(text(x+8 if side=="right" else x-8,(y1+y2)/2+4,label,"dimt","start" if side=="right" else "end"))
    return "".join(o)

def arm_profile(thick_at, x_from=0.0, x_to=WIDTH, grooves=True, comb=False, floor_off=0.0):
    """outline of the arm cross-section across the curb (x along curb, z up) as a polygon."""
    t = thick_at
    pts = [(x_from, floor_off), (x_from, floor_off + t - CH if x_from == 0 else floor_off + t)]
    if x_from == 0: pts.append((CH, floor_off + t))
    centers = [X0 + i * PITCH for i in range(N) if x_from < X0 + i * PITCH < x_to]
    for c in centers:
        if comb:
            pts += [(c - CW/2, floor_off + t), (c - CW/2, floor_off), (c + CW/2, floor_off), (c + CW/2, floor_off + t)]
        elif grooves:
            yb = floor_off + t - CD
            yc = yb + RTIP / math.sin(ALPHA)
            pts.append((c - CW/2, floor_off + t))
            # rounded V bottom
            a0, a1 = math.pi + ALPHA, 2 * math.pi - ALPHA
            tl = (c - (yc - RTIP*math.sin(ALPHA) - yb) * math.tan(ALPHA), 0)
            for k in range(9):
                a = (math.pi + ALPHA) + (math.pi - 2*ALPHA) * k / 8
                pts.append((c + RTIP * math.cos(a), yc + RTIP * math.sin(a)))
            pts.append((c + CW/2, floor_off + t))
    if x_to == WIDTH:
        pts += [(WIDTH - CH, floor_off + t), (WIDTH, floor_off + t - CH), (WIDTH, floor_off)]
    else:
        pts += [(x_to, floor_off + t), (x_to, floor_off)]
    if comb:  # comb slots split the polygon; return per-tooth polygons instead
        return None
    return pts

def comb_teeth(t):
    """C-C: teeth between slots that go through to the stone."""
    edges = [0.0]
    for i in range(N):
        c = X0 + i * PITCH; edges += [c - CW/2, c + CW/2]
    edges.append(WIDTH)
    teeth = []
    for a, b in zip(edges[0::2], edges[1::2]):
        pts = [(a, 0), (a, t), (b, t), (b, 0)]
        if a == 0: pts = [(0, 0), (0, t - CH + 0.0), (min(CH, b), t if CH <= b else t - CH + b), (b, t), (b, 0)]
        if b == WIDTH: pts = [(a, 0), (a, t), (WIDTH - CH, t), (WIDTH, t - CH), (WIDTH, 0)]
        teeth.append(pts)
    return teeth

def meniscus_liquid(state, theta=math.radians(45), w=CW, d=CD, R_recede=0.5):
    """liquid polygon inside one V-groove (x centred, y up from V tip region)."""
    bmax = math.pi/2 - ALPHA - theta
    yc_tip = RTIP / math.sin(ALPHA)
    def wall_x(y): return y * math.tan(ALPHA)
    if state == "full":
        yb, arc = d, None
    elif state == "sag":
        beta = bmax; R = (w/2) / math.sin(beta); yb = d; cy = d + R*math.cos(beta); arc = (R, cy, beta)
    else:
        beta = bmax; R = R_recede; b = R*math.sin(beta); yb = b / math.tan(ALPHA); cy = yb + R*math.cos(beta); arc = (R, cy, beta)
    pts = []
    # right wall up from the rounded tip to contact
    ytan = yc_tip - RTIP*math.sin(ALPHA)  # approx tangent height
    for k in range(9):
        a = (math.pi + ALPHA) + (math.pi - 2*ALPHA) * k / 8
        pts.append((RTIP*math.cos(a), yc_tip + RTIP*math.sin(a)))
    pts.append((wall_x(yb), yb))
    if arc is None:
        pts.append((-wall_x(yb), yb))
    else:
        R, cy, beta = arc
        for k in range(25):
            phi = -math.pi/2 + beta - 2*beta*k/24
            pts.append((R*math.cos(phi), cy + R*math.sin(phi)))
    pts.append((-wall_x(yb) if arc is None else -wall_x(yb), yb))
    return pts, arc

# ---------- panel builders ----------
def svg(vb_w, vb_h, body, label, minw):
    return f'<svg viewBox="0 0 {vb_w} {vb_h}" role="img" aria-label="{label}" style="min-width:{minw}px">{body}</svg>'

def panel_side():
    s = 3.3; ox, oy = 270, 230   # inner edge top
    P = lambda x, z: (ox + x*s, oy - z*s)
    b = []
    # floors
    b.append(poly([P(-45,-100),P(0,-100),P(0,-106),P(-45,-106)],"tile"))
    b.append(poly([P(152,-100),P(200,-100),P(200,-106),P(152,-106)],"tile"))
    b.append(text(*P(-43,-96),"shower floor","lbl small"))
    b.append(text(*P(198,-96),"bathroom floor","lbl small","end"))
    # curb
    b.append(poly([P(0,0),P(152,0),P(152,-100),P(0,-100)],"stone"))
    b.append(text(*P(110,-60),"granite curb","lbl on-stone","middle"))
    # fixed glass panel + silicone bead
    gx = 76
    bead = [P(gx,9)] + [P(gx - 6*(1 - math.cos(math.pi/2*k/12)), 9*(1 - math.sin(math.pi/2*k/12))) for k in range(13)] + [P(gx,0)]
    b.append(poly(bead,"bead"))
    b.append(poly([P(gx,0),P(gx+10,0),P(gx+10,62),P(gx,62)],"glass"))
    b.append(text(*P(gx+14,48),"fixed glass panel","lbl"))
    b.append(text(*P(gx+14,40),"water runs down it","lbl small muted"))
    # water running down the glass
    for k,(dx,dz) in enumerate(((gx-1.2,16),(gx-1.2,30))):
        cx, cy = P(dx,dz); b.append(f'<path class="drop" d="M{f(cx)},{f(cy-7)} q4,6 0,9 q-4,-3 0,-9z"/>')
    # puddle
    pud = [P(6,0)]
    for k in range(11):
        a = math.pi/2 * k/10
        pud.append(P(6 + 4 - 4*math.cos(a), 3*math.sin(a)))
    pud += [P(gx-6.5,3), P(gx-6.5,0)]
    b.append(poly(pud,"water"))
    # clip: arm, arc, leg
    re = 3; arm_top, arm_bot = T, 0
    pts = []
    pts.append(P(66, 1.0)); pts.append(P(54, T))
    for k in range(13):
        a = math.pi/2 * k/12
        pts.append(P(re - (re+T)*math.sin(a), -re + (re+T)*math.cos(a)))
    pts += [P(-T,-28), P(-T,-40), P(0,-40)]
    for k in range(13):
        a = math.pi/2 * (12-k)/12
        pts.append(P(re - re*math.sin(a), -re + re*math.cos(a)))
    pts.append(P(66,0))
    b.append(poly(pts,"nylon"))
    # drips from tip
    for k,z in enumerate((-46,-58)):
        cx, cy = P(-1.3,z); b.append(f'<path class="drop" d="M{f(cx)},{f(cy-8)} q5,7 0,10 q-5,-3 0,-10z"/>')
    # tape on leg
    b.append(poly([P(0,-10),P(0.9,-10),P(0.9,-30),P(0,-30)],"tape"))
    # dimensions
    b.append(dimh(P(0,0)[0], P(gx,0)[0], P(0,24)[1], "3 in (76 mm) to the glass"))
    b.append(dimh(P(0,0)[0], P(66,0)[0], P(0,12)[1], "arm 66 mm"))
    b.append(dimh(P(66,0)[0], P(gx,0)[0], P(0,12)[1], "10"))
    b.append(dimv(P(-9,0)[0], P(0,0)[1], P(0,-40)[1], "40 mm","left"))
    b.append(dimh(P(0,0)[0], P(152,0)[0], P(0,-112)[1], "6 in (152 mm) curb", above=False))
    # callouts
    def call(x,z,tx,tz,s1,s2=None,anchor="start"):
        a = P(x,z); t = P(tx,tz)
        o = line(a[0],a[1],t[0],t[1],"lead") + f'<circle class="leaddot" cx="{f(a[0])}" cy="{f(a[1])}" r="2.5"/>'
        o += text(t[0]+(4 if anchor=="start" else -4), t[1]+4, s1, "lbl", anchor)
        if s2: o += text(t[0]+(4 if anchor=="start" else -4), t[1]+19, s2, "lbl small muted", anchor)
        return o
    b.append(call(35,2.0,38,-22,"puddle, about 3 mm deep","held flat by surface tension"))
    b.append(call(63,0.8,58,-48,"comb inlet (section C)","slots open to the stone"))
    b.append(call(gx-2,2.5,gx+14,22,"silicone bead","clip stops just short of it"))
    b.append(call(25,1.5,22,-78,"grooved arm (section A)","rests directly on the granite"))
    b.append(call(0.5,-14,-38,-4,"tape on the leg only","never under the arm","end"))
    b.append(call(-1.3,-40,-38,-62,"drip tip (section D)","drops fall onto the tile","end"))
    # section cut marks
    for xm, lab in ((25,"A"),(62,"C")):
        x1, y1 = P(xm, 7); x2, y2 = P(xm,-5)
        b.append(line(x1,y1,x2,y2,"cut")); b.append(text(x1, y1-4, lab, "cutl","middle"))
    W, H = 950, 630
    return svg(W, H, "".join(b), "Side section of the shower curb with the drain clip", 640)

def panel_arm():
    s, ox, oy = 22, 70, 150
    P = lambda x, z: (ox + x*s, oy - z*s)
    b = [poly([P(-1,0),P(31,0),P(31,-2.2),P(-1,-2.2)],"stone")]
    # water in grooves (wetted, full)
    for i in range(N):
        c = X0 + i*PITCH; yb = T - CD
        liq, _ = meniscus_liquid("full")
        b.append(poly([P(c + x, yb + y) for x, y in liq], "water"))
    b.append(poly([P(x,z) for x,z in arm_profile(T)], "nylon"))
    # water levels
    for z, lab in ((3.0,"puddle starts 3.0 mm deep"),(1.6,"thins to about 1.6 mm")):
        b.append(line(*P(-1,z),*P(31,z),"lvl")); b.append(text(P(31,z)[0]+8,P(31,z)[1]+5,lab,"lbl small"))
    b.append(dimv(P(0,0)[0]-14,P(0,T)[1],P(0,0)[1],"2.6","left"))
    b.append(dimh(P(0,0)[0],P(30,0)[0],P(0,-2.2)[1]+4,"30 mm wide · 13 grooves, 1.0 mm wide at 2.0 mm pitch · 1.0 mm ridges",above=False))
    b.append(text(*P(15,-1.2),"granite","lbl on-stone","middle"))
    return svg(1000, 250, "".join(b), "Section A, the grooved arm", 640)

def panel_groove():
    s = 150; b = []
    states = (("full","Filled","p ≈ 0 Pa","flat meniscus, groove full"),
              ("sag","Pinned at the ridges","−58 Pa suction","meniscus sags until it meets the wall at θ"),
              ("recede","Receded into the V","−144 Pa suction","stronger pull, less water, slower flow"))
    for k,(st,title,pr,sub) in enumerate(states):
        ox, oy = 125 + k*270, 270
        P = lambda x, y: (ox + x*s, oy - y*s)
        # solid around groove
        wall = [P(-0.72,-0.12),P(-0.72,CD),P(-0.5,CD)]
        yc = RTIP/math.sin(ALPHA)
        for j in range(13):
            a = (math.pi + ALPHA) + (math.pi - 2*ALPHA) * j/12
            wall.append(P(RTIP*math.cos(a), yc + RTIP*math.sin(a)))
        wall += [P(0.5,CD),P(0.72,CD),P(0.72,-0.12)]
        liq, arc = meniscus_liquid(st)
        b.append(poly([P(x,y) for x,y in liq],"water"))
        b.append(poly(wall,"nylon"))
        b.append(text(ox, 30, title, "h3t","middle"))
        b.append(text(ox, 52, pr, "dimt strong","middle"))
        b.append(text(ox, 318, sub, "lbl small muted","middle"))
        if st == "full":
            # alpha annotation
            cx, cy = P(0, 0.05)
            b.append(line(cx, cy, cx, P(0,CD+0.15)[1], "lead dash"))
            b.append(text(P(0.06,0.55)[0], P(0.06,0.55)[1], "α = 21°", "dimt strong"))
        if st == "sag":
            R, cy, beta = arc
            cpt = P(0.5, CD)
            b.append(text(cpt[0]-2, cpt[1]+22, "θ", "dimt strong","end"))
    return svg(790, 335, "".join(b), "Section B, one groove and its three water states", 600)

def panel_comb():
    s, ox, oy = 48, 60, 150
    P = lambda x, z: (ox + x*s, oy - z*s)
    t = T - (T - 1.0) * (62 - 54) / 12
    b = [f'<clipPath id="cclip"><rect x="{ox-48}" y="0" width="{f(10.5*s+48)}" height="300"/></clipPath><g clip-path="url(#cclip)">']
    b.append(poly([P(-1,0),P(31,0),P(31,-1.6),P(-1,-1.6)],"stone"))
    b.append(poly([P(-1,0),P(31,0),P(31,0.6),P(-1,0.6)],"water"))
    for pts in comb_teeth(t):
        b.append(poly([P(x,z) for x,z in pts],"nylon"))
    b.append(line(*P(-1,0.6),*P(31,0.6),"lvl")); b.append("</g>")
    b.append(text(P(0,0)[0],P(0,t)[1]-44,"a 0.6 mm film still reaches the slots","lbl small"))
    b.append(dimv(P(0,0)[0]-16,P(0,t)[1],P(0,0)[1],f"{t:.1f}","left"))
    b.append(dimh(P(X0-CW/2,0)[0],P(X0+CW/2,0)[0],P(0,t)[1]-14,"1.0 slot"))
    b.append(text(*P(5,-1.0),"granite","lbl on-stone","middle"))
    b.append(text(P(10.5,0)[0]-2,P(0,-1.6)[1]+18,"first 10 mm of the 30 mm width shown","lbl small muted","end"))
    return svg(580, 250, "".join(b), "Section C, the comb inlet", 360)

def panel_mount():
    s = 34; b = []
    for k,(lift,title,verdict,cls) in enumerate(((0.0,"Arm on the stone","grooves reach the water","ok"),
                                                (1.0,"1 mm tape under the arm","grooves sit above the water: stalls","bad"))):
        ox, oy = 90 + k*450, 210
        P = lambda x, z: (ox + (x-1.6)*s, oy - z*s)
        b.append(poly([P(1.6,0),P(9.4,0),P(9.4,-1.6),P(1.6,-1.6)],"stone"))
        b.append(poly([P(1.6,0),P(9.4,0),P(9.4,1.6),P(1.6,1.6)],"water"))
        if lift: b.append(poly([P(2.2,0),P(8.8,0),P(8.8,lift),P(2.2,lift)],"tape"))
        pts = arm_profile(T, x_from=2.2, x_to=8.8, floor_off=lift)
        b.append(poly([P(x,z) for x,z in pts],"nylon"))
        for i in range(N):
            c = X0 + i*PITCH
            if 2.2 < c < 8.8 and not lift:
                liq,_ = meniscus_liquid("full")
                b.append(poly([P(c+x, lift + T - CD + y) for x,y in liq],"water"))
        b.append(line(*P(1.6,1.6),*P(9.4,1.6),"lvl"))
        b.append(text(P(9.4,1.6)[0]+6,P(9.4,1.6)[1]+5,"water 1.6","dimt"))
        fl = lift + T - CD
        b.append(line(*P(1.6,fl),*P(9.4,fl),"lvl2"))
        b.append(text(P(9.4,fl)[0]+6,P(9.4,fl)[1]+(18 if fl < 1.6 else 5),f"groove floor {fl:.1f}","dimt"))
        b.append(text(ox+133, 28, title, "h3t","middle"))
        b.append(text(ox+133, 50, verdict, f"verdict {cls}","middle"))
    return svg(900, 290, "".join(b), "Mounting comparison", 600)

def panel_wick():
    s, ox, oy = 22, 70, 120
    P = lambda x, z: (ox + x*s, oy - z*s)
    gw, gd = 13.0, 1.2; g0 = (WIDTH - gw)/2
    b = [poly([P(-1,0),P(31,0),P(31,-2.2),P(-1,-2.2)],"stone")]
    outline = [P(0,0),P(0,T-CH),P(CH,T),P(g0,T),P(g0,T-gd),P(g0+gw,T-gd),P(g0+gw,T),P(WIDTH-CH,T),P(WIDTH,T-CH),P(WIDTH,0)]
    b.append(poly(outline,"nylon"))
    b.append(poly([P(g0+0.5,T-gd),P(g0+gw-0.5,T-gd),P(g0+gw-0.5,T-0.05),P(g0+0.5,T-0.05)],"fabric"))
    b.append(dimh(P(g0,0)[0],P(g0+gw,0)[0],P(0,T)[1]-14,"13 mm groove, 1.2 deep"))
    b.append(text(*P(15,-1.2),"granite","lbl on-stone","middle"))
    b.append(text(P(31,0)[0]+6, P(0,1.8)[1], "microfiber strip, 12 mm", "lbl small"))
    b.append(text(P(31,0)[0]+6, P(0,1.8)[1]+16, "let 10–15 mm lie on the stone", "lbl small muted"))
    b.append(text(P(31,0)[0]+6, P(0,1.8)[1]+31, "past the end of the arm", "lbl small muted"))
    return svg(1000, 200, "".join(b), "Section A, cloth version", 640)

def panel_tip():
    s, ox, oy = 7, 40, 40
    P = lambda x, z: (ox + x*s, oy - z*s)   # x along curb, z down the leg (0 = top of leg)
    b = [poly([P(0,-3),P(30,-3),P(30,-28),P(15,-40),P(0,-28)],"nylon")]
    for i in range(N):
        c = X0 + i*PITCH
        zend = -28 - 12 * (1 - abs(c-15)/15)
        b.append(line(*P(c,-3.5),*P(c,zend+0.6),"grooveline"))
    cx, cy = P(15,-40)
    b.append(f'<path class="drop" d="M{f(cx)},{f(cy+6)} q7,9 0,13 q-7,-4 0,-13z"/>')
    b.append(text(P(30,0)[0]+14, P(0,-10)[1], "grooves run straight down", "lbl small"))
    b.append(text(P(30,0)[0]+14, P(0,-30)[1], "V tip gathers them", "lbl small"))
    b.append(text(P(30,0)[0]+14, P(0,-30)[1]+15, "into one drip point", "lbl small muted"))
    b.append(dimh(P(0,0)[0],P(30,0)[0],P(0,-3)[1]-10,"30 mm"))
    b.append(dimv(P(0,0)[0]-12,P(0,-28)[1],P(0,-40)[1],"12 mm V","left"))
    return svg(520, 360, "".join(b), "Section D, the drip tip seen from the shower", 360)

html = open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "template.html")).read()
for k, v in dict(SIDE=panel_side(), ARM=panel_arm(), GROOVE=panel_groove(), COMB=panel_comb(),
                 MOUNT=panel_mount(), WICK=panel_wick(), TIP=panel_tip()).items():
    html = html.replace("{{"+k+"}}", v)
open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "curb-drain-sections.html"),"w").write(html)
print(len(html))
