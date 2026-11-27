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
    b.append(poly([P(-45,-63.5),P(12.7,-63.5),P(12.7,-69.5),P(-45,-69.5)],"tile"))
    b.append(poly([P(152,-63.5),P(200,-63.5),P(200,-69.5),P(152,-69.5)],"tile"))
    b.append(text(*P(-43,-59.5),"shower floor","lbl small"))
    b.append(text(*P(198,-59.5),"bathroom floor","lbl small","end"))
    # curb
    b.append(poly([P(12.7,-19),P(152,-19),P(152,-63.5),P(12.7,-63.5)],"stone"))
    b.append(poly([P(0,0),P(152,0),P(152,-19),P(0,-19)],"stone"))
    b.append(line(*P(0,-19),*P(152,-19),"slabline"))
    b.append(text(*P(130,-12),"¾ in slab","lbl on-stone","middle"))
    b.append(text(*P(130,-45),"curb","lbl on-stone","middle"))
    # fixed glass panel + silicone bead
    gx = 66.7
    bead = [P(gx,6)] + [P(gx - 4.8*(1 - math.cos(math.pi/2*k/12)), 6*(1 - math.sin(math.pi/2*k/12))) for k in range(13)] + [P(gx,0)]
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
    pud += [P(gx-5.3,3), P(gx-5.3,0)]
    b.append(poly(pud,"water"))
    # clip: arm, arc, leg
    re = 3; arm_top, arm_bot = T, 0
    pts = []
    pts.append(P(59, 1.0)); pts.append(P(47, T))
    for k in range(13):
        a = math.pi/2 * k/12
        pts.append(P(re - (re+T)*math.sin(a), -re + (re+T)*math.cos(a)))
    pts += [P(-T,-32), P(0,-32)]
    for k in range(13):
        a = math.pi/2 * (12-k)/12
        pts.append(P(re - re*math.sin(a), -re + re*math.cos(a)))
    pts.append(P(59,0))
    b.append(poly(pts,"nylon"))
    # drips from tip
    for k,z in enumerate((-38,-49)):
        cx, cy = P(-1.3,z); b.append(f'<path class="drop" d="M{f(cx)},{f(cy-8)} q5,7 0,10 q-5,-3 0,-10z"/>')
    # tape on leg
    b.append(poly([P(0,-6),P(0.9,-6),P(0.9,-17),P(0,-17)],"tape"))
    # dimensions
    b.append(dimh(P(0,0)[0], P(gx,0)[0], P(0,24)[1], "2⅝ in (67 mm) to the glass"))
    b.append(dimh(P(0,0)[0], P(59,0)[0], P(0,12)[1], "arm 59 mm"))
    b.append(dimh(P(59,0)[0], P(gx,0)[0], P(0,12)[1], ""))
    b.append(text(P(59,0)[0]-0, P(0,12)[1]-7, "7.7 ", "dimt", "end"))
    b.append(dimv(P(-9,0)[0], P(0,0)[1], P(0,-32)[1], "32 mm","left"))
    b.append(dimv(P(160,0)[0], P(0,-19)[1], P(0,-63.5)[1], "1¾ in"))
    b.append(dimv(P(160,0)[0], P(0,0)[1], P(0,-19)[1], "¾ in"))
    b.append(dimh(P(0,0)[0], P(152,0)[0], P(0,-75.5)[1], "curb (width not to scale)", above=False))
    # callouts
    def call(x,z,tx,tz,s1,s2=None,anchor="start"):
        a = P(x,z); t = P(tx,tz)
        o = line(a[0],a[1],t[0],t[1],"lead") + f'<circle class="leaddot" cx="{f(a[0])}" cy="{f(a[1])}" r="2.5"/>'
        o += text(t[0]+(4 if anchor=="start" else -4), t[1]+4, s1, "lbl", anchor)
        if s2: o += text(t[0]+(4 if anchor=="start" else -4), t[1]+19, s2, "lbl small muted", anchor)
        return o
    b.append(call(35,2.0,40,-6,"puddle, about 3 mm deep","held flat by surface tension"))
    b.append(call(56,0.8,72,-30,"comb inlet (section C)","slots open to the stone"))
    b.append(call(6,-19,-38,-26,"½ in overhang","drops fall clear","end"))
    b.append(call(gx-2,2.5,gx+14,22,"3/16 in silicone bead","2.9 mm gap to the clip"))
    b.append(call(25,1.5,30,-48,"grooved arm (section A)","rests directly on the granite"))
    b.append(call(0.5,-11,-38,-6,"tape on the leg only","never under the arm","end"))
    b.append(call(-1.3,-32,-38,-48,"drip edge (section D)","drips every 23 mm","end"))
    # section cut marks
    for xm, lab in ((25,"A"),(55,"C")):
        x1, y1 = P(xm, 7); x2, y2 = P(xm,-5)
        b.append(line(x1,y1,x2,y2,"cut")); b.append(text(x1, y1-4, lab, "cutl","middle"))
    W, H = 950, 520
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
    t = T - (T - 1.0) * (55 - 47) / 12
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
    return svg(1000, 290, "".join(b), "Mounting comparison", 640)

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

