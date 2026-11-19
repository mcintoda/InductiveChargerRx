# Enclosure: off-the-shelf survey and custom O-ring design (rev A)

Requirements carried over from the design: fully sealed (IP68, bath depth plus warm-water cycling),
**no epoxy or potting** (serviceable), body-safe outer surfaces, a **flat thin front wall** pressed
onto the electrodes, a **flat back** within about 5 mm of a Qi pad, and as small as possible.

---

## 1. Off-the-shelf boxes: what's available

| Box | Outside (mm) | Verdict |
|---|---|---|
| Hammond 1555C2GY (PC, IP68) | 120 × 65 × 40.5 | **Fits the 112 mm PCB**, but has about 3.5× the volume of the custom design. The lid has molded standoffs and corner screw bosses, so the PCB can't lie flat on a wall. An air gap of ~1 mm costs most of the electrode signal (each 0.1 mm of air costs about 20 %), so the lid features would need to be ground off. Opaque grey (a clear-lid 1554 variant exists) |
| Hammond 1551 miniature (PC, IP68) | 60 × 35 × 22 / 80 × 40 × 22 | Too short for the 60 mm electrode ladder |
| Takachi WP (ABS/ASA, IP67) | smallest found 100 × 100 × 25 | Wrong shape, and IP67 (temporary immersion) |
| Takachi WH handheld (IP67) | 88 × 146 × 20 and up | Thin, but wide, IP67, and has a battery door (an extra seal) |
| Polycase / Bopla IP68 ranges | larger outdoor boxes | No slim (< 20 mm) IP68 part found |

**Conclusion:** no off-the-shelf IP68 box is thin and flat enough. If you want a quick first
prototype anyway, use the **Hammond 1555C2GY**: grind the lid standoffs flat, mount the PCB
electrode-side-down on the lid with thin double-sided tape, and put the coil on the base. Sensing and
charging will work, but the device will be bulky. The custom design below is recommended.

