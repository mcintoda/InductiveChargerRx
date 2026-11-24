# PCB routing and JLC order files

The board is fully routed (rev C). `hardware/kicad/bath_monitor.kicad_pcb` is now the source of truth for placement
and copper: schematic changes are carried into it, never regenerated from scratch.

## Day-to-day pipeline
```
python3 hardware/tools/gen_schematic.py && python3 hardware/tools/verify_netlist.py
python3 hardware/tools/sync_pcb.py            # carry schematic changes into the routed board (values, nets, new parts)
python3 hardware/tools/fixroute.py            # only if sync_pcb added parts: route them, DRC-checked
python3 hardware/tools/acid_traps.py hardware/kicad/bath_monitor.kicad_pcb   # copper notches < 90 deg (expect 1: a GND thermal corner)
python3 hardware/tools/jlc_outputs.py         # hardware/fab: gerbers zip, bom_jlc.csv, cpl_jlc.csv (FDC1004 build;
                                              #   --variant=touch or --variant=both, see docs/sensing-options.md)
```

## Copper clean-up after routing (done once for rev C, 2026-11-24)
The grid router leaves 0.05 mm staircases, dead-end stubs, copper joined only by overlap and acute notches
(etchant traps). After any re-route, run, in this order:
```
python3 hardware/tools/tidy_board.py hardware/kicad/bath_monitor.kicad_pcb    # joints, stubs, loops, staircases
python3 hardware/tools/hand_fixes_revC.py hardware/kicad/bath_monitor.kicad_pcb   # 5 spots tidy can't reach (rev C only)
python3 hardware/tools/fillet_notches.py hardware/kicad/bath_monitor.kicad_pcb    # fill every notch < 90 deg
```
- `tidy_board.py` drives `tidy_tracks.py` per net and layer. Steps:
  - join copper that only touched by overlap;
  - prune dead ends and dead vias;
  - cut loops;
  - straighten staircases.

  A DRC runs after each pass. Any net/layer that gains an error steps down a level (less straightening),
  so the result never has more errors than the input. It is deterministic; run it once, on the routed board.
- `hand_fixes_revC.py` replaces 5 slanted pad entries and router clusters (U7 +3V3 ×2, ILIM, FDC_CIN2, ACC_INT)
  with square ones. It matches exact segments of tidy's output and stops if they're missing.
- `fillet_notches.py` measures the real copper outline (tracks, pads, vias and zones merged per net, `acid_traps.py`).
  A short track across the mouth of each notch under 90° makes both new corners 90° + θ/2. Any fillet that causes a
  DRC error is retried at 0.15 mm, then dropped.

Rev C result:
- 1631 → 1130 track segments, including 94 fillets. Short segments (< 0.1 mm): 621 → 6.
- Copper notches under 90°: 98 → 1. The one left is the GND zone's thermal relief at U7 pad 7.
- 0 dangling tracks or vias, 0 unconnected, netlist MATCH.

## How the board was first built (from scratch)
`gen_pcb.py` (placement) → `route.py prep` (electrode lanes, TMP117 bus, thermal vias, DSN for an autorouter) →
`fixroute.py` (grid router used in place of Freerouting) → `route.py finish` steps (GND stitching, zone refill, DRC).
Re-running this replaces the hand-locked routing, so only do it for a new board revision.

## What `route.py prep` already does
- **Electrode lanes:** a via inside each of the 7 electrodes, then a straight 0.2 mm lane on B.Cu up to the electronics
  band. B.Cu sits behind the hatched In1 SHIELD, so the lanes are shielded from the water.
- **TMP117 bus and NTC:** straight B.Cu lanes through the electrode band to the thermal tab and to TH1.
- **Thermal vias** under the BQ51050B exposed pad and the ESP32 module's ground pads (0.3 mm drill, JLC standard).
- **Autorouter constraints** (in the DSN only):
  - keep-out over the whole electrode band;
  - In1/In2 marked as planes, so they stay unbroken GND / SHIELD;
  - hand routing marked *protected*.

## The autoroute
Freerouting (open source) reads the DSN and writes the SES. Any of these works:

1. **KiCad app:** File → Export → Specctra DSN is already done. Open `hardware/kicad/route/bath_monitor.dsn` in
   Freerouting (GUI), click *Autorouter*, then *File → Export Specctra Session File* to `bath_monitor.ses`.