RUN_L, RUN_N = 304.8, 3          # final design: 3 ft run in three sections (cad/curb_run.py)
TOOTH_P = RUN_L / round(RUN_L / 24.0)
TAB_LEN, TAB_ROOT, TAB_TIP, CLR_SIDE, CLR_END = 6.0, 14.0, 20.0, 0.3, 0.5
PAD, RE = 59.0, 3.0
TAB_YC = (RE + PAD - 12.0) / 2

def run_centers(left_outer):
    first = (2.6 if left_outer else 1.5) + CW / 2
    out, c = [], first
    while c <= RUN_L - 1.5 - CW / 2 + 1e-9:
        out.append(c); c += PITCH
    return out

def panel_tip():
    s, ox, oy = 6.0, 60, 50
    span = 3 * TOOTH_P
    P = lambda x, z: (ox + x*s, oy - z*s)        # x along curb, z down the leg (0 = curb top)
    outline = [P(0,-3)] + [P(span,-3)]
    saw = []
    for k in range(3, -1, -1):
        saw.append(P(k*TOOTH_P, -22))
        if k:   # rounded tip, 1.5 mm radius
            cx, r = (k-0.5)*TOOTH_P, 1.5
            phi = math.atan((TOOTH_P/2)/10); zc = -32 + r/math.sin(phi)
            for j in range(9):
                th = -phi - (math.pi - 2*phi) * j / 8
                saw.append(P(cx + r*math.cos(th), zc + r*math.sin(th)))
    b = [poly(outline + saw, "nylon")]
    for c in [1.0 + 2.0*i for i in range(int(span/2))]:
        ph = (c % TOOTH_P) / TOOTH_P
        zend = -22 - 10 * (1 - abs(ph - 0.5) * 2)
        b.append(line(*P(c,-3.6),*P(c,zend+0.7),"grooveline"))
    for k in range(3):
        cx, cy = P((k+0.5)*TOOTH_P, -32)
        b.append(f'<path class="drop" d="M{f(cx)},{f(cy+6)} q6,8 0,12 q-6,-4 0,-12z"/>')
    b.append(dimh(P(0,0)[0],P(TOOTH_P,0)[0],P(0,-3)[1]-10,f"{TOOTH_P:.1f} mm"))
    b.append(dimv(P(0,0)[0]-12,P(0,-22)[1],P(0,-32)[1],"10 mm","left"))
    b.append(text(P(span,0)[0]+14, P(0,-12)[1], "grooves run straight down", "lbl small"))
    b.append(text(P(span,0)[0]+14, P(0,-34)[1], "each tooth gathers", "lbl small"))
    b.append(text(P(span,0)[0]+14, P(0,-34)[1]+15, "its grooves into one drip", "lbl small muted"))
    b.append(text(P(span,0)[0]+14, P(0,-34)[1]+33, "tips rounded to 1.5 mm", "lbl small"))
    b.append(text(P(span,0)[0]+14, P(0,-34)[1]+48, "so they're smooth underfoot", "lbl small muted"))
    return svg(720, 330, "".join(b), "Section D, the sawtooth drip edge seen from the shower", 520)

