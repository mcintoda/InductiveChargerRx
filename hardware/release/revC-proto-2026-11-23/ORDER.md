# brim rev C prototype order (2026-11-23)

## 1. JLCPCB: boards + assembly (`jlcpcb/`)
Two orders with the same `bath_monitor-gerbers.zip`, so both sensing methods are on the bench side by side
(docs/sensing-options.md):

| Order | BOM + CPL | Boards / assembled |
|---|---|---|
| A, FDC1004 sensing (default) | `fdc/bom_jlc.csv`, `fdc/cpl_jlc.csv` | 5 / 3 |
| B, touch sensing | `touch/bom_jlc.csv`, `touch/cpl_jlc.csv` | 5 / 2 |

One order only? Use A for all 5 and convert two by hand later (remove R22–R26, fit R11, R15–R17, R20: 0402).

| Option | Choose |
|---|---|
| Layers / thickness | 4 layers, **1.0 mm**, stackup JLC04101H-7628 |
| Solder mask / silkscreen | **White** / black |
| Surface finish | **ENIG** (0.4 mm-pitch DFN and LGA parts) |
| Via | 0.3 / 0.6 mm (standard) |
| Board qty / assembled qty | see the table above (JLC minimum is 5 boards per order) |
| Assembly | Standard PCBA, **bottom side only** (all 67 placed parts are on the bottom) |
| Remove order number | "Specify a location" or "No" (there's no free silk area for it) |

**Check in the placement preview before paying** (KiCad and JLC sometimes differ by 90/180°): pin 1 / the dot of
U1 (ESP32 module, antenna must overhang the top edge), U2 BQ51050B, U5 FDC1004, U7 LIS2DW12, U9 AW2013,
D1 RGB LED, Q1, U4, U6 and J2 (USB-C opening facing the tab's outer edge). Fix any wrong one with
`ROT_FIX` in `tools/jlc_outputs.py` and regenerate, or rotate it in JLC's editor.
Not assembled (hand fitted): battery, Qi coil (L1), piezo (BZ1), electrodes are copper only.

## 2. JLC3DP: enclosure (`jlc3dp/`)
`cup.stl`, `plug.stl`, `bracket.stl`, one set per device (order 3 sets), plus **one `plug_tight.stl` and one
`plug_loose.stl`** (O-ring squeeze 30 % / 17 % vs 22 % nominal) to bracket the print tolerance: fit whichever seals
with a firm push and passes the leak test, then set `GLAND_DEPTH` in `hardware/mech/enclosure.py` to match.
A cup on its own (no plug) is the open test cup for sensing on the bench.
Cup and plug: **SLA resin, a translucent/clear grade** so the status light shows through. Bracket: any resin or MJF.
Resin units are test units only (not rated for long skin contact): see docs/enclosure.md §2.3.

## 3. Hand parts (`bom_hand_parts.csv`, docs/bom-hand-parts.md)
Amazon (battery, O-ring, suction cups, Qi pads), Digi-Key (coil, piezo, thermal pad, grease, humidity cards),
McMaster (screws, foam). Pick the exact Amazon listings: O-ring must be **90 mm ID × 1.5 mm cross-section**.
Items 12–13 are spare capacitors and resistors for tuning the Qi receiver (C4, C23) and FOD (R2) on the bench.

## 4. Before the boards arrive
- Install ESP-IDF **v5.3.6** (older versions carry known Mbed TLS CVEs).
- Read docs/bring-up.md §0: each board is flashed **once** (`firmware/tools/flash_unit.py`: firmware + setup
  password in one pass), then all of bring-up runs on that image over the USB console. Keep the flash tab on until
  the electronics checks are done; after that, firmware updates go over Wi-Fi.
