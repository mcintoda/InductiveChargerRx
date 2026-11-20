# PCB routing and JLC order files

The board is placed and partly hand-routed. **One step remains: the autoroute of the dense electronics band.**

## Pipeline
```
python3 hardware/tools/gen_schematic.py && python3 hardware/tools/verify_netlist.py
python3 hardware/tools/route.py prep          # fresh placement + hand routing -> hardware/kicad/route/bath_monitor.dsn
<autoroute>                                   # bath_monitor.dsn -> bath_monitor.ses   (see below)
python3 hardware/tools/route.py finish        # import, GND stitching, zone refill, DRC report
python3 hardware/tools/jlc_outputs.py         # hardware/fab: gerbers zip, bom_jlc.csv, cpl_jlc.csv (FDC1004 build;
                                              #   --variant=touch or --variant=both, see docs/sensing-options.md)
```

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
`ROT_FIX` in `jlc_outputs.py`. Parts marked *verify* in `hardware/lcsc_parts.csv` are well-known JLC Basic numbers
that weren't confirmed by search in this session: check them on the order page.
