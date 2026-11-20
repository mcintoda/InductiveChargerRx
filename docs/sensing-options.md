# Level sensing options: touch vs FDC1004

Rev B can be built three ways from the same PCB. The only difference is which 0R / 1k links are fitted.
That lets us measure the options side by side on the bench before we settle on one for production.

| Option | What measures | Firmware mode | Strength | Weakness |
|---|---|---|---|---|
| **A. Touch, learned** | ESP32-S3 touch, 7 pads, driven shield | `touch` with `ratiometric = false` | No extra parts | Everything that scales the wet signal (return path, person in the bath, conductivity) reads as level error. Simulated worst case 7.9 mm at ×0.85 coupling |
| **B. Touch, ratiometric** (default) | Same hardware | `touch` | Live reference: a covered pad below divides out the common scale. 1.8 mm worst case at every coupling scale | Needs one fully covered pad below the one being read. Relies on pad-to-pad gain learned in earlier baths |
| **C. FDC1004** | FDC1004 on PAD1 (reference liquid), PAD5, PAD6 (alarm region) and REF (environment), with its own shield driver | `fdc` | TI's 3-electrode scheme in hardware, femtofarad resolution, 24-bit. 1.6 mm worst case at every coupling scale | +1 IC (~US$3 at LCSC) and 750 µA while measuring. Only sees 40–60 mm, plus "PAD1 covered". Shares the pads with the touch peripheral |

The simulation results come from `firmware/test/test_logic.c`, which runs with `make -C firmware/test`. They are model numbers. The bench decides.

## Board variants (one PCB)

Touch series resistors: R11–R16 (PAD1–PAD6), R20 (REF), R17 (shield drive).
FDC links: R22 (PAD1→CIN1), R23 (PAD5→CIN2), R24 (PAD6→CIN3), R25 (REF→CIN4), R26 (shield→SHLD1).

| Variant | Fit | Do not fit | Wake pad |
|---|---|---|---|
| Touch only (production candidate A/B) | R11–R17, R20 | U5, C24, C25, R22–R26 | PAD1 |
| FDC only (production candidate C) | U5, C24, C25, R22–R26, R12–R14 (PAD2–4 stay on touch for wake) | R11, R15, R16, R17, R20 | PAD2 |
| Both (bench comparison) | everything | — | PAD2 |

The firmware probes for the FDC1004 at 0x50 on the first boot. If it answers, it:

- **wakes on PAD2**. With the sensor rail off, the FDC's input ESD diodes clamp PAD1's touch signal.
- **keeps the sensor rail on** whenever it is awake, for the same reason.
- **interleaves the two converters**. The touch FSM is paused while the FDC converts (`sense_pause`/`sense_resume`), so the two never drive the pads at the same time.

On the "both" board each converter still sees the other's input capacitance as a fixed load on the shared pads. The baselines absorb it, but the absolute sensitivities are a little lower than on single-option boards. Use the "both" board to compare behaviour (drift, films, return path, noise) on identical water. Confirm the final choice on a single-option board.

### Choosing the mode

Choose the mode on the settings page (charger mode, *Level sensing*):

- `touch`: production default.
- `fdc`: the policy is driven by the FDC. The alarm pad is limited to 5 or 6. Below 40 mm the level reads as "PAD1 covered" (9 mm).
- `compare`: alarms come from touch. Every 2 s sample is logged on the USB console as:

```
CMP,t,learned_mm,ratio_mm,fdc_mm,top_touch,top_fdc,drift,raw1..raw7,pf1..pf4
```

`fdc_mm = -1` means the level is below the FDC window. Capture the log with `idf.py monitor | grep CMP > run.csv`.

## Bench protocol

Use the "both" board in the closed enclosure on an acrylic test tank. Mark a ruler at 1 mm.

For each run:

1. log `compare` mode;
2. fill at about 5 mm/min (a typical bath);
3. note the true level every 5 mm;
4. hold at the alarm level for 5 minutes.

| # | Test | What it shows | Pass |
|---|---|---|---|
| 1 | Plain fill, tap water, tank grounded through the drain (metal waste) | Baseline accuracy | All three within ±3 mm over 40–60 mm |
| 2 | Same fill, tank floating (plastic waste, no return path) | Return-path sensitivity | B and C stay within ±3 mm. A is expected to degrade |
| 3 | Fill to 30 mm, then a person (or a 20 L bucket of water touching a hand) in the bath, then continue to 60 mm | Body coupling | Same as 2 |
| 4 | Salt water, 1 tsp/L, and bubble-bath foam | Conductivity and films | No early alarm. Level error within ±3 mm |
| 5 | Spray the dry wall above the waterline at 50 mm | Film rejection | No alarm. The reading settles within 30 s |
| 6 | Hot fill at 42 °C against 20 °C, wall warm-up over 30 min | Thermal drift | Dry REF tracking keeps the at-rest reading within ±2 mm |
| 7 | 30 min at constant level | Noise | 1σ < 0.5 mm per sample |
| 8 | Current, PPK2 on the battery | Energy | Awake average in each mode. The FDC adds roughly 4 × 10 ms × 750 µA per 2 s, about 15 µA average |
| 9 | Drain and repeat 5 baths without charger recalibration | Learning and drift | Bath 5 no worse than bath 1 |

## Decision

| If the bench shows… | Ship |
|---|---|
| B meets every pass line | **Touch only, ratiometric.** No FDC, no links: the cheapest and simplest board |
| B fails 2 or 3 and C passes | **FDC only.** Accept the extra part. Touch stays only as the wake-up on PAD2 |
| B fails 4/5 (films) and C passes | FDC, but first try raising `LVL_CHAIN_FRAC` and the shield drive level on touch |
| Both fail 2/3 | A grounding strip against the water is not allowed (body-safe, no wet contacts). Revisit the electrode geometry instead: wider REF and PAD1, smaller gap to the wall |

Record the results and the decision in `docs/design.md`.

## Sources

- TI FDC1004 datasheet (registers, CAPDAC, 3-electrode liquid-level scheme): https://www.ti.com/lit/ds/symlink/fdc1004.pdf
- LCSC FDC1004DGSR, C2865994: https://www.lcsc.com/product-detail/C2865994.html