def panel_joint():
    s, ox, oy = 7.0, 90, 520
    P = lambda x, y: (ox + (x - (RUN_L - 24))*s, oy - y*s)   # plan view: x along curb, y across it
    x0, x1 = RUN_L - 24, RUN_L + 24
    b = [f'<clipPath id="jclip"><rect x="{f(P(x0,0)[0])}" y="0" width="{f(48*s)}" height="{oy + 40}"/></clipPath><g clip-path="url(#jclip)">']
    def half(xa, xb, cls, centers):
        b.append(poly([P(xa,-2.6),P(xb,-2.6),P(xb,PAD),P(xa,PAD)], cls))
        for c in centers:
            if xa < c < xb:
                b.append(poly([P(c-CW/2,PAD-8),P(c+CW/2,PAD-8),P(c+CW/2,PAD+0.5),P(c-CW/2,PAD+0.5)],"slot"))
                b.append(line(*P(c,0.5),*P(c,PAD-8.3),"grooveplan"))
    half(x0, RUN_L, "nylon", run_centers(True))
    half(RUN_L, x1, "nylon2", [RUN_L + c for c in run_centers(False)])
    # socket (gap) in the second section, then the tab of the first
    d = TAB_LEN + CLR_END; k = (TAB_TIP - TAB_ROOT) / TAB_LEN / 2
    wr, wt = TAB_ROOT/2 + CLR_SIDE, TAB_TIP/2 + CLR_SIDE + k*CLR_END
    b.append(poly([P(RUN_L, TAB_YC-wr), P(RUN_L+d, TAB_YC-wt), P(RUN_L+d, TAB_YC+wt), P(RUN_L, TAB_YC+wr)], "gap"))
    b.append(poly([P(RUN_L, TAB_YC-TAB_ROOT/2), P(RUN_L+TAB_LEN, TAB_YC-TAB_TIP/2), P(RUN_L+TAB_LEN, TAB_YC+TAB_TIP/2), P(RUN_L, TAB_YC+TAB_ROOT/2)], "nylon"))
    b.append("</g>")
    b.append(line(*P(RUN_L,-6),*P(RUN_L,PAD+3),"cut"))
    b.append(text(P(RUN_L,0)[0]-6, P(0,PAD+4)[1], "start", "lbl small", "end"))
    b.append(text(P(RUN_L,0)[0]+6, P(0,PAD+4)[1], "middle", "lbl small"))
    b.append(line(*P(RUN_L+TAB_LEN,-2.6),*P(RUN_L+TAB_LEN,-8),"dim"))
    b.append(dimh(P(RUN_L,0)[0], P(RUN_L+TAB_LEN,0)[0], P(0,-7)[1], "6 mm tab", above=False))
    b.append(dimv(P(x1,0)[0]+14, P(0,TAB_YC+TAB_TIP/2)[1], P(0,TAB_YC-TAB_TIP/2)[1], "20 tip"))
    b.append(line(*P(RUN_L-0.3, TAB_YC+TAB_ROOT/2), P(x0,0)[0]-6, P(0,TAB_YC+TAB_ROOT/2+12)[1], "lead"))
    b.append(text(P(x0,0)[0]-10, P(0,TAB_YC+TAB_ROOT/2+12)[1]+4, "14 mm root", "dimt", "end"))
    b.append(line(*P(RUN_L+TAB_LEN+0.3, TAB_YC+TAB_TIP/2-1), P(x1,0)[0]+6, P(0,TAB_YC+TAB_TIP/2+9)[1], "lead"))
    b.append(text(P(x1,0)[0]+8, P(0,TAB_YC+TAB_TIP/2+9)[1]-4, "0.3 mm sides", "dimt"))
    b.append(text(P(x1,0)[0]+8, P(0,TAB_YC+TAB_TIP/2+9)[1]+12, "0.5 mm end", "dimt"))
    b.append(text(P(x0,0)[0]-8, P(0,PAD-4)[1], "comb", "lbl small muted", "end"))
    b.append(text(P(x0,0)[0]-8, P(0,12)[1], "grooves", "lbl small muted", "end"))
    b.append(text(P(x0,0)[0]-8, P(0,1)[1], "edge", "lbl small muted", "end"))
    return svg(600, 610, "".join(b), "Section E, plan view of a joint", 400)