2. **Command line:** `java -jar freerouting.jar -de hardware/kicad/route/bath_monitor.dsn -do hardware/kicad/route/bath_monitor.ses -mp 30`
3. **Claude:** approve running the Freerouting jar in this environment, and the whole pipeline runs end to end.
   This is the step that was paused: it needs you to OK executing a downloaded program.

Then run `route.py finish`. Pass criteria: DRC with **0 unconnected items, 0 clearance errors**. Silkscreen
warnings are cosmetic.

## Status (2026-11-22, rev C): fully routed

![Copper layers F.Cu / In2 / B.Cu](img/pcb-routed-layers.png)

`hardware/kicad/bath_monitor.kicad_pcb` is routed: **0 unconnected, 0 clearance / hole / edge errors**
(six short dead-end stubs remain as DRC warnings, harmless). The pad connectivity matches the schematic netlist (60 nets; the TMP117 exposed pad is
tied to GND, which the symbol has no pin for). The only DRC items left are cosmetic warnings: silkscreen
overlaps and silk clipped by mask or edge (back silk only carries designators), plus `lib_footprint_issues`
because the footprints are embedded rather than read from a library.

How it got there:

1. Freerouting 1.9 (`route.py prep` / `finish` / `again`, run under `xvfb-run`) does the bulk.
2. `tools/fixroute.py` is a small grid A* router (F.Cu / In2 / B.Cu, DRC-driven). It reroutes what is left,
   does transactional rip-up (kept only if the DRC score improves), adds GND island vias, and falls back to
   0.15 mm tracks in fine-pitch spots. Run it after any edit:
   `python3 hardware/tools/fixroute.py`.
3. A few spots were laid out by hand (locked tracks):
   - **FDC block.** R23 (PAD5) and R24 (PAD6) drop straight down on B.Cu to a via inside their own
     electrodes E5 / E6, so no long detours are needed. U5 pin 7 GND reaches In1 through a small GND
     tongue cut into the shield plane above the REF electrode. No vias are allowed over E8 (REF) except
     REF's own.
   - **U2 right-side fan-out.** Pins 4–6 (VBAT, CLAMP1, COMM1) fan out to staggered vias. VBAT then joins
     its In2 run.
   - **R5 / R28 GND.** Each has its own GND via. The RECT and TAB_CC2 links were moved off them.
   - **TMP117.** GND vias in the exposed pad and beside it tie the split B.Cu pour through F.Cu.
   - **Right F.Cu shield strip.** Two vias tie it to the In1 shield plane.
   - **Rev C parts** (accelerometer U7, LED driver U9 + RGB LED D1, piezo pads BZ1) were added to the routed
     board with `tools/sync_pcb.py` (no re-generation, so the routing above is kept), then routed by fixroute
     plus a few locked hand tracks: the LED corner (AW2013 channels LED0/1/2 = green/blue/red to fit the
     pads), a GND via inside U7's 2 x 2 mm footprint for its ground pads, and two SDA bridges.

All 207 vias are JLC-standard 0.6 / 0.3 mm (the board rules enforce a 0.3 mm minimum drill). The minimum
track is 0.15 mm; the default is 0.2 mm.

Then `python3 hardware/tools/jlc_outputs.py` writes `hardware/fab/` (gerbers zip, `bom_jlc.csv`,
`cpl_jlc.csv`). The folder is git-ignored, so regenerate it before ordering.

## Order settings at JLCPCB
| Option | Value |
|---|---|
| Layers / thickness | 4 / 1.0 mm, stackup JLC04101H-7628 |
| Solder mask / silkscreen | **White** / black (the electrodes show through the translucent case) |
| Surface finish | ENIG |
| Min via | 0.3 / 0.6 mm (standard, no extra cost) |
| Assembly | **Bottom side**, standard PCBA, files `bom_jlc.csv` + `cpl_jlc.csv` |
| Not assembled | Electrodes (copper), test pads, battery and Qi coil (hand-soldered) |

Check the rotations in JLC's placement preview. KiCad and JLC sometimes disagree by 90/180° per footprint. Fix them in
`ROT_FIX` in `jlc_outputs.py`. All LCSC numbers in `hardware/lcsc_parts.csv` were checked against lcsc.com on 2026-11-22. Earlier, parts marked *verify* were well-known JLC Basic numbers
that weren't confirmed by search in this session: check them on the order page.
