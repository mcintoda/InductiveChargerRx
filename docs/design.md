# Bath Monitor — System Design (rev B)

A sealed, wirelessly charged device that suction-mounts inside the bathtub,
senses the water level **through its plastic wall** (no electrical contact with
water), measures water temperature to ±0.1 °C class accuracy, and pushes an
alert to an iPhone over Wi-Fi before the tub overflows.

---

## 1. Requirements

| # | Requirement | Design response |
|---|-------------|-----------------|
| R1 | Detect water reaching a user-chosen level | 6-segment capacitive ladder behind the front wall. Any segment can be the alarm level, and the lower segments give an early warning and a fill-rate estimate |
| R2 | Non-contact water sensing | Electrodes sit on the PCB inside the enclosure and sense through a 1.2 mm plastic wall. No metal touches the water |
| R3 | Accurate water temperature | TI TMP117 (±0.1 °C, −20…50 °C) on a thermally isolated PCB tongue behind a thin wall window |
| R4 | iOS notification, no BLE pairing, free | Wi-Fi → HTTPS POST to **ntfy** (free, open-source, iOS app on the App Store). No account, no custom app, no server to run |
| R5 | Fully waterproof | Sealed enclosure (IP68 target) with no connectors, buttons or holes |
| R6 | Wireless recharging | Qi-compatible receiver, so it charges on any standard Qi pad |
| R7 | Safe for skin contact | ≤4.2 V internal, no exposed conductors, body-safe plastics and silicone, protected Li-ion cell with temperature-monitored charging |
| R8 | Minimal design | One radio MCU with built-in touch sensing (no separate capacitance IC), one charger IC, one sensor, one LDO |
| R9 | Built at JLCPCB | 4-layer PCB, one-side SMT assembly, JLC Basic/Extended parts, JLC3DP enclosure for prototypes |

### Things deliberately left out
- **BLE app or pairing.** Wi-Fi alone covers it.
- **Display or physical buttons.** Phone notifications cover it, and buttons break the seal.
- **USB port.** It's a water path. Firmware updates go over Wi-Fi (OTA). Factory programming uses test pads before sealing.
- **Separate capacitance-to-digital IC (e.g. FDC1004).** The ESP32-S3's touch peripheral has a hardware *shield driver* designed for water rejection, and it can wake the chip from deep sleep. The FDC1004 would add about $3, an I²C device, and ~29 µA of standby current.
- **Accelerometer, buzzer or RGB LED.** The owner decided against a local beeper (rev B).

---

## 2. Non-contact level-sensing options considered

| Method | Verdict |
|--------|---------|
| **Capacitive through enclosure wall (chosen)** | Sealed, no moving parts, cheap, and works with bubbles. Water's εr ≈ 80 gives a very large signal through 1–2 mm of plastic |
| Capacitive from outside the tub | Not feasible. Steel and cast-iron tubs are conductive, and acrylic tubs have inaccessible fibreglass backing |
| Ultrasonic from the tub rim | Steam and condensation foul the transducer, bubble bath foam scatters the signal, and the device ends up bulkier |
| IR time-of-flight (VL53L…) | Clear water is IR-transparent, so it reads the tub floor. Unreliable |
| Float switch / reed | Moving parts and a water path. Soap scum makes it stick |
| Conductive probes | Exposed metal, electrolysis and corrosion. Violates R2/R7 |

---

## 3. Architecture

```
          Qi pad (outside tub, mains-powered)
                 ┊  ~100–205 kHz
         ┌───────┴───────┐
         │ Rx coil +     │
         │ resonant caps │
         └───────┬───────┘
                 │ AC
         ┌───────▼────────┐  CHG   ┌──────────────────────────────┐
         │  BQ51050B      ├───────►│                              │
         │  Qi Rx + Li-ion│  RECT  │        ESP32-S3-MINI-1       │
         │  charger       ├─div───►│                              │
         └───────┬────────┘        │  Touch T1–T6 ◄── level ladder│
          TS ◄─NTC│ OUT            │  Touch T14  ──► shield driver│
         ┌───────▼────────┐        │  I²C ◄────────► TMP117       │
         │ Li-ion 1S      │        │  GPIO ──► sensor power       │
         │ 320 mAh + PCM  │        │  ADC  ◄── VBAT/2             │
         └───────┬────────┘        │  GPIO ──► status LED         │
                 │ VBAT            │  Wi-Fi ⇢ router ⇢ ntfy.sh     │
         ┌───────▼────────┐  3V3   │          ⇢ iPhone            │
         │ LDO 3.3 V,     ├───────►│                              │
         │ Iq ≈ 2 µA      │        └──────────────────────────────┘
         └────────────────┘
```

