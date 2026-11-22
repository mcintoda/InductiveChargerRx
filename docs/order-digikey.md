# Digi-Key order: parts JLC does not assemble

JLC builds the PCB with every SMD part on it (`hardware/fab/bom_jlc.csv`). These are the hand-fitted parts and the
enclosure consumables. Quantities are for **3 prototype builds** plus spares.

Upload [`hardware/digikey_bom.csv`](../hardware/digikey_bom.csv) to Digi-Key's BOM Manager (it matches on the
manufacturer part number where the Digi-Key number is blank), or add the lines by hand.

| Qty | Part | Manufacturer / MPN | Digi-Key # | ~US$ each | Fits where |
|---|---|---|---|---|---|
| 4 | Qi receiver coil, 30 mm, 8.23 µH | TDK **WR303050-12F5-ID** | [product page](https://www.digikey.com/en/products/detail/tdk-corporation/WR303050-12F5-ID/6124579) | 4.2–4.5 | Behind the battery, leads to L1 |
| 3 | LiPo 3.7 V 500 mAh, protected, 29 × 36 × 4.75 mm | Adafruit **1578** | [1528-1841-ND](https://www.digikey.com/en/products/detail/adafruit-industries-llc/1578/5054539) | ~8 | Behind the electrodes, wires to J1 (**see battery note**) |
| 5 | Piezo bender, 20 mm, 6.3 kHz, wire leads | PUI Audio **AB2063B-2-LW50** | [product page](https://www.digikey.com/en/products/detail/pui-audio-inc/AB2063B-2-LW50/22535104) | 0.66 | Bonded inside the plug, leads to BZ1 |
| 1 | Thermal gap pad, 40 × 40 × 0.5 mm | t-Global **TG-A1660-40-40-0.5** | [1168-TG-A1660-40-40-0.5-ND](https://www.digikey.com/en/products/detail/t-global-technology/TG-A1660-40-40-0-5/11617038) | ~8 | Cut 10 × 7 mm: TMP117 tab to thermal window |
| 1 | Silicone grease, 85 ml | MG Chemicals **8462-85ML** | [473-1232-ND](https://www.digikey.com/en/products/detail/mg-chemicals/8462-85ML/6035523) | ~10 | Thin film on the O-ring |
| 1 | Humidity indicator cards (can) | SCS **3HIC125** | [SCP667-ND](https://www.digikey.com/product-detail/en/scs/3HIC125/SCP667-ND/1621628) | ~20 / can | One spot inside the cup |

## Battery note (decide before printing the enclosure)
The enclosure is sized for a **403040 cell: 4.0 × 30 × 40 mm**. Digi-Key doesn't stock one. The options:

| Option | Size | Change needed |
|---|---|---|
| **Adafruit 1578** (listed above) | 4.75 × 29 × 36 mm, 500 mAh, protected, JST-PH plug | Case 0.8 mm deeper (10.1 → 10.9 mm): one parameter (`BATT_T`) in `hardware/mech/enclosure.py`, then regenerate |
| Jauch LP503040JH+PCM, [1908-LP503040JH+PCM+2WIRES50MM-ND](https://www.digikey.com/en/products/detail/jauch-quartz/LP503040JH-PCM-2-WIRES-50MM/9560983) | 5.4 × 30.5 × 42 mm, 600 mAh, protected, bare wires | Case 1.4 mm deeper and 2 mm longer in the battery bay |
| A true 403040 500 mAh protected cell from a battery shop / marketplace | 4.0 × 30 × 40 mm | None |

Whichever you pick: the cell must have its **own protection module (PCM)**. Temperature comes from TH1 on the PCB,
so any 2-wire cell works. Cut a JST plug off and solder the wires to J1 (red = pin 1).

## Not on Digi-Key (order elsewhere)
| Qty | Part | Where |
|---|---|---|
| 5 | O-ring **90 × 1.5 mm, EPDM 70 Shore A** (metric) | McMaster-Carr, an O-ring specialist, or a metric EPDM O-ring kit. Digi-Key only stocks AS568 inch sizes |
| 12 | Screw **M2 × 4 mm, A4 (316) stainless, thread-forming for plastic (PT/plastite), flat head** | McMaster-Carr or a fastener shop. Digi-Key's M2 stainless flat heads (NBK SETS-M2-4) are machine screws, so they'd need tapped holes |
| 1 | PORON urethane foam, 1.6 mm (1/16") sheet | McMaster-Carr / Rogers distributors. Cut Ø30 mm discs behind the coil |
| 1 pack | Suction cups, 40 mm mushroom head | Bambu Lab HA011 (see `docs/enclosure.md` §2.7) |

Also needed: the enclosure prints (`hardware/mech/out/`, JLC3DP) and a USB-C cable for the first flash.