Sources: [Hammond 1555 datasheet](https://www.mouser.com/datasheet/2/177/1555-1289236.pdf),
[Hammond 1555C drawing](https://www.hammfg.com/files/parts/pdf/1555CGY.pdf),
[RS 1555C2GY listing](https://uk.rs-online.com/web/p/general-purpose-enclosures/2291128),
[Hammond 1551WHFLBK](https://www.buerklin.com/en/p/hammond/general-purpose-enclosures/1551whflbk/66H432/?view=GRID),
[Takachi WP (RS)](https://nz.rs-online.com/web/p/general-purpose-enclosures/1325359),
[Takachi WH (RS)](https://uk.rs-online.com/web/p/hand-held-enclosures/1325366),
[Takachi WH catalogue](https://www.takachi-enclosure.com/assets/attachments/images/takachi_plastic_handheld_enclosures_2021.pdf),
[Polycase IP68](https://polycase.com/ip68-enclosures).

---

## 2. Custom enclosure: cup + radial O-ring plug (no epoxy)

![Parts](img/enclosure_parts.png)

**Outside size: 43.8 × 118.0 × 11.5 mm** (internal cavity 39.4 × 113.6 × 8.8 mm). Three printed parts:

| Part | What it does |
|---|---|
| **Cup** | One piece: 1.2 mm flat front wall (the sensing face), 2.2 mm side walls, open back. A 0.8 mm thermal window sits behind the TMP117 tab. The bore entry has a 0.6 mm lead-in chamfer so it doesn't cut the O-ring |
| **Plug** | 1.5 mm flat back wall (Qi face) with a 2.2 mm skirt carrying the O-ring groove. Two posts press the PCB onto the front wall in the electronics band, and a pry notch at the top edge allows opening |
| **Bracket** | Stays stuck to the tub with 2 suction cups. The device slides in from the top and rests on two corner stops. Side lips overlap only the outer 3 mm of the front face, so the electrodes and the thermal window stay fully exposed. Lift the device out to charge |

### 2.1 How it seals

![Section through the gland](img/enclosure_gland.png)

- **Radial (piston) O-ring seal.** The O-ring sits in a groove around the plug's skirt and is squeezed
  between the groove bottom and the cup's bore. Squeeze is set by the geometry, not by screw torque,
  so there is no flange, no gasket to crush evenly, and no glue.
- **Retention:** 4 × M2 × 4 mm A4-stainless self-tapping screws (for plastics) go through the side walls into the plug,
  on the **outside of the O-ring** (axis at Z 9.6 mm, groove at Z 5.9–8.2). Water can enter a
  screw hole but stops at the O-ring. The screws only stop the plug backing out, for example when warm water
  heats the trapped air: +30 °C gives about 10 kPa, which is about 50 N on the plug.
- **Internal clamping:** PCB 1.0, battery 6.0, coil 1.2 and 1.0 mm PORON foam (compressed to 0.6) fill
  the 8.8 mm cavity exactly. Closing the plug presses the electrodes flat on the front wall, which matters
  because each 0.1 mm of air gap costs about 20 % of the signal.

| Gland parameter (static radial, CS 1.5 mm) | Value |
|---|---|
| O-ring | **88 × 1.5 mm EPDM 70 Sh A** (hot water, soap and bath oils. Silicone also works but is less tear-resistant) |
| Installed stretch on the groove bottom | 4.3 % (groove perimeter 288.5 mm) |
| Groove depth / width | 1.05 / 2.30 mm |
| Radial clearance, plug ↔ bore | 0.10 mm |
| Squeeze | **22 % nominal**, 15–28 % with the plug pushed fully to one side |
| Groove fill | 64 % |
| Groove corner radius | 4.9 mm (≥ 3 × CS) |

These follow standard static-radial guidance (roughly 18–25 % squeeze, ≤ 85 % fill; see
[Marco Rubber](https://www.marcorubber.com/downloads/Marco-O-Ring-Gland-General-Design-Considerations.pdf),
[ERIKS](https://o-ring.info/en/technical%20manual/eriks%20-%20technical%20manual%20-%20o-ring%20gland%20design%20information.pdf),
[eFunda](https://www.efunda.com/DesignStandards/oring/design_guidelines.cfm)).

### 2.2 Fit check

![Sections](img/enclosure_section.png)

`hardware/mech/fit_and_render.py` places the PCB (with the 5.5 mm top-corner radius now in the
placement-study board), the ESP32 module, the 603450 cell, the Qi coil and the foam at their real positions,
and intersects them with the cup and plug. **Interference is 0.000 mm³ for every pair.** The PCB front face
sits exactly on the front-wall inner face.

### 2.3 Printing at JLC3DP

| Option | Use | Notes |
|---|---|---|
| **SLA resin** (e.g. Ledo 6060, 8228) | **First prototypes** | Solid resin parts are watertight, and the bore and groove come out smooth enough for an O-ring. JLC itself says resin is not for outdoor or hot use. Bath water at ≤ 45 °C is fine for testing. Resin is **not certified for long skin contact**, so treat these as test units |
| **MJF PP** (polypropylene, if offered) | Better prototypes / small runs | Body-safe, hydrophobic (helps reject water films, see the electrode study), resistant to soap and oil. Slightly porous and rough, so lightly sand the bore and use a thin film of silicone O-ring grease |
| MJF PA12 nylon | Not recommended | Absorbs water and is porous at a 1.2 mm wall |
| **Injection-molded PP** | Production | Same geometry. Add 0.5–1° draft on the cup walls |

SLA/MJF tolerances (about ±0.1–0.2 mm) are the main risk for the seal. `PLUG_CLR` and `GLAND_DEPTH` in
`enclosure.py` are parameters: print one cup and plug, measure the bore and groove, and adjust
before ordering more.

Sources: [JLC3DP capabilities](https://jlc3dp.com/capabilities/3d-printing-service),
[JLC3DP SLA resins](https://jlcpcb.com/help/article/223-Comparing-SLA-Resin-Materials),
[JLC3DP MJF materials (incl. PP)](https://jlc3dp.com/blog/mjf).

### 2.4 Purchased parts (enclosure)

| Qty | Part |
|---|---|
| 1 | O-ring 88 × 1.5 mm, EPDM 70 Sh A (buy a few) |
| 4 | Screw M2 × 4 mm, A4 (316) stainless, self-tapping for plastics (PT/plastite style), flat head |
| 1 | PORON foam 1.0 mm, about 30 × 50 mm (behind the coil) |
| 1 | Thermal gap pad 0.5 mm, 10 × 7 mm (TMP117 tab ↔ thermal window) |
| 2 | Suction cup Ø40 mm with mushroom head (head ≈ 10 mm, neck ≈ 5 mm) |
| – | Silicone O-ring grease (no epoxy anywhere) |

### 2.5 Assembly and leak test
1. Put the gap pad on the cup's thermal window. Drop the PCB in electrode-side-first, then the battery, coil and foam.
2. Grease the O-ring lightly, roll it into the plug groove, and press the plug in (the lead-in chamfer guides it). Fit the 4 screws.
3. **Leak test before first bath use.** Put the closed device in a jar of water and pull a light vacuum
   (a hand vacuum pump or a food-saver jar). A stream of bubbles marks a leak. Then do 1 h at 0.5 m in 45 °C
   water, and 20 cycles between 15 °C and 45 °C. A humidity-indicator dot inside makes any ingress visible.
4. To open: remove the 4 screws and lever the plug out at the top notch.

### 2.6 Notes
- **Buoyancy:** it displaces about 59 cm³. In SLA resin the device weighs about 62 g and sinks slowly; in PP about 57 g and barely floats.
  It doesn't matter in the bracket. If floating is wanted, drop the plug posts and use foam instead.
- **LED:** natural (translucent) PP or a clear resin shows the status LED through the wall. With an opaque material,
  add a 0.8 mm thin spot in the plug above the LED.
- **Qi:** the coil sits 1.5 mm behind the plug's outer face, well inside the ~5 mm limit.
- **Body contact:** the outer surfaces are plastic only. The screw heads are A4 stainless (passive, very low nickel release)
  and sit on the side walls.

Outputs: `hardware/mech/out/{cup,plug,bracket}.step|.stl`, `assembly.step`. Rebuild with
`python3 hardware/mech/enclosure.py` and check with `python3 hardware/mech/fit_and_render.py`.