### 3.1 MCU: ESP32-S3-MINI-1-N8
- Wi-Fi 2.4 GHz with a PCB antenna and a pre-certified module, so no RF design work.
- **Capacitive touch with a hardware shield driver (T14)**, designed to reject water films and droplets. One touch channel can wake the chip from deep sleep, so the dry standby state needs no CPU polling.
- Native USB on GPIO19/20, used through test pads for the first flash. No USB-UART chip.
- Alternatives considered: the ESP32-C3 and C6 have no touch peripheral, so they would need an FDC1004. The C6 also only offers Wi-Fi 6 power savings that don't matter here.

### 3.2 Level sensor: PCB capacitive ladder
Full study, simulation and figures: **[placement-and-electrodes.md](placement-and-electrodes.md)**.
- 6 level electrodes, **30 × 9 mm at 10 mm pitch** (60 mm range), plus a 30 × 6 mm **dry reference electrode** 4 mm above the top pad (IO7). All on L1, pressed against a flat 1.2 mm wall with no air gap.
- Simulated: about 0.9 pF dry, **+5.8 pF fully wet** per pad. The response is linear across each pad, so interpolation gives the level to **±0.9 mm** over the full range.
- **Driven shield** (T14): L1 side strips plus a hatched L2 plane behind every electrode, with L3 empty and L4 carrying traces only in the electrode band. Driven rather than grounded, the baseline drops from 41 pF to 0.9 pF.
- **Idle electrodes in HIGHZ**, not GND. Simulation shows this is what removes false readings from water films on the wall.
- **Alarm level** = any pad, chosen in the settings page. The default is the top pad. PAD1 (bottom, T1) is the deep-sleep wake channel.

### 3.3 Temperature: TMP117AIDRVR
- ±0.1 °C max from −20 to +50 °C, 16-bit, I²C, ~3.5 µA at 1 Hz. In practice it's powered from a GPIO only while measuring, so ~0 µA when off.
- Placed at the **bottom** of the device (the deepest point), on a 12 × 10 mm PCB tab joined to the board by a 6 mm neck. TMP117 is on the back. A GND copper window on the front, stitched with vias to the TMP117's exposed pad, couples it to the wall.
- A thermal gap pad couples the TMP117 to a **0.8 mm thin-wall window** in the front face.
- Expected performance: steady-state error < 0.2 °C relative to the water, with a time constant of ~60–90 s. Bath temperature changes slowly, so this is acceptable.
- *Upgrade if faster response is needed:* replace the thin wall with a bonded 316L stainless disc (body-safe, nickel-bearing but passive). Keep it ≥15 mm from the Qi coil to avoid eddy heating and foreign-object-detection (FOD) trips.

