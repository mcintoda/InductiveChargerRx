# squeeze: what to order, where, and how to put it together

Everything for **one pair** (a parent's unit and a child's unit). Prices are rough (USD, late 2026).

| # | Order | From | Files | ~$ |
|---|---|---|---|---|
| 1 | Main board, assembled (all parts on top) | **JLCPCB** PCB + PCBA | `hardware/fab/squeeze-gerbers.zip`, `bom_jlc.csv`, `cpl_jlc.csv` | 60–90 for 2 assembled (5 bare) |
| 2 | Printed parts for both units + the skin mold | **JLC3DP** | `hardware/mech/out/*.stl` | 40–60 |
| 3 | Parts JLC does not mount (coil, battery, servo, antenna, O-rings, screws) | LCSC (same cart as the PCB) / Amazon / DigiKey | `hardware/fab/hand_parts.csv`, list below | 50–70 |
| 4 | Silicone for the skins | Smooth-On dealer / Amazon | the mold from #2 | 70–80 |

The skin is the one part JLC can't make. JLC3DP prints, but it doesn't cast silicone, and its flexible
print material (TPU, about Shore 88A) is far too stiff to squeeze. You cast the two skins at home in the
printed mold, in about 30 minutes of work plus curing (section 4). If you'd rather not, a vacuum-casting service
(for example PCBWay's) can make them from `out/skin.step`; ask for the softest silicone they offer (about Shore 10–20A).

---

## 1. JLCPCB: the main board

Upload `hardware/fab/squeeze-gerbers.zip` at jlcpcb.com → *Order now*.

| Setting | Value | Why |
|---|---|---|
| Layers | **4** | Solid ground plane under the module and the charger |
| PCB thickness | **1.0 mm** | Height budget inside the base |
| Surface finish | **ENIG** | Flat pads for the QFN, the LGA sensor and the module |
| Via covering | Tented (default) | |
| Min via hole / diameter | 0.25 / 0.5 mm (standard, no extra cost) | |
| Quantity | 5 (minimum) | Assemble 2, or 3 to keep a spare |
| Everything else | default | |

The outline includes the **LED tab** above the top edge. It is joined by two necks with mouse-bite holes, and JLC
routes it as one board. If JLC asks for edge rails for assembly, accept them.

**PCB Assembly** (switch it on in the same order):
- Assemble **top side**, quantity 2 (or 3). Tooling holes: added by JLC.
- Upload `bom_jlc.csv` and `cpl_jlc.csv`.
- **BOM check:** ICs, connectors, the LED, the NTC and the inductor carry LCSC numbers. The plain resistors and
  capacitors are matched by JLC from the comment (value, rating, package). Accept the **Basic** part it suggests
  whenever one matches.
- **Stock check:** the **BMP280 (C83291)** is marked discontinued at LCSC and still had stock at the time of writing. If it
  shows zero, choose JLC's "pre-order" or ask me to switch to another sensor.
- **Placement preview: check the rotation of the polarised parts.** KiCad and JLC sometimes disagree by 90/180°.
  Look at the pin-1 marks of U1 (ESP32 module), U2 (BQ51050B), U3 (RT9080), U4 (BMP280), U5 (TPS61023),
  D1 (RGB LED) and J3 (USB-C, mouth at the board edge). Rotate any that are wrong in the preview. JLC's engineers
  also review it before production.
- The coil, battery, servo and LED wires are **not** placed: they are through-hole wire pads you solder yourself.

## 2. JLC3DP: the printed parts

Upload the STLs from `hardware/mech/out/`:

| File | Qty | Material | Notes |
|---|---|---|---|
| `base.stl` | 2 | SLA resin, white (standard resin) | Flat 1.2 mm floor over the Qi coil |
| `chassis.stl` | 2 | SLA resin (standard) | |
| `plate_pos.stl` | 2 | SLA resin (standard) | Smooth surface: the bosses slide in the chassis tunnels |
| `plate_neg.stl` | 2 | SLA resin (standard) | |
| `cam.stl` | 2 | SLA resin (standard, or a tough resin if offered) | |
| `mold_half_a.stl`, `mold_half_b.stl`, `mold_core.stl` | 1 each | SLA resin, **high detail** | One mold casts both skins. See the silicone warning in section 4 |

(`skin.stl` is the cast part: don't print it.)

## 3. Hand parts (per pair)

| Qty | Part | Where | Notes |
|---|---|---|---|
| 2 | **TDK WR303050-12F5-ID** Qi receiver coil | LCSC **C6357742**: add it to the same LCSC/JLC cart | Same coil as brim. Lies ferrite side up under the board |
| 2 | **503030 LiPo, 3.7 V ~400 mAh, with protection PCM**, wire leads | Amazon / AliExpress | 5 × 30 × 30 mm (31 mm wide still fits) |
| 2 | **SG90 micro servo** (or MG90S, or a coreless 9 g servo if the SG90 is too noisy) | Amazon | Cut the mounting tabs and the plug off |
| 2 | **2.4 GHz FPC antenna with U.FL, adhesive**, ~100 mm cable | e.g. TE/Linx ANT-2.4-FPC-LH100UF (DigiKey), SparkFun 18086 | Clicks onto the module's U.FL |
| 4 | Silicone O-ring **10 mm ID × 1.5 mm** | Amazon / McMaster | Plate return bands, 2 per unit |
| 4 | M2 × 6 thread-forming screws (brim's McMaster 95893A165) | | 2 per unit, base into chassis |
| — | 1.6 mm PORON foam (brim's sheet), 30 AWG silicone wire, foam tape | | |
| 2 | Qi charging pad (5 W) | Any; brim's works | |

## 4. Skins (the only home process)

Smooth-On **Dragon Skin 10 MEDIUM** (Shore 10A, translucent) + **Silc Pig** pigment (blue and orange) +
**Ease Release 200** + clear acrylic spray. About 25 g of silicone per skin.

1. **Seal the mold first.** Many SLA resins stop platinum silicone from curing. Post-cure the mold parts fully in
   sunlight or UV, spray two coats of clear acrylic, and **test-cure a dab of silicone on the mold** before the real pour.
2. Spray release on the cavity and the core. Bolt or tape the two halves together, cavity up.
3. Mix 25 g (1A:1B by weight) with a few drops of pigment. Pour it into the cavity until it is about 60 % full.
4. Slowly push the core in. Excess silicone leaves through the 8 vent holes in its lid. Weight it down.
5. Wait 5 h (MEDIUM), then demold and trim the vents. Post-bake at 60 °C for 2 h for full cure (skin-safe).
6. Repeat with the other colour.

## 5. Assembly and first flash (per unit)

1. **Coil:** lay it ferrite side **up** on the base floor (glue dot). Put a 1.6 mm PORON pad over it. Feed its two leads
   up through the **COIL** holes of the board and solder.
2. **Battery:** solder red to **BAT +**, black to **BAT −**. The board needs the battery to run, even when flashing.
3. **Servo:** cut the plug off and solder red / brown / orange to **5V / GND / SIG**.
4. **LED tab:** snap it off at the mouse bites with pliers. Solder 4 thin wires, about 70 mm long, from **A R G B** on the
   tab to **A R G B** on the board.
5. **Antenna:** click the U.FL onto the module.
6. **Flash** (USB-C, battery fitted):
   ```
   cd squeeze/firmware
   idf.py menuconfig            # Squeeze pair -> Pair secret: the same on both units
   idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.parent" -B build-parent build flash monitor
   idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.child"  -B build-child  build flash monitor
   ```
   It stays awake while USB is plugged in. Build once with `SQZ_TRACE=y` and squeeze the board's air: the trace shows the
   pressure (about 101 kPa) and the level.
7. **Servo zero:** with USB attached, the servo sits at rest (45°). Press the cam onto the horn with its **short axis
   toward the plates' tunnels** and fit the horn screw.
8. **Mechanics:** put the servo (tabs cut) into the cradle with a dot of hot glue. Fix the battery to the servo's side with foam tape.
   Stick the antenna and the LED tab to the post (LED facing up). Slide the plates' bosses into the tunnels and stretch the two
   O-rings across the pegs.
9. **Close:** lower the chassis onto the base and fit 2 × M2 screws from below. Stretch the skin over until its bead snaps into
   the base groove. Try it first **without RTV**: the stretch-fit is usually airtight enough, and the base can still come off
   for reflashing. If the squeeze signal fades within a second, add a thin bead of RTV in the groove.

## Order checklist
- [ ] JLCPCB: gerbers + PCBA (BOM, CPL), 4 layers, 1.0 mm, ENIG, assemble 2. Rotations checked in the preview
- [ ] Same cart: 2 × coil C6357742
- [ ] JLC3DP: 5 parts × 2 + mold set × 1
- [ ] Batteries, servos, antennas, O-rings
- [ ] Dragon Skin 10 MEDIUM, Silc Pig, Ease Release 200, clear acrylic
