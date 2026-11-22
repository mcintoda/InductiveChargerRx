# Bring-up and bench test plan (rev B hardware)

Work through these in order on the first boards. Each step lists what to measure, the pass criterion and,
where the design has a tunable, which constant or part to change. The firmware logs every sample over the
USB test pads (`idf.py monitor`), so most steps need only the log.

**Equipment:** bench supply with current limit, multimeter, LCR meter (100 kHz), µA power analyser (e.g. Nordic PPK2),
a calibrated reference thermometer (±0.1 °C), 2–3 different Qi chargers, a clear container about 15 cm deep, a ruler,
a spray bottle, salt, a vacuum jar or hand vacuum pump.

## 1. Power-up (board only, no battery)
| Check | Pass | If not |
|---|---|---|
| Resistance VBAT–GND and 3V3–GND before power | > 10 kΩ | Look for solder bridges at U2 (QFN) and U1 |
| 3.7 V at J1 from a bench supply, 100 mA limit | 3V3 = 3.30 V ± 2 % | Check U4 orientation |
| Flash through the USB-C flash tab (no battery needed, no buttons) | `idf.py flash monitor` boots; the 3V3 rail reads 3.30 V from USB | Check J2 solder joints, the CC resistors (R27–R30) and U6 |
| Snap off the flash tab (no filing) | Stub ≤ 0.6 mm; no copper burr bridging the 4 cut inner-layer traces (look at the edge with a loupe) | Trim a burr with a knife; only file if the stub is over 0.6 mm |
| Idle current in deep sleep, dry, off the charger | **≤ 60 µA** (budget 40 µA) | Check that GPIO12 is low (TMP117 rail off) and nothing back-feeds through SDA/SCL |

## 2. Touch electrodes (in the closed enclosure)
| Check | Pass | Tunable |
|---|---|---|
| Raw counts, dry, all 7 channels | Stable within ±0.5 % over 1 min | `TOUCH_PAD_SHIELD_DRV_L2` in `sense_touch.c`: raise it if the shield load is higher than expected (counts unstable or very low) |
| Lower into water in 5 mm steps, log `level`, `top pad` against the ruler | Each pad gains ≥ 15 % when fully covered. Level within ±2 mm after one fill | `LVL_FRINGE_MM` (level.h) is the fixed offset: set it to the mean error |
| Spray water on the dry wall above the waterline | The level does not move by more than one pad and settles within 30 s | If worse: confirm idle channels are HIGHZ. Compare `TOUCH_PAD_CONN_GND` to see the difference |
| Repeat with salty water (1 tsp per litre) | As above | Raise `LVL_WET_FRAC` / `LVL_CHAIN_FRAC` if films chain up |
| Deep-sleep wake: lower until the wake pad (PAD1, or PAD2 with the FDC1004 fitted) is half covered | Wakes within 1 s | `lvl_wake_threshold()` factor (0.5) and `touch_pad_sleep_channel_set_work_time` |
| FDC1004 (if fitted): the boot log says `FDC1004 fitted`. In `compare` mode the dry `pf1..pf4` are steady to ±0.01 pF and CAPDAC settles | Each covered pad gains ≥ 3 pF | CAPDAC auto-range in `fdc1004.c`. Then run the protocol in [sensing-options.md](sensing-options.md) |

## 3. Temperature
| Check | Pass |
|---|---|
| Container at 30 / 37 / 40 / 45 °C, compare with the reference thermometer after 3 min | ±0.3 °C (sensor ±0.1 °C plus the wall gradient) |
| Step from 25 °C to 40 °C water: time to within 0.3 °C | ≤ 3 min (estimate 60–90 s time constant). If slower: thinner gap pad, check the pad covers the window |

## 4. Wireless charging (BQ51050B + TDK WR303050-12F5-ID)
| Check | Pass | Tunable |
|---|---|---|
| Coil inductance with the plug's back wall on a Qi transmitter (Ls′) and in free air (Ls) | Ls′ ≈ 8.2 µH | C_s = 1 / ((2π·100 kHz)² · Ls′): today 3 × 100 nF + 10 nF. C_d = 1 / ((2π·1 MHz)² · Ls − 1/C_s): today 3.3 nF |
| Charges on 3 different Qi pads (LED on, CHG_N low) | Starts within 5 s on each | Re-tune C_s, C_d. Check that the coil is centred under the Qi ring |
| Charge current (ammeter in series with the battery) | 230–290 mA (set 262 mA) | R1 (ILIM). Below the characterised range: TI E2E says accuracy is reduced |
| **Charge termination** at 4.2 V | Current tapers, CHG_N goes high, transmitter stops. Never ends on the 10 h timer | R3 (TERM, 10k → ~109 mA). If it fails to terminate: 4.7k (≈ 52 mA) or wire TERM to the firmware |
| Coil and battery temperature while charging (sealed enclosure, 25 °C room) | < 45 °C | Lower the charge current (raise R1) |
| Foreign-object detection | No false FOD trips on any pad | R_FOD (R2, 196R) per TI's FOD calibration procedure |

## 5. Radio and notifications
| Check | Pass |
|---|---|
| RSSI with the device in the bracket in the real tub (water filled to the alarm level) | ≥ −80 dBm |
| ntfy: fill a container past pad 6 | iPhone gets "Bath nearly full" then "BATH FULL", plus repeats while still filling, stopping when the "tap" stops |
| Wi-Fi off during a fill | Alarm is retried and logged; nothing crashes |

## 6. Power budget
| Check | Pass |
|---|---|
| Deep sleep, dry | ≤ 60 µA |
| Charge used by a 25 min simulated bath (PPK2) | ≤ 5 mAh |
| Projected life on 500 mAh at one bath per day | ≥ 3 months |

## 7. Enclosure (print one cup + plug first)
| Check | Pass | Tunable |
|---|---|---|
| Measure bore and plug skirt / groove | Radial gap 1.05–1.25 mm with the O-ring fitted | `PLUG_CLR`, `GLAND_DEPTH` in `hardware/mech/enclosure.py` |
| Plug insertion force with grease | Pushes in by hand, does not back out unscrewed | Same |
| Vacuum bubble test (closed device in water under light vacuum) | No bubble stream | Groove finish, O-ring size (90 × 1.5 → 89 × 1.5) |
| 1 h at 0.5 m in 45 °C water, then 20 cycles 15 ↔ 45 °C | Humidity dot stays dry | |
| Bracket on the tub with the two suction cups, device in, 24 h with water | Stays put | `KEY_*` keyhole sizes for the cups you bought |

## 8. Full system
A real bath: wake on PAD1, notifications at the right time, temperature within 0.3 °C of the reference, sleep after
the tap is off, and a "drained" reset afterwards. Record any false alarm with its log.

## Known checks still open in the design
- **ERC:** KiCad 7's command line has no electrical rules check. Run *Inspect → Electrical Rules Checker* in the KiCad app
  (or kicad-cli 8+) once. `hardware/tools/verify_netlist.py` already proves the drawn wiring matches the intended netlist.
- **PCB routing:** see `docs/pcb-routing.md`.