### 3.4 Wireless charging: BQ51050B
- A single chip combining a Qi (WPC 1.2) receiver and a 4.20 V Li-ion charger, with no separate charger IC needed. It charges on any phone Qi pad.
- Charge current is set by R_ILIM = 2k + 196R = 2196 Ω to **143 mA (0.45 C for the 320 mAh cell)**. The datasheet only characterises K_ILIM = 314 AΩ for 500–1500 mA. TI engineers on E2E say lower settings work with reduced accuracy, as long as fast charge stays above 100 mA and termination above 30 mA ([TI E2E: low charge current accuracy](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/576502/bq51050b-low-charge-current-accuracy)). R_TERM = 10k gives about 60 mA termination (41.7 %). **Verify on the bench** that charging terminates (the 10 h safety timer is the backstop). If it misbehaves, TI's suggested fallback is BQ51003 + BQ25100 (one more IC).
- The battery NTC is **on the PCB** (TH1, Murata NCP15XH103F03RC: 10 kΩ, B = 3380, the type the BQ51050B's internal 20 kΩ bias is designed for), on the back side, pressed against the cell. It connects straight to TS/CTRL, so any protected 2-wire cell works. Charging stops when the cell is too cold or hot (0 / 60 °C) and is reduced between 45 and 60 °C, with no extra resistors.
- The `CHG` output goes to an MCU GPIO. **Qi-present wake:** `RECT` swings from about 5 V up to its clamp level, which is too wide for a plain divider into a 3.3 V pin. So `RECT` drives a BSS138 through a 1M/1M divider, and the BSS138 pulls `QI_DET_N` (1 MΩ pull-up) low on an RTC GPIO. Placing the device on the pad wakes the MCU, and the detector draws 0 µA off the pad.
- **Rx coil**: an ~11 µH Qi receiver coil with a ferrite backing, ≤32 mm diameter (Würth WE-WPCC receiver family or equivalent stocked at LCSC). It sits against the **back wall**. Coil-to-pad distance must stay ≤5 mm including the wall.
- **Resonant capacitors** (per the WPC spec and the BQ51050B datasheet):
  - `C1 = 1 / ((2π·100 kHz)² · Ls′)` where Ls′ is the coil inductance measured *on a transmitter* ferrite. With Ls′ = 11 µH this gives about **230 nF**. The schematic builds it as 100n + 100n + 22n = 222 nF (102 kHz), reusing BOM values.
  - `C2 = 1 / ((2π·1 MHz)² · Ls − 1/C1)` where Ls is the free-space inductance.
  - Tune on the bench with an LCR meter. The exact values depend on the coil chosen.
- Note: if the MCU stays awake with Wi-Fi on while on the pad, its load can keep the charger from reaching termination. The firmware therefore keeps the settings web page up for 10 minutes after placement, then sleeps.

### 3.5 Power
| Item | Choice |
|------|--------|
| Cell | 1S Li-ion pouch, **320 mAh (300 min), 25.5 × 36 × 4.3 mm**, **with integrated protection module (PCM)**, 2 wires (temperature from the PCB NTC) |
| Regulator | **XC6220B331MR** LDO (1 A, Iq ≈ 8 µA), with RT9080-33 (600 mA, 2 µA) as a drop-in alternative footprint. It must cover the ESP32 Wi-Fi TX peaks of ~350 mA |
| Battery monitor | 1 M / 1 M divider + 100 nF into ADC1 (≈2 µA) |
| Sensor rail | TMP117 and its I²C pull-ups are powered from a GPIO, switched on only during measurement |
| Cut-off | Firmware stops at 3.4 V and sends a low-battery notification at 20 % |

Why not a buck converter: from a 3.6–4.2 V battery to 3.3 V, an LDO is 80–90 % efficient. It's the smallest, quietest option and draws almost nothing in standby.

### 3.6 Power budget (estimates, to be confirmed on hardware)

| State | Current | Time per day | mAh/day |
|-------|---------|--------------|---------|
| Deep sleep, touch wake on T1 | ~40 µA | 24 h | ~1.0 |
| Bath active, light sleep, sampling every 2 s | ~2 mA | 25 min | ~0.8 |
| Wi-Fi bursts (~5 events × ~3 s × ~120 mA) | — | — | ~0.5 |
| **Total (one bath per day)** | | | **~2.3** |

With 320 mAh, that's about **4 months between charges** at one bath per day. Even at 3× worse in practice, it's still about 6 weeks.

---

## 4. Mechanical

```
   FRONT (water side)                 SIDE SECTION
  ┌──────────────┐  ▲               front wall      back wall
  │  ◠ antenna   │  │ ~25 mm        │ PCB│batt│coil│
  │  ESP32-S3    │  │ (stays dry)   │    │    │    │
  ├──────────────┤  │               │ pads    ferrite
  │ ▭ pad 6 ←alarm (default)        │    │    │    │
  │ ▭ pad 5      │  │               │    │    │    │
  │ ▭ pad 4      │  │ 60 mm         │ L1 pads face front wall
  │ ▭ pad 3      │  │ sensing       │ coil faces back wall
  │ ▭ pad 2      │  │               │
  │ ▭ pad 1 ←wake│  │               │
  ├──────────────┤  │
  │ ◉ TMP117 window ~15 mm          
  └──────────────┘  ▼
   43.8 × 119.8 × 10.45 mm
```

- **Mounting: a two-part design.** A small *bracket* with two silicone suction cups stays stuck to the tub wall, and the *sensor* slides into it (a snap rail with no metal and no magnets, since magnets disturb Qi).
  - Positioning the bracket once sets the alarm height, so you take the sensor out to charge without moving the bracket.
  - The sensor's back stays flat, so the coil sits within ~2 mm of the Qi pad.
- **Antenna at the top**, ≥20 mm above the top pad, so it stays above water. Water strongly absorbs 2.4 GHz, so mount the bracket with the top of the device above the overflow rim. The owner's tub is **acrylic**, which is RF-transparent and smooth, so it's ideal for suction cups. If the RSSI is still weak (distant router), switch to the ESP32-S3-MINI-1**U** with a short internal antenna routed to the top cap.
- **Sealing** (full design: **[enclosure.md](enclosure.md)**): a one-piece cup plus a plug with a **radial NBR O-ring (90 × 1.5)**, held by 4 × M2 A4 screws outboard of the seal. No epoxy, and it can be opened.
  - Outside size 43.8 × 119.8 × 10.45 mm. CAD (STEP/STL) is in `hardware/mech/out/`, generated by `hardware/mech/enclosure.py`. Interference with the PCB, battery and coil checked: 0.
  - Prototype: JLC3DP SLA resin, or MJF PP. Production: injection-molded PP with the same geometry.
  - Target IP68 at 0.5 m for 1 h, plus a vacuum bubble test and a 15–45 °C cycling test.
  - No off-the-shelf IP68 box is thin enough. The Hammond 1555C2GY works only as a bulky stop-gap (see enclosure.md).
- **Materials** (in contact with skin and hot soapy water up to 45 °C):
  - Production: polypropylene (PP) or polycarbonate (PC). Suction cups are platinum-cure / food-grade silicone. No exposed metal (or 316L only).
  - JLC3DP prototype: SLA resin is fine for testing but isn't certified body-safe, so seal it with a clear coat or use MJF PA12 with vapour smoothing. Treat prototypes as test units.
- All edges get ≥1.5 mm radii, since people may lean against it.

---

## 5. Electrical safety and user safety

1. Maximum internal voltage is 4.2 V and the enclosure is sealed with no conductive path to the water, so there's no shock hazard.
2. The Li-ion cell has three protection layers: the cell's PCM (overcharge, overdischarge, short circuit), the BQ51050B charge control with NTC temperature cut-off, and the firmware undervoltage cut-off. Charge current is limited to 0.45 C (143 mA into 320 mAh). The enclosure leaves room for +10 % cell swelling, taken up by the foam.
3. Charging only happens **out of the bath** on a standard Qi pad. The user guide must state that the pad (a mains device) stays outside the wet zone.
4. The device never heats the water, and the electronics dissipate < 10 mW while sensing.
5. The level alarm fails safe. If a sensor reading is invalid, the battery is critical, or Wi-Fi fails during an active fill, the device keeps retrying and records the event. The low-battery warning is sent while there's still ≥20 % charge.

---

## 6. Firmware behaviour (ESP-IDF, C)

```
           ┌─────────────┐  T1 wet (touch wake)   ┌──────────────┐
  ┌──────► │ DEEP SLEEP  ├──────────────────────► │ FILLING      │
  │        │  ~40 µA     │                        │ sample 2 s   │
  │        └──────┬──────┘                        │ level, rate, │
  │   RECT high   │                               │ temperature  │
  │   (on pad)    ▼                               └──┬───────┬───┘
  │        ┌─────────────┐                 ETA ≤ 2 min│       │ alarm pad wet
  │        │ CHARGING    │                        ┌──▼──┐ ┌──▼────────────┐
  │        │ web config  │                        │WARN │ │ ALARM         │
  │        │ 10 min, OTA │                        │push │ │ Critical push │
  │        └──────┬──────┘                        └─────┘ │ + temperature │
  │               │ timeout / off pad                     └──────┬────────┘
  │               ▼                                              ▼
  └───────────────┴──────────────────────────────  IN BATH: timer wake every 5 min,
                                                   back to DEEP SLEEP when all pads dry
```

**Notifications (examples)**
- `Bath filling — 37.8 °C` (optional, off by default)
- `Bath nearly full — ~2 min to target, 39.1 °C`
- 🔴 `BATH AT TARGET LEVEL — turn off the tap. 39.4 °C` (urgent priority, repeats every 60 s while still rising)
- `Water too hot: 43.0 °C` (threshold configurable, default 42 °C)
- `Sensor detached / submerged` (all pads wet within one sample, which means it fell in)
- `Bath monitor battery low (18 %)`

**Fill-rate estimate**: a linear fit of the interpolated level over the last 60 s gives the time to reach the alarm pad. A typical tub rises 1–3 cm/min, so the 60 mm ladder gives several minutes of warning.

**Setup (no app, no pairing)**
1. On first power-up, or after a reset, the device starts an access point called `BathMonitor-XXXX` with a captive portal.
2. The iPhone joins it, and a page asks for the Wi-Fi network, the alarm pad and the temperature limit. It then shows the generated ntfy topic as a subscribe link.
3. Afterwards, settings are at `http://bathmonitor.local` whenever the device is on the Qi pad.
4. **Factory reset with no buttons:** put it on the pad and lift it off 3 times within 15 s.

**Calibration**
- A dry-air baseline is captured automatically on each charger placement.
- Each pad's wet/dry threshold is set at 50 % of the dry→wet delta measured during the first bath. A per-pad "learn" step is also available on the settings page.
- The capacitance drift with temperature is compensated using the TMP117 reading.

**Notification transport: ntfy (owner's choice, rev B)**
- The device sends an HTTPS POST to `https://ntfy.sh/<topic>`, with headers `Title`, `Priority` and `Tags`. The iPhone subscribes to the same topic in the free ntfy iOS app.
- The topic name acts as the password. Setup generates a long random one (e.g. `bath-7f3k9q2m…`) and shows it as a QR code / link to subscribe.
- **Limitation: ntfy can't send iOS Critical Alerts** (Apple only grants those to approved apps), so it won't sound through Silent or Focus. The firmware makes up for this:
  - The alarm notification uses priority `5` (urgent).
  - It **repeats every 60 s while the alarm pad stays wet and the level keeps rising**, for up to 15 min. It stops automatically once the level stops rising (tap turned off).
  - The setup guide tells the user to allow ntfy in their Focus modes and to enable its sound.
- If ntfy.sh is ever unwanted, the same firmware works with a self-hosted ntfy server (just change the URL).
- To speed up reconnecting, the device stores the BSSID and channel in RTC memory and uses a static IP if configured, giving ~1 s connects.

---

## 7. PCB (JLCPCB)

| Parameter | Value |
|-----------|-------|
| Layers | 4. Electronics band: GND on L1–L3, components on L4. Electrode band: L1 electrodes + shield strips, L2 hatched shield, L3 empty, L4 traces |
| Thickness | 1.0 mm |
| Size | 38 × 102 mm body + 12 × 10 mm thermal tab on a 6 mm neck (see placement study) |
| Assembly | Single-side SMT (L4) |
| Finish | ENIG (flat pads for the module, better for test pads) |
| Solder mask | **White**. Through the translucent case, the electrodes read as soft grey panels, which is the front's level graphic |
| Keep-outs | No copper beneath or beside the module antenna. No copper pour on L1–L3 under the Qi coil footprint (coil is on the battery side, so this mainly matters for the ferrite outline) |
| Test pads | 3V3, GND, EN, IO0, USB D+/D−, VBAT, for a pogo-pin jig |

### ESP32-S3 pin map

| Function | GPIO | Notes |
|----------|------|-------|
| Level pads 1–6 | 1–6 | Touch T1–T6 through 1 kΩ series resistors. T1 is the deep-sleep wake channel |
| Reference pad | 7 | Touch T7 through 1 kΩ. Dry reference electrode for drift compensation |
| Shield driver | 14 | Touch T14 → L1 hatch + L2 plane |
| VBAT sense | 9 | ADC1_CH8, 1M/1M divider |
| I²C SDA / SCL | 10 / 11 | TMP117 at address 0x48 |
| Sensor power | 12 | Feeds TMP117 VDD and the I²C pull-ups |
| Qi present (`QI_DET_N`) | 13 | Active-low from BSS138, RTC GPIO, ext0 wake |
| CHG status | 40 | Open-drain from BQ51050B, pulled up internally (moved from GPIO15 to the right side of the module for a cleaner schematic) |
| Status LED | 21 | Through a 1 kΩ resistor, visible through a thin wall spot |
| USB D− / D+ | 19 / 20 | Test pads only |
| EN / BOOT | EN / 0 | Test pads + RC on EN |

---

## 7a. Schematic (rev A)
- The KiCad 7 project is in `hardware/kicad/`. The schematic is **generated** by `hardware/tools/gen_schematic.py`, so edit the script and rerun it.
- Drawing style: signal flows left to right, series parts are horizontal, shunt parts are vertical, and connections are real wires. GND, +3V3 and VBAT use power symbols. Net labels are used only for six signals that cross between blocks: `CHG_N`, `QI_DET_N`, `VBAT_SENSE`, `SDA`, `SCL` and `SENSE_3V3`.
- Each part in the script also carries its *intended* pin-to-net map. `hardware/tools/verify_netlist.py` exports the netlist with kicad-cli and fails if the drawn wiring differs from that map in any way.
- `hardware/bom_jlc.csv` is generated in JLCPCB's assembly format. The **LCSC part numbers are still blank** and need filling from the JLC parts library before ordering.
- Checks performed: `verify_netlist.py` reports an exact match (44 nets, all unconnected pins flagged). A pin-type check found no undriven power inputs and no output conflicts. KiCad 7's CLI has no ERC, so run ERC in the KiCad GUI (or KiCad 8+) before layout.
- The BQ51050B values have been checked against the TI datasheet (SLUSB42F). Only the resonant capacitors (C1–C4, depend on the chosen coil) and R_FOD (FOD calibration) remain to be tuned on the bench.
- `BathMonitor.pretty` holds the project footprints: `TouchPad_30x9mm`, `RefPad_30x6mm` and `ShieldTap`.
- The BOM uses only 7 capacitor values and 4 resistor values (20 lines in total). See the placement study, section 1.
- The placement-study PCB (`bath_monitor.kicad_pcb`) is generated by `hardware/tools/gen_pcb.py`. It is placed but not routed.

## 8. Validation plan (prototype)
1. **Level.** In a tub, log the raw counts for all pads while filling, with plain water and with bubble bath. Splash and condensation tests should cause no false alarms. Check repeatability over 10 fills.
2. **Temperature.** Compare against a calibrated reference thermometer at 30, 37, 40 and 45 °C, recording the steady-state error and the time constant.
3. **Charging.** Test on 3 different Qi pads. Check that the coil temperature stays below 45 °C and that charge terminates properly.
4. **RF.** Measure RSSI with the device mounted on acrylic and steel tubs, at the router's distance.
5. **Ingress.** 1 h at 0.5 m, plus 20 hot/cold cycles (15 °C ↔ 45 °C) to stress the seal.
6. **Power.** Use a Nordic PPK2 or similar to measure deep-sleep current and the charge consumed per bath.

## 9. Decisions log
| Date | Decision |
|------|----------|
| 2026-11-19 | 60 mm alarm-level range: accepted |
| 2026-11-19 | Notifications: ntfy (free). Pushover dropped |
| 2026-11-19 | No local beeper |
| 2026-11-19 | Tub is acrylic, so the PCB antenna module stays (no -1U variant needed) and standard silicone suction cups are used |
| 2026-11-19 | BOM minimised to 7 capacitor + 4 resistor values. Dry reference electrode added (IO7) |
| 2026-11-19 | Placement: electronics band on top under the antenna, electrodes below, battery behind the electrodes, thermal tab at the bottom. All parts on the back |
| 2026-11-19 | Electrodes 30 × 9 mm, driven hatched L2 shield, idle pads HIGHZ. Polypropylene 1.2 mm wall recommended for production |
| 2026-11-19 | BQ51050B datasheet checked: charge current must be ≥ 500 mA, so the cell grows to 1000 mAh (0.5 C). R_ILIM = 3 × 196R (534 mA), R_TERM = 10k (222 mA), NTC 10k B3380 direct. Added a 2nd 10 µF on RECT and 100 nF on BAT per the reference design |
| 2026-11-19 | Enclosure: custom cup + radial O-ring plug + 4 × M2 screws (no epoxy). No suitable off-the-shelf IP68 box. PCB top corners R5.5 |
| 2026-11-19 | Battery back to 500 mAh (403040, 4 mm thick). Charge at 262 mA (1k + 196R), below the BQ51050B's characterised range but endorsed by TI on E2E; bench-verify termination. NTC moved onto the PCB (TH1), J1 down to 2 wires. Enclosure 43.8 × 119.8 × 10.1 mm. Suction cups sourced (enclosure.md) |
| 2026-11-22 | Battery changed to a protected 320 mAh LiPo, 25.5 × 36 × 4.3 mm (Amazon). R1 1k → 2k (C4109): charge 143 mA (0.45 C), termination ~60 mA. Foam is now the swelling buffer: 1.6 mm PORON installed at 1.25 mm, a +10 % swollen cell takes it to 0.82 mm (49 %). Enclosure 43.8 × 119.8 × 10.45 mm. Runtime estimate ~4 months |
| 2026-11-19 | Branding: working name "brim", drop-to-the-brim mark, foam/tide/deep/aqua palette, Inter type. Debossed logo + wordmark on the dry front band, alarm-level chevrons, Qi target over the coil on the back (docs/branding.md) |
| 2026-11-19 | Brand rev B: ripple (pebble-in-water) mark, muted palette (mist / slate / ink / sea glass), unpainted deboss. Case: 2.5 mm front round, graduated level scale with pad numbers, alarm chevron, waterline groove on the sides, Qi coil outline on the back |
| 2026-11-19 | Markings simplified: level horizontal scale on the left margin only (ticks + pad numbers in one column), alarm chevron on the right; Qi outline is one plain ring (no dashes or alignment ticks) |
| 2026-11-19 | Front markings reverted to the clean look: no scale or numbers. The electrodes show through the translucent cup as grey panels (white solder mask); small alarm arrows on both edges |
| 2026-11-20 | ESP32-S3-MINI-1 footprint corrected (20.5 mm body). Qi coil: TDK WR303050-12F5-ID (8.23 µH); C_s 310 nF, C_d 3.3 nF. All LCSC numbers filled. Hand routing + autorouter prep. Firmware written and building; bring-up plan |
| 2026-11-20 | Level sensing: touch firmware made ratiometric (live reference: divide by a covered pad below; simulated 1.8 mm worst case at ×0.85–1.15 coupling vs 7.9 mm learned-only). FDC1004 added as a fit option on the same PCB (R22–R26 links, U5 in the electronics band). Firmware modes touch / fdc / compare. Choice decided on the bench per docs/sensing-options.md |
| 2026-11-20 | FDC1004 path is the default: FDC-only build (R11, R15, R16, R17, R20 DNP; PAD2 wakes), firmware default mode `fdc` with automatic touch fallback. Touch and both builds kept as variants |
| 2026-11-20 | Break-off USB-C flash tab (J2 HRO TYPE-C-31-M-12, own XC6220 LDO U6, CC Rd = 2 × 10k each): first flash is plug-in-and-flash with no battery or buttons; tab snapped off before assembly. Firmware stays awake while USB is attached |
| 2026-11-22 | J2 (C165948) checked against the HRO TYPE-C-31-M-12 drawing: pinout, pad pitch, peg holes and shell slots match the KiCad footprint (within the drawing's ±0.05 mm). Moved J2 0.76 mm outward: the drawing puts the PCB edge 5.79 mm in front of the peg holes, so the shell overhangs the tab edge by ~0.5 mm and the plug's overmould can't hit the board before it fully seats |
| 2026-11-22 | Flash tab breaks clean enough to skip filing: mouse bites centred on the board edge on all three bridges (two new ones flank the middle bridge's inner-layer traces). The enclosure fit check now models a 0.6 mm rough stub on the right edge: 0 interference with the 0.7 mm side clearance |
| 2026-11-22 | Brand mark rev C: a rectangular bathtub in isometric view with a tap, filled to just below the brim (replaces the ripple). Same geometry drives the case deboss, the logo, a compact app/fav icon and the settings-page header served by the firmware |
| 2026-11-22 | Rev C additions: LIS2DW12 accelerometer (always on, ~1 µA; motion wake, double-tap acknowledge, tilt check), AW2013 I²C RGB LED driver + XL-1615 RGB LED replacing the green LED, 20 mm piezo disc bonded inside the plug driven in antiphase from GPIO16/17. LED and AW2013 sit on the switched sensor rail (an always-on anode would back-feed the unpowered driver), so the LED is capped at 5 mA per colour and pauses during FDC1004 conversions. KTD2026 was out of stock at JLC, hence the AW2013. A case-humidity sensor (SHTC3, seal-leak warning) was tried and dropped; the humidity-indicator dot and the leak test cover the seal |
