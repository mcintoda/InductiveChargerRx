# Bath Monitor

A sealed, Qi-charged sensor that suction-mounts in the bathtub. It sends a
notification to your iPhone (over Wi-Fi, no pairing) before the bath
overflows, and reports the water temperature.

- **Level:** a 6-pad capacitive ladder that senses through the enclosure wall (non-contact)
- **Temperature:** TMP117, ±0.1 °C
- **Radio:** ESP32-S3 Wi-Fi → free ntfy push notifications (iOS app)
- **Power:** ~500 mAh Li-ion, BQ51050B Qi receiver/charger, ~6 months per charge (estimate)
- **Build:** JLCPCB 4-layer PCB + SMT assembly, JLC3DP enclosure

- [`docs/design.md`](docs/design.md): requirements, architecture, power budget, mechanics, firmware behaviour
- [`hardware/kicad/`](hardware/kicad/): KiCad 7 project (schematic rev A)
- [`hardware/bom_jlc.csv`](hardware/bom_jlc.csv): JLCPCB assembly BOM (generated; LCSC numbers still to be filled)
- [`hardware/tools/gen_schematic.py`](hardware/tools/gen_schematic.py): regenerates the schematic and BOM

```
python3 hardware/tools/gen_schematic.py    # needs KiCad 7+ symbol libraries
```
