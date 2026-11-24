# brim: product requirements (rev C)

**Status:** baseline for the rev C prototypes, 2026-11-24. Supersedes the short table in [design.md §1](design.md#1-requirements).
Each requirement has an ID, a "shall" statement, where it comes from, and how it is verified. Hardware and software
requirements trace up to the system requirement they serve (**Parent**).

**Verification methods:** **T** test, **A** analysis or calculation, **I** inspection, **D** demonstration.
**Status:** **Met** (shown by design, analysis or an automated check that already runs), **Bench** (needs the
prototype; the procedure is named), **Open** (not yet designed or decided).

---

## 1. Product

### 1.1 What it is
brim is a sealed sensor that sits on the inside wall of a bathtub. It watches the water level and temperature while
the tub fills, warns the owner's phone about two minutes before the water reaches their chosen line, alerts again at
the line, and signals locally with a light and a beeper. It charges on a standard Qi pad.

### 1.2 Users and situations
| User | Situation | What they need |
|---|---|---|
| Parent of young children (primary for launch) | Runs the bath while getting the children ready | A warning before it's full, and a "too hot for little ones" alert |
| Family caring for an older relative | The relative runs their own bath | Alerts to a relative's phone, temperature limit |
| Landlord, short-term-rental host | Guests run baths | Overflow warning, proof the device is working |
| Anyone who gets distracted | Phone call, doorbell | Not having to watch the tub |

### 1.3 Safety position
brim warns about the **water**. It is not a child-safety, drowning-prevention or medical device, and its
documentation, packaging and marketing shall say so (SYS-SAF-05).

### 1.4 Out of scope (rev C)
Controlling taps or drains; detecting a person in the water; a phone app of our own; Bluetooth; voice assistants
(considered for later); a display or buttons.

---

## 2. System requirements

### 2.1 Function
| ID | Requirement | Source | Verify | Status |
|---|---|---|---|---|
| SYS-FN-01 | The system shall detect the water reaching a user-chosen level within a 60 mm sensing span on the tub wall. | Core need | T: bring-up §2, design §8.1 | Bench |
| SYS-FN-02 | The alarm shall trigger within ±5 mm of the chosen level. | Overflow margin | T: 10-fill repeatability, design §8.1 | Bench (sim: 1.8 mm worst case) |
| SYS-FN-03 | The system shall send a "nearly full" warning when the predicted time to the chosen level is ≤ 2 min, at fill rates from 3 to 30 mm/min. | Early warning is the key difference from simple alarms | T: host test `test_policy`; bench fill | Met (logic) / Bench |
| SYS-FN-04 | The system shall repeat the full alarm every 60 s while the water keeps rising, for up to 15 min, unless silenced. | Forgotten tap | T: host test | Met |
| SYS-FN-05 | After the water has stopped for 2 min, a renewed rise (top-up) shall raise a new alarm, even after the previous one was silenced. | Hot-water top-ups are common | T: host test `test_refill` | Met (logic) |
| SYS-FN-06 | The system shall measure water temperature and alert above a user limit (default 38 °C, range 30–50 °C). | Scald risk for young children | T: bring-up §3; host test | Met / Bench |
| SYS-FN-07 | The system shall offer an optional "cooling down" alert (25–37 °C), which only fires after the bath has been warm. | Caregivers | T: host test `test_cool` | Met |
| SYS-FN-08 | The system shall detect being knocked out of position (tilt > 30° for 20 s during a bath) and being fully submerged, and alert. | Wrong readings must not look like "all fine" | T: host tests; bench | Met / Bench |
| SYS-FN-09 | The system shall tell the owner when it stops working: a server-side alert after 3 days without a check-in. | A silent failure is the worst failure of a reminder device | D: unplug Wi-Fi for 3 days | Bench |

### 2.2 Alerts
| ID | Requirement | Source | Verify | Status |
|---|---|---|---|---|
| SYS-AL-01 | Alerts shall reach a phone through a free, account-free push service (ntfy), on iPhone and Android. | No app of our own | D | Met |
| SYS-AL-02 | A phone alert shall arrive within 15 s of the event when the home Wi-Fi is up. | Two-minute warning budget | T: stopwatch over 10 alerts | Bench |
| SYS-AL-03 | The full alarm shall also sound and flash on the device within 4 s, without Wi-Fi. | Phone in another room, Wi-Fi down | T | Bench |
| SYS-AL-04 | A double-tap on the device shall silence repeats for the current fill. | Parent is already there | T | Bench |
| SYS-AL-05 | Every alert text shall say what happened and what to do, in plain words. | Usability | I: policy.c messages | Met |
| SYS-AL-06 | The whole household shall be able to receive the same alerts. | Families | D: two phones subscribed to one topic | Met (ntfy) |

### 2.3 Use and setup
| ID | Requirement | Source | Verify | Status |
|---|---|---|---|---|
| SYS-US-01 | A first-time user shall complete setup in ≤ 10 min without an account, using the quick start card. | Product promise | D: 5 untrained users | Bench |
| SYS-US-02 | Setup shall confirm success on the phone ("brim is connected") and say clearly when the Wi-Fi password is wrong. | Wrong password otherwise found at the first full bath | D | Met (firmware) |
| SYS-US-03 | Mounting shall need no tools: two suction cups and a slide-in bracket on smooth acrylic, enamel, steel or glazed tile. | Renters | D | Bench |
| SYS-US-04 | Charging shall be: lay it on any flat Qi pad, back down. Phones with Samsung Wireless PowerShare or Pixel Battery Share shall also work. | Not everyone owns a pad | T: 3 pads + 2 phones | Bench |
| SYS-US-05 | Settings shall be reachable from the phone while brim is on the charger, with no IP address to type. | Usability | D | Met |
| SYS-US-06 | Every device state shall be shown by a distinct light pattern, documented in the quick start guide. | Usability | I: status.c vs guide | Met |

### 2.4 Performance
| ID | Requirement | Source | Verify | Status |
|---|---|---|---|---|
| SYS-PF-01 | Battery life shall be ≥ 4 months at one bath a day (target 6). | Charge about twice a year | A: design §3.6; T: PPK2 per-bath charge | Bench |
| SYS-PF-02 | A full charge shall take ≤ 3 h. | Overnight not needed | T | Bench |
| SYS-PF-03 | Temperature accuracy shall be ±0.5 °C at 30–45 °C water in the closed enclosure. | Allows an NTC in cost-reduced tiers | T: bring-up §3 | Bench |
| SYS-PF-04 | Outside dimensions shall be ≤ 45 × 120 × 11 mm, weight ≤ 60 g. | Small enough to ignore | I: CAD (43.8 × 119.8 × 10.45 mm) | Met / Bench (weight) |
| SYS-PF-05 | Splashes, bubble bath, bath oils and condensation shall cause no false alarm. | Real baths | T: bring-up §2 spray and salt tests | Bench |

### 2.5 Environment and durability
| ID | Requirement | Source | Verify | Status |
|---|---|---|---|---|
| SYS-EN-01 | The device shall be sealed to IP68: 1 h at 0.5 m in 45 °C water, then 20 cycles between 15 °C and 45 °C, with no ingress. | Lives in the bath | T: enclosure §2.5 | Bench |
| SYS-EN-02 | Operating water temperature 10–50 °C; storage −10 to 50 °C. | Bath use | A | Met (parts rated) |
| SYS-EN-03 | The device shall survive a 1 m drop onto tile and squeezing by a child. | Households with kids | T | Open (test to add) |
| SYS-EN-04 | Outer surfaces shall resist soap, shampoo and bath oils, and be cleanable. | Bath use | T: soak test | Bench |

### 2.6 Safety
| ID | Requirement | Source | Verify | Status |
|---|---|---|---|---|
| SYS-SAF-01 | No conductor shall be exposed to the water; maximum internal voltage 4.2 V. | Shock | I | Met |
| SYS-SAF-02 | The cell shall be protected against overcharge, overdischarge, overcurrent and short circuit, charged ≤ 0.5 C, and the enclosure shall allow +10 % cell swelling without load on the case. | Li-ion safety | A: design §5, enclosure fit check | Met |
| SYS-SAF-03 | Charging shall happen only out of the bath; the guide shall say the pad stays out of the wet zone. | Mains device | I | Met |
| SYS-SAF-04 | Outer materials shall be suitable for skin contact in production (PP or certified material; resin prototypes are test units only). | Body contact | I | Open (production material) |
| SYS-SAF-05 | All user-facing material shall state that brim watches the water, not the child, and that children must never be left alone in the bath. | Safety position, liability | I: site, guide | Met |

### 2.7 Security and privacy
| ID | Requirement | Source | Verify | Status |
|---|---|---|---|---|
| SYS-SEC-01 | Nobody without physical access shall be able to change settings or firmware. | Silently disabling alarms | A: security.md | Met |
| SYS-SEC-02 | Only firmware signed with our key shall run (release and production builds). | Supply chain | T: signature check | Met |
| SYS-SEC-03 | The home Wi-Fi password and alert topic shall not travel or rest in clear text (WPA2 setup network; encrypted storage in production). | Privacy | A: security.md | Met |
| SYS-SEC-04 | Shipped firmware shall have no known unpatched CVEs at release; the SBOM shall be re-checked monthly while units are in use. | Hygiene | T: docs/sbom | Met (2026-11-23: 0 CVEs) |
| SYS-SEC-05 | No personal data shall be collected by us; alerts go only to the owner's ntfy topic. | Privacy | I | Met |

### 2.8 Compliance (production)
| ID | Requirement | Verify | Status |
|---|---|---|---|
| SYS-CMP-01 | FCC Part 15B (US) and CE RED / UKCA (EU/UK), using the radio module's existing certification. | Lab test | Open |
| SYS-CMP-02 | Battery: UN38.3 cell, IEC 62133 where required; shipping as lithium-ion contained in equipment. | Supplier documents | Open |
| SYS-CMP-03 | RoHS and REACH for all parts and materials. | Supplier declarations | Open |
| SYS-CMP-04 | Marketing to parents shall not make brim a "children's product" under US CPSIA (intended for the adult). | Legal review | Open |

### 2.9 Cost
| ID | Requirement | Verify | Status |
|---|---|---|---|
| SYS-CST-01 | Landed cost of the full design ≤ US$50 per unit at 1,000 units (printed case). | Cost model | Met (est. $49) |
| SYS-CST-02 | A cost-reduced variant shall be possible at ≤ US$20 parts and assembly without changing the system requirements above, except SYS-US-04 (no charging needed). | Cost model, Lean tier | Met (est. $18) |

---

## 3. Hardware subsystems

### 3.1 Sensing (HW-SNS)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| HW-SNS-01 | Six level electrodes, 30 mm wide on 10 mm pitch, plus one dry reference electrode above them, on the PCB's front copper under white solder mask. | SYS-FN-01 | I: board | Met |
| HW-SNS-02 | The electrodes shall sense through a 1.2 mm plastic wall with no air gap (the stack clamps the PCB to the wall). | SYS-FN-01 | A: fit check (PCB face at wall) | Met |
| HW-SNS-03 | A driven shield (side strips + inner-layer plane) shall surround the electrodes to reject water films. | SYS-PF-05 | I | Met |
| HW-SNS-04 | Each fully covered pad shall change its reading by ≥ 15 % (touch) or ≥ 3 pF (FDC1004). | SYS-FN-02 | T: bring-up §2 | Bench |
| HW-SNS-05 | The board shall support both the ESP32-S3 touch sensing and an FDC1004, selected by fitted 0 Ω links. | Risk reduction | I | Met |
| HW-SNS-06 | Water temperature: TMP117 on a thermally isolated board tab pressed to a thin wall window via a gap pad; powered only while measuring. | SYS-PF-03 | T | Bench |

### 3.2 Power (HW-PWR)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| HW-PWR-01 | Qi (WPC BPP) receiver + charger BQ51050B with TDK WR303050 coil; coil within 2 mm of the back face. | SYS-US-04 | T: 3 pads | Bench |
| HW-PWR-02 | Charge current 143 mA (R_ILIM 2.196 kΩ), termination ~60 mA, battery temperature via on-board NTC. | SYS-SAF-02 | T: bring-up §4 | Bench |
| HW-PWR-03 | Cell: protected Li-ion 3.7 V, 320 mAh (≥ 300), 25.5 × 36 × 4.3 mm. | SYS-PF-01 | I | Met |
| HW-PWR-04 | 3.3 V regulator ≥ 500 mA peak (Wi-Fi), quiescent ≤ 2 µA (RT9080). | SYS-PF-01 | I | Met |
| HW-PWR-05 | Deep-sleep current, dry and off the pad, ≤ 30 µA (target 20). | SYS-PF-01 | T: PPK2, bring-up §6 | Bench |
| HW-PWR-06 | Qi presence and charge status shall be readable by the MCU, and placing it on a pad shall wake it. | SYS-US-04 | T | Bench |
| HW-PWR-07 | Battery voltage measurable to ±50 mV. | SYS-PF-01 | T | Bench |

### 3.3 Processing and radio (HW-MCU)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| HW-MCU-01 | ESP32-S3-MINI-1-N8 module (pre-certified radio), antenna overhanging the board edge, no copper under it. | SYS-CMP-01 | I | Met |
| HW-MCU-02 | Wi-Fi RSSI ≥ −75 dBm at the router distance with the device on acrylic and steel tubs. | SYS-AL-02 | T: design §8.4 | Bench |
| HW-MCU-03 | Programmable without the enclosure through a break-off USB-C tab, and through test pads after it is removed. | Manufacturing | D | Met |

### 3.4 User interface (HW-UI)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| HW-UI-01 | RGB LED via an I²C driver (AW2013), visible through the translucent case in a lit bathroom. | SYS-US-06 | D | Bench |
| HW-UI-02 | Piezo sounder bonded inside the back cover, ≥ 70 dB(A) at 1 m (target; tune frequency on the bench). | SYS-AL-03 | T | Bench |
| HW-UI-03 | Accelerometer (LIS2DW12) for double-tap, motion wake and tilt, ≤ 1 µA in its wake mode. | SYS-AL-04, SYS-FN-08 | T | Bench |

### 3.5 Board (HW-PCB)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| HW-PCB-01 | 4-layer, 1.0 mm FR-4, white solder mask, ENIG, standard 0.3/0.6 mm vias, single-sided assembly at JLCPCB. | Manufacturing | I | Met |
| HW-PCB-02 | Design rules: 0 clearance errors, 0 unconnected nets; schematic and board netlists match. | Quality | T: DRC, `verify_netlist.py` | Met (2026-11-23) |
| HW-PCB-03 | All assembled parts available at JLC with stock ≥ 10× the build. | Supply | T: stock check | Met (2026-11-23) |

### 3.6 Mechanical (HW-MECH)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| HW-MECH-01 | One-piece cup and a plug sealed by a radial 90 × 1.5 mm O-ring (22 % squeeze, ~65 % fill), held by 4 × M2 screws outboard of the seal; no glue. | SYS-EN-01 | A: gland calc; T: leak test | Met / Bench |
| HW-MECH-02 | Internal stack clamps the PCB to the front wall; 1.6 mm PORON foam absorbs +10 % battery swelling at ≤ 50 % compression. | HW-SNS-02, SYS-SAF-02 | A: `enclosure.py` assert | Met |
| HW-MECH-03 | Zero interference between all internal parts and the case in CAD, including a 0.6 mm rough stub from the broken-off tab. | Fit | A: `fit_and_render.py` | Met |
| HW-MECH-04 | Bracket with two 40 mm mushroom-head suction cups; its top sits 3 mm below the full line; lips cover only the front edge round. | SYS-US-03 | I | Met |
| HW-MECH-05 | Front face: alarm arrows at the default full line, side waterline grooves, grip grooves in the dry band; 3 mm front edge round. | SYS-US-03 | I | Met |
| HW-MECH-06 | A humidity indicator inside the case shows any ingress. | SYS-EN-01 | I | Met |

### 3.7 Manufacturing (HW-MFG)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| HW-MFG-01 | Each unit is flashed once: firmware plus a per-unit setup password and serial in a factory partition, in one pass, printed with a Wi-Fi QR code on its card. | SYS-SEC-03 | D: `flash_unit.py` | Met |
| HW-MFG-02 | Each unit passes a functional test and a leak test before packing. | SYS-EN-01 | D | Open (fixture) |

---

## 4. Software subsystems

### 4.1 Level sensing (SW-LVL)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| SW-LVL-01 | Estimate the level from the pads with per-pad learned full-wet values and reference-pad drift compensation, ±2 mm after one fill. | SYS-FN-02 | T: host tests (1.8 mm sim) | Met (sim) / Bench |
| SW-LVL-02 | Reject water films: a pad counts only once the pad below is ≥ 90 % wet. | SYS-PF-05 | T: host tests | Met |
| SW-LVL-03 | Estimate the fill rate by least squares over 60 s and the time to the line. | SYS-FN-03 | T: host tests | Met |
| SW-LVL-04 | Re-learn the dry baseline on every charger placement and after each drained bath. | SYS-FN-02 | I | Met |
| SW-LVL-05 | Fall back to touch sensing automatically on a board without the FDC1004. | HW-SNS-05 | T | Bench |

### 4.2 Alert policy (SW-POL)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| SW-POL-01 | Events: filling (optional), nearly full, full, still filling, filling again, too hot, cooling down, submerged, tilted, battery low, battery empty, check-in, not checked in. | SYS-FN-* | T: host tests | Met |
| SW-POL-02 | Each event at most once per bath, except the full-alarm repeats (SYS-FN-04) and re-arm (SYS-FN-05). | SYS-AL-05 | T | Met |
| SW-POL-03 | Time handling with ≥ 1 s resolution over the device's life (no float wall-clock time). | All timing | T: `test_refill` on a 1.7e9 s base | Met |
| SW-POL-04 | The policy shall be pure C with no hardware calls, built and tested on the host. | Testability | T: `make -C test` | Met (48 checks) |

### 4.3 Power management (SW-PWR)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| SW-PWR-01 | Deep sleep when dry, waking on: water at the wake pad (touch, checked every ~0.5 s), Qi placement, motion, check-in timer. | SYS-PF-01 | T | Bench |
| SW-PWR-02 | During a fill, sample every 2 s in light sleep; when steady, sleep 5 min, or 1 min near or at the line. | SYS-FN-05 | I | Met |
| SW-PWR-03 | Radio off between alerts; reuse a live connection within one alert burst. | SYS-PF-01 | I | Met |
| SW-PWR-04 | On the pad, stay awake (pad-powered) with the charging light until lifted. | SYS-US-06 | D | Bench |
| SW-PWR-05 | Below 3.45 V: one "battery empty" alert, then sleep until placed on a charger. | SYS-SAF-02 | T | Bench |

### 4.4 Connectivity and alerts (SW-NET)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| SW-NET-01 | 2.4 GHz Wi-Fi station (WPA2-PSK or open); HTTPS to ntfy with certificate verification against the built-in CA bundle. | SYS-AL-01, SYS-SEC-03 | I | Met |
| SW-NET-02 | Retry each alert 3 times; if the phone alert fails, sound the local alarm for nearly-full and too-hot too. | SYS-AL-03 | I | Met |
| SW-NET-03 | Every 2 days, re-arm a 70 h scheduled "hasn't checked in" message on the ntfy server; weekly silent "brim OK" with battery; cancel the scheduled message on factory reset. | SYS-FN-09 | D | Bench |
| SW-NET-04 | Works with a self-hosted ntfy server; servers that can't schedule are detected and not retried every 6 h. | SYS-AL-01 | I | Met |

### 4.5 Setup and settings (SW-CFG)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| SW-CFG-01 | Setup network `brim-setup-XXXX` (WPA2, per-unit password) with a captive portal; times out after 15 min, restarted by a tap or the charger. | SYS-US-01 | D | Met |
| SW-CFG-02 | Verify the Wi-Fi details after saving; on failure reopen setup with the reason. | SYS-US-02 | D | Met |
| SW-CFG-03 | Settings: Wi-Fi, alarm pad (only the pads the chosen sensing can see), hot limit with 38/40/42 quick-set, optional cooling level, filling alert, ntfy server, sensing method; test alert; firmware upload. | SYS-US-05 | I | Met |
| SW-CFG-04 | One silent "brim is charging" notification per placement that opens the settings page. | SYS-US-05 | D | Met |
| SW-CFG-05 | Factory reset: 3 placements in 20 s, confirmed by a double-tap within 10 s. | Usability | D | Met (firmware) |

### 4.6 Device interface (SW-UI)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| SW-UI-01 | Light patterns: cyan blink setup, blue blip watching, yellow breathing nearly full, red fast blink full, white steady silenced, amber breathing charging, green steady charged, magenta breathing too hot, orange blink tilted, one-second battery flash on a tap. | SYS-US-06 | I: status.c vs guide | Met |
| SW-UI-02 | Full alarm: three bursts of three beeps, repeated with the phone alert; a chirp on silence. | SYS-AL-03 | D | Bench |
| SW-UI-03 | Double-tap: silence during a bath, unlock settings for 2 min on the charger, confirm a factory reset. | SYS-AL-04, SYS-SEC-01 | D | Bench |

### 4.7 Security and updates (SW-SEC)
| ID | Requirement | Parent | Verify | Status |
|---|---|---|---|---|
| SW-SEC-01 | Settings and firmware changes on the home network need a per-session key, a Host header naming the device, and a double-tap unlock. | SYS-SEC-01 | A: security.md | Met |
| SW-SEC-02 | All values on pages HTML-escaped; inputs length-checked. | SYS-SEC-01 | T: fuzz (DNS, escaping) | Met |
| SW-SEC-03 | OTA: signed images only (release/production); size-checked; a new image is kept only after it boots successfully (rollback). | SYS-SEC-02 | T | Met / Bench |
| SW-SEC-04 | Production: Secure Boot V2, flash encryption (release mode), NVS encryption, JTAG off. | SYS-SEC-03 | I: sdkconfig.production | Met |
| SW-SEC-05 | ESP-IDF ≥ v5.3.6; SBOM regenerated per release. | SYS-SEC-04 | T | Met |

---

## 5. Open items before production
1. Bench results for every **Bench** item, starting with sensing (SYS-FN-01/02, SYS-PF-05), charging (HW-PWR-01/02),
   sleep current (HW-PWR-05) and the leak test (SYS-EN-01).
2. Drop and squeeze test (SYS-EN-03): define the procedure.
3. Production material for the case (SYS-SAF-04) and the injection-mold decision (see the cost model).
4. Compliance plan and lab quotes (SYS-CMP-01…04).
5. Production test fixture (HW-MFG-02).
6. Choose one sensing method after the comparison in [sensing-options.md](sensing-options.md); update HW-SNS-05.

Related documents: [design.md](design.md), [enclosure.md](enclosure.md), [bring-up.md](bring-up.md),
[security.md](security.md), [sbom/](sbom/README.md), [bom-hand-parts.md](bom-hand-parts.md),
[../firmware/README.md](../firmware/README.md).
