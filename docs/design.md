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
         │ ~500 mAh + PCM │        │  ADC  ◄── VBAT/2             │
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
- Charge current is set by R_ILIM = 1k + 196R to **~260 mA (0.5 C)**, assuming K_ILIM = 314 (verify). That's gentle and keeps the coil cool.
- The battery NTC goes to the TS pin, so charging stops when the cell is hot or cold.
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
| Cell | 1S Li-ion pouch, ~500 mAh, ≤5 mm thick (e.g. 503040 size), **with integrated protection module (PCM) and 10 k NTC lead** |
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

With 500 mAh, that's about **6–7 months between charges** at one bath per day. Even at 3× worse in practice, it's still 2 months.

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
   ~44 × 118 × 13 mm
```

- **Mounting: a two-part design.** A small *bracket* with two silicone suction cups stays stuck to the tub wall, and the *sensor* slides into it (a snap rail with no metal and no magnets, since magnets disturb Qi).
  - Positioning the bracket once sets the alarm height, so you take the sensor out to charge without moving the bracket.
  - The sensor's back stays flat, so the coil sits within ~2 mm of the Qi pad.
- **Antenna at the top**, ≥20 mm above the top pad, so it stays above water. Water strongly absorbs 2.4 GHz, so mount the bracket with the top of the device above the overflow rim. The owner's tub is **acrylic**, which is RF-transparent and smooth, so it's ideal for suction cups. If the RSSI is still weak (distant router), switch to the ESP32-S3-MINI-1**U** with a short internal antenna routed to the top cap.
- **Sealing**:
  - Prototype: two shells with a silicone O-ring in a groove and A4 (316) stainless screws, or a bonded seam with a marine silicone sealant.
  - Production: ultrasonic weld (no screws).
  - Target IP68 at 0.5 m for 1 h.
  - The sealed air volume makes the device float if it detaches.
- **Materials** (in contact with skin and hot soapy water up to 45 °C):
  - Production: polypropylene (PP) or polycarbonate (PC). Suction cups are platinum-cure / food-grade silicone. No exposed metal (or 316L only).
  - JLC3DP prototype: SLA resin is fine for testing but isn't certified body-safe, so seal it with a clear coat or use MJF PA12 with vapour smoothing. Treat prototypes as test units.
- All edges get ≥1.5 mm radii, since people may lean against it.

---

## 5. Electrical safety and user safety

1. Maximum internal voltage is 4.2 V and the enclosure is sealed with no conductive path to the water, so there's no shock hazard.
2. The Li-ion cell has three protection layers: the cell's PCM (overcharge, overdischarge, short circuit), the BQ51050B charge control with NTC temperature cut-off, and the firmware undervoltage cut-off. Charge current is limited to 0.5 C.
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
- Values marked "verify" or "TBD" (R1/R2 charge-current set, R3 termination, C1–C4 resonant tuning, TS/NTC network) must be checked against the BQ51050B datasheet and the chosen coil.
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
