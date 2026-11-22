# BOM: parts JLC does not supply

One list for everything that is not on the JLC assembly BOM (`hardware/fab/bom_jlc.csv`): the hand-fitted parts and
the enclosure consumables. Quantities cover **3 prototype builds** plus spares. The source of truth is
[`hardware/bom_hand_parts.csv`](../hardware/bom_hand_parts.csv) (open it in a spreadsheet, or upload the Digi-Key
rows to Digi-Key's BOM Manager, which matches on the manufacturer part number).

| # | Qty | Part | MPN | Supplier | Supplier # | ~US$ | Where / notes |
|---|---|---|---|---|---|---|---|
| 1 | 3 | LiPo cell 3.7 V 320 mAh (300 mAh min), 25.5 x 36 x 4.3 mm, protection PCM (overcharge, overdischarge, overcurrent, short), 2 wires, ~6 g | 320 mAh 253643-size LiPo (your Amazon listing) | Amazon | the listing you found | ~6 | Behind the electrodes, wires to J1 (red = pin 1). Cut off the plug and solder: J1 is pads, not a connector, so plug model and size don't matter, only polarity. Check on arrival: <= 4.4 mm thick, PCM under the tape |
| 2 | 4 | Qi receiver coil 30 x 29.6 x 0.9 mm, 8.23 uH | TDK WR303050-12F5-ID | Digi-Key | [link](https://www.digikey.com/en/products/detail/tdk-corporation/WR303050-12F5-ID/6124579) | 4.5 | Behind the battery, leads to L1. Also Mouser 810-WR303050-12F5-ID |
| 3 | 5 | Piezo bender 20 mm, 6.3 kHz, wire leads | PUI Audio AB2063B-2-LW50 | Digi-Key | [link](https://www.digikey.com/en/products/detail/pui-audio-inc/AB2063B-2-LW50/22535104) | 0.66 | Bonded (cyanoacrylate) inside the plug at PCB (19, 23.5), leads to BZ1 |
| 4 | 1 | Thermal gap pad 40 x 40 x 0.5 mm, 16.6 W/m-K | t-Global Technology TG-A1660-40-40-0.5 | Digi-Key | [1168-TG-A1660-40-40-0.5-ND](https://www.digikey.com/en/products/detail/t-global-technology/TG-A1660-40-40-0-5/11617038) | 8 | Cut 10 x 7 mm pieces: TMP117 tab to the thermal window |
| 5 | 1 | Silicone grease, 85 ml | MG Chemicals 8462-85ML | Digi-Key | [473-1232-ND](https://www.digikey.com/en/products/detail/mg-chemicals/8462-85ML/6035523) | 10 | Thin film on the O-ring |
| 6 | 1 | Humidity indicator cards, 3-spot (can of 125) | SCS 3HIC125 | Digi-Key | [SCP667-ND](https://www.digikey.com/product-detail/en/scs/3HIC125/SCP667-ND/1621628) | 20 | Cut one spot, stick it inside the cup as the leak indicator |
| 7 | 1 | O-ring 90 x 1.5 mm, FKM 80 Shore A (pack of 5) | Tameson S26DT-X5 | Tameson | [S26DT-X5](https://tameson.com/products/s26dt-x5-fkm-o-ring-90-x-1p5mm-od-93mm-80-shore-a-5-pieces) | 8 | Plug groove. EPDM 70 Sh A is ideal but not found in this size; NBR alternative: Tameson S26DS-X20 |
| 8 | 1 | Screw, flat head, thread-forming for plastic, 18-8 stainless, Torx drive, M2 x 6 mm (pack of 50; 4 per device) | McMaster-Carr 95893A165 | McMaster-Carr | [95893A165](https://www.mcmaster.com/95893A165/) | 13.33 | Side walls into the plug, 4 per device. Fits the existing M2 holes (2.3 mm clearance, 1.6 mm pilot). The tip reaches 1.5 mm past the plug skirt, 0.9 mm clear of the coil: checked in fit_and_render.py |
| 9 | 1 | Microcellular urethane (PORON-type) foam sheet, 1/16 in, 12 x 12 in | Zoro Select ZUSA-MCP-101 | Zoro | [G1984851](https://www.zoro.com/zoro-select-foam-sheet-microcellular-12-in-w-12-in-l-116-in-thick-black-zusa-mcp-101/i/G1984851) | 17 | Cut 30 mm discs: between the coil and the plug |
| 10 | 1 | Suction cups 40 mm, mushroom head (pack of 10) | Bambu Lab HA011 | Bambu Lab store / Amazon | [HA011](https://us.store.bambulab.com/products/suction-caps-with-mushroom-head) | 2 | Bracket keyholes, 2 per device (docs/enclosure.md 2.7) |

Approximate total for the list: **about US$118** plus shipping. Prices are search snapshots: check them in the cart.

## Before ordering
- **Battery:** marketplace cells vary. On arrival check thickness (≤ 4.4 mm), that a protection board sits under the tape, and polarity (red to J1 pin 1). Cut the connector off and solder the wires to J1, so the listing's connector model, size and polarity warnings don't apply, as long as red goes to pin 1. The case is sized for 25.5 × 36 × 4.3 mm, with room for +10 % swelling (see enclosure.md).
- **Screws:** McMaster 95893A165 (M2 x 6 mm, 18-8, Torx, thread-forming for plastic, pack of 50). They fit the case's existing M2 holes.
- **O-ring:** FKM in the exact 90 × 1.5 mm size. EPDM would be ideal but was not found in that size.

Not in this list: the PCB and its SMD parts (JLC PCBA), the enclosure prints (`hardware/mech/out/`, JLC3DP), and a USB-C cable for the first flash.
