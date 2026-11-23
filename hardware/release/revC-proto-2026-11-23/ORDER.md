# brim rev C prototype order (2026-11-23)

## 1. JLCPCB: boards + assembly (`jlcpcb/`)
Upload `bath_monitor-gerbers.zip`, then for assembly `bom_jlc.csv` and `cpl_jlc.csv`.

| Option | Choose |
|---|---|
| Layers / thickness | 4 layers, **1.0 mm**, stackup JLC04101H-7628 |
| Solder mask / silkscreen | **White** / black |
| Surface finish | **ENIG** (0.4 mm-pitch DFN and LGA parts) |
| Via | 0.3 / 0.6 mm (standard) |
| Board qty / assembled qty | 5 / 5 (JLC minimum is 5 boards; assemble all, they're cheap insurance) |
| Assembly | Standard PCBA, **bottom side only** (all 67 placed parts are on the bottom) |
| Remove order number | "Specify a location" or "No" (there's no free silk area for it) |

**Check in the placement preview before paying** (KiCad and JLC sometimes differ by 90/180°): pin 1 / the dot of
U1 (ESP32 module, antenna must overhang the top edge), U2 BQ51050B, U5 FDC1004, U7 LIS2DW12, U9 AW2013,
D1 RGB LED, Q1, U4, U6 and J2 (USB-C opening facing the tab's outer edge). Fix any wrong one with
`ROT_FIX` in `tools/jlc_outputs.py` and regenerate, or rotate it in JLC's editor.
Not assembled (hand fitted): battery, Qi coil (L1), piezo (BZ1), electrodes are copper only.

## 2. JLC3DP: enclosure (`jlc3dp/`)
`cup.stl`, `plug.stl`, `bracket.stl`, one set per device (order 3 sets).
Cup and plug: **SLA resin, a translucent/clear grade** so the status light shows through. Bracket: any resin or MJF.
Resin units are test units only (not rated for long skin contact): see docs/enclosure.md §2.3.

## 3. Hand parts (`bom_hand_parts.csv`, docs/bom-hand-parts.md)
Amazon (battery, O-ring, suction cups, Qi pads), Digi-Key (coil, piezo, thermal pad, grease, humidity cards),
McMaster (screws, foam). Pick the exact Amazon listings: O-ring must be **90 mm ID × 1.5 mm cross-section**.

## 4. Before the boards arrive
- Install ESP-IDF **v5.3.6** (older versions carry known Mbed TLS CVEs).
- Read docs/bring-up.md: first flash through the USB tab, then charging, sensing and leak tests.
