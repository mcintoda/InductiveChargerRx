<img src="docs/img/brand_logo.svg" alt="brim" height="64">

# brim: bath level monitor

A sealed, Qi-charged sensor that suction-mounts in the bathtub. It sends a
notification to your iPhone (over Wi-Fi, no pairing) before the bath
overflows, and reports the water temperature.

- **Level:** a 6-pad capacitive ladder that senses through the enclosure wall (non-contact)
- **Temperature:** TMP117, ±0.1 °C
- **Radio:** ESP32-S3 Wi-Fi → free ntfy push notifications (iOS app)
- **Power:** 320 mAh protected LiPo (25.5 × 36 × 4.3 mm), BQ51050B Qi receiver/charger at 143 mA, ~6 months per charge (estimate). Charges lying flat on any Qi pad, like a phone
- **Build:** JLCPCB 4-layer PCB + SMT assembly, JLC3DP enclosure

> Also in this repo: **[`squeeze/`](squeeze/README.md)**, a pair of hand-held pebbles that pass squeezes back and forth (separate project, reuses brim's Qi charger block).

- [`docs/design.md`](docs/design.md): requirements, architecture, power budget, mechanics, firmware behaviour
- [`docs/placement-and-electrodes.md`](docs/placement-and-electrodes.md): board placement study and electrode design (with field simulation)
- [`docs/sensing-options.md`](docs/sensing-options.md): touch vs FDC1004 level sensing: board variants, compare mode, bench protocol, decision rules
- [`docs/sensing-infographic.html`](docs/sensing-infographic.html): interactive explainer of how the level and temperature sensing work electrically
- [`docs/branding.md`](docs/branding.md): name, mark, palette, and the debossed design features on the enclosure
- [`docs/pcb-routing.md`](docs/pcb-routing.md): routing pipeline and JLC order settings
- [`docs/bring-up.md`](docs/bring-up.md): bench test plan for the first boards
- [`firmware/`](firmware/): ESP-IDF firmware (ESP32-S3) with host unit tests
- **Product requirements (system, hardware, software):** [`docs/requirements.md`](docs/requirements.md)
- **Product website (marketing page):** [`docs/site/index.html`](docs/site/index.html)
- **Security review (Wi-Fi, web, OTA):** [`docs/security.md`](docs/security.md); firmware SBOM and CVE check: [`docs/sbom/`](docs/sbom/README.md)
- **Quick start guide for users:** [`docs/quick-start.html`](docs/quick-start.html) (setup, mounting, alerts, charging, light legend)
- [`docs/enclosure.md`](docs/enclosure.md): watertight enclosure (O-ring, no epoxy) with CAD in [`hardware/mech/`](hardware/mech/)
- **Parts JLC does not supply:** [`docs/bom-hand-parts.md`](docs/bom-hand-parts.md) (one BOM, all suppliers; CSV: [`hardware/bom_hand_parts.csv`](hardware/bom_hand_parts.csv))
- **Schematic without KiCad:** [`docs/schematic.pdf`](docs/schematic.pdf) (zoomable, searchable) or [`docs/img/schematic.svg`](docs/img/schematic.svg) / [`.png`](docs/img/schematic.png) (shows in the browser)
- [`hardware/kicad/`](hardware/kicad/): KiCad 7 project (schematic rev C, routed 4-layer PCB)
- [`hardware/bom_jlc.csv`](hardware/bom_jlc.csv): JLCPCB assembly BOM (generated; LCSC numbers still to be filled)
- [`hardware/tools/gen_schematic.py`](hardware/tools/gen_schematic.py): regenerates the schematic and BOM
- [`hardware/tools/gen_pcb.py`](hardware/tools/gen_pcb.py) / [`electrode_sim.py`](hardware/tools/electrode_sim.py): placement-study PCB and electrode simulation
- [`hardware/tools/verify_netlist.py`](hardware/tools/verify_netlist.py): checks that the drawn wiring matches the intended netlist

```
python3 hardware/tools/gen_schematic.py    # needs KiCad 7+ symbol libraries; also refreshes docs/schematic.pdf/.svg/.png
python3 hardware/tools/verify_netlist.py   # needs kicad-cli
```
