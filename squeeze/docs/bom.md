# squeeze: bill of materials

Prices are rough (USD, late 2026) and cover **both units** unless noted. Search the part names. Brands are
examples, not requirements.

## Stage 1: breadboard (test the fun)

| Qty | Part | Why | ~$ |
|---|---|---|---|
| 2 | Seeed Studio **XIAO ESP32-C3** (with its FPC antenna) | Radio and brain, same as the keeper | 10 |
| 2 | **BMP390** pressure sensor breakout, I2C, STEMMA QT (Adafruit or similar) | Squeeze sensor | 22 |
| 2 | STEMMA QT / Qwiic to female header cable, or 4 jumper wires | Sensor to XIAO (3V3, GND, SDA = D4, SCL = D5) | 2 |
| 2 | **SG90 micro servo** (or MG90S, metal gear) | Actuator. Signal on D10, power from the XIAO's 5V pin (USB) | 6 |
| 2 | 470 µF 10 V electrolytic capacitor | Across the servo's supply (start-up current) | 1 |
| 2 | Rubber **ear-syringe bulb** (no valve), ~60 ml | The thing you squeeze | 6 |
| 2 | Small airtight food box (or a pill bottle) + 30 cm of 3 mm ID silicone tube | Sensor inside, tube to the bulb. Seal the wire and tube holes with hot glue | 6 |
| 2 | Common-cathode RGB LED (5 mm) + 3 × 220 Ω | Optional at this stage: R = D2, G = D6, B = D7 | 1 |
| 2 | USB-C cable + phone charger or power bank | No battery yet: with none fitted the firmware never sleeps | — |
| 2 | Jumper wire **D1 to GND** | Tells the firmware there is no battery (it reads 0 V), so it stays awake on USB. A floating D1 could read as a battery | — |
| | **Total** | | **~55** |

To feel the squeeze: tape the servo to a flat stick. Glue a coin-sized foam pad on the horn's end and set it so the horn
presses the pad into your palm as it turns. Hold the stick and the bulb in the same hand.

## Stage 2: the keeper (per pair)

### Electronics
| Qty | Part | Notes | ~$ |
|---|---|---|---|
| 2 | Seeed XIAO ESP32-C3 | | 10 |
| 2 | Carrier PCB, 32 × 22 mm, 2-layer, JLC SMT | To design (KiCad), reusing brim's Qi block | 30 (5 boards min.) |
| 2 | TI **BQ51050B** + its passives (as brim rev C) | Qi receiver + Li-ion charger. R_ILIM for ~200 mA | on the PCB |
| 2 | **TDK WR303050-12F5-ID** Qi coil | The same coil as brim (`docs/bom-hand-parts.md` line 2) | 9 |
| 2 | **TPS61023** boost + 1 µH inductor, **TPS22918** load switch, 220 µF bulk (2 × 100 µF 1206) | Servo 5 V, switched fully off when idle | on the PCB |
| 2 | **Bosch BMP390** (LGA) | | on the PCB |
| 2 | **503030 LiPo** 3.7 V ~400 mAh **with protection PCM**, wire leads | 5 × 30 × 30 mm. Check the listing's dimensions; 31 mm wide still fits | 12 |
| 2 | SG90 micro servo, or a coreless metal-gear 9 g servo if the SG90 is too noisy | Cut the mounting tabs off | 6–30 |
| 2 | Common-cathode RGB LED, 0603 or 3 mm, on a small wired tab | Under the dome | 1 |
| 2 | 1.6 mm PORON foam (brim's McMaster 86375K132 sheet covers this) | Pad over the coil | — |
| 2 | Qi charging pad (5 W is plenty) | Any; brim's works | 20 |

### Mechanical
| Qty | Part | Notes | ~$ |
|---|---|---|---|
| 1 set | Printed parts per unit: base, chassis, 2 plates, cam (`hardware/mech/out/*.stl`) | JLC3DP SLA resin (8001 / 9600) or MJF. ~10 parts per pair | 25 |
| 1 set | Skin mold: 2 halves + core (`mold_*.stl`), **SLA** | One mold casts both skins | 20 |
| 1 | **Smooth-On Dragon Skin 10 MEDIUM** trial unit (2 lb) | ~25 g per skin. Plenty for retries | 35 |
| 1 | **Smooth-On Silc Pig** pigments (blue, orange; or a sampler) | A few drops per skin | 25 |
| 1 | Ease Release 200 (or another silicone release) | | 20 |
| 1 | Clear acrylic spray or shellac | Seals the resin mold against cure inhibition | 8 |
| 4 | M2 × 6 thread-forming screws (brim's McMaster 95893A165 fits) | 2 per unit | — |
| 1 | RTV silicone sealant (clear) | Skin-to-base air seal | 6 |
| 2 | Small silicone O-rings ~1.5 × 25 mm ID | Plate return bands (CAD rev B) | 2 |
| | **Total** (beyond stage 1 and what brim already has) | | **~250–300** |