def panel_overview():
    s = 0.86; ox, oy = 60, 60
    P = lambda x, y: (ox + x*s, oy + y*s)      # top view: x along curb, y from shower edge (top) toward bathroom
    total = RUN_L * RUN_N
    b = [poly([P(0,0),P(total,0),P(total,152),P(0,152)],"stone")]
    b.append(poly([P(0,66.7),P(total,66.7),P(total,76.7),P(0,76.7)],"glass"))
    b.append(poly([P(0,61.9),P(total,61.9),P(total,66.7),P(0,66.7)],"bead"))
    b.append(poly([P(0,6),P(total,6),P(total,62),P(0,62)],"water", 'style="opacity:.55"'))
    for k in range(RUN_N):
        xa = k * RUN_L
        b.append(poly([P(xa,-2.6),P(xa+RUN_L,-2.6),P(xa+RUN_L,PAD),P(xa,PAD)], "nylon" if k % 2 == 0 else "nylon2"))
        b.append(poly([P(xa,PAD-8),P(xa+RUN_L,PAD-8),P(xa+RUN_L,PAD),P(xa,PAD)], "combband"))
        if k < RUN_N - 1:
            xr = xa + RUN_L
            b.append(poly([P(xr,TAB_YC-TAB_ROOT/2),P(xr+TAB_LEN,TAB_YC-TAB_TIP/2),P(xr+TAB_LEN,TAB_YC+TAB_TIP/2),P(xr,TAB_YC+TAB_ROOT/2)], "nylon" if k % 2 == 0 else "nylon2"))
        name = ("start", "middle", "end")[k] if RUN_N == 3 else f"section {k+1}"
        b.append(text(P(xa + RUN_L/2, 0)[0], P(0, 36)[1] + 5, name, "lbl inv", "middle"))
        b.append(dimh(P(xa,0)[0], P(xa+RUN_L,0)[0], P(0,-2.6)[1]-12, f"{RUN_L:.1f} mm"))
    b.append(dimh(P(0,0)[0], P(total,0)[0], P(0,152)[1]+22, f"{total:.0f} mm (3 ft) curb run", above=False))
    b.append(text(P(0,0)[0]-8, P(0,4)[1], "shower", "lbl small", "end"))
    b.append(text(P(0,0)[0]-8, P(0,4)[1]+15, "side", "lbl small muted", "end"))
    b.append(text(P(total,0)[0]+8, P(0,71.7)[1]+5, "glass", "lbl small"))
    b.append(text(P(total,0)[0]+8, P(0,120)[1]+5, "bathroom", "lbl small"))
    b.append(text(P(total,0)[0]+8, P(0,135)[1]+5, "side", "lbl small muted"))
    return svg(960, 250, "".join(b), "Plan view of the whole 3 ft run on the curb", 640)

html = open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "template.html")).read()
for k, v in dict(SIDE=panel_side(), ARM=panel_arm(), GROOVE=panel_groove(), COMB=panel_comb(),
                 MOUNT=panel_mount(), TIP=panel_tip(), JOINT=panel_joint(), OVERVIEW=panel_overview()).items():
    html = html.replace("{{"+k+"}}", v)
open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "curb-drain-sections.html"),"w").write(html)
print(len(html))
