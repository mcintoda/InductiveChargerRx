# Parts order: everything JLC does not assemble

JLC builds the PCB with every SMD part on it (`hardware/fab/bom_jlc.csv`). These are the hand-fitted parts and the
enclosure consumables. Quantities are for **3 prototype builds** plus spares.

**Digi-Key:** upload [`hardware/digikey_bom.csv`](../hardware/digikey_bom.csv) to Digi-Key's BOM Manager (it matches on the
manufacturer part number where the Digi-Key number is blank), or add the lines by hand.

| Qty | Part | Manufacturer / MPN | Digi-Key # | ~US$ each | Fits where |
|---|---|---|---|---|---|
| 4 | Qi receiver coil, 30 mm, 8.23 µH | TDK **WR303050-12F5-ID** | [product page](https://www.digikey.com/en/products/detail/tdk-corporation/WR303050-12F5-ID/6124579) | 4.2–4.5 | Behind the battery, leads to L1 |
| 5 | Piezo bender, 20 mm, 6.3 kHz, wire leads | PUI Audio **AB2063B-2-LW50** | [product page](https://www.digikey.com/en/products/detail/pui-audio-inc/AB2063B-2-LW50/22535104) | 0.66 | Bonded inside the plug, leads to BZ1 |
| 1 | Thermal gap pad, 40 × 40 × 0.5 mm | t-Global **TG-A1660-40-40-0.5** | [1168-TG-A1660-40-40-0.5-ND](https://www.digikey.com/en/products/detail/t-global-technology/TG-A1660-40-40-0-5/11617038) | ~8 | Cut 10 × 7 mm: TMP117 tab to thermal window |
| 1 | Silicone grease, 85 ml | MG Chemicals **8462-85ML** | [473-1232-ND](https://www.digikey.com/en/products/detail/mg-chemicals/8462-85ML/6035523) | ~10 | Thin film on the O-ring |
| 1 | Humidity indicator cards (can) | SCS **3HIC125** | [SCP667-ND](https://www.digikey.com/product-detail/en/scs/3HIC125/SCP667-ND/1621628) | ~20 / can | One spot inside the cup |

## Battery: buy a true 403040 on Amazon (no case change)
The enclosure is sized for a **403040 cell: 4.0 × 30 × 40 mm**, and Amazon has them. The cell must have its
**own protection module (PCM)**: temperature comes from TH1 on the PCB, so any protected 2-wire cell works.

| Qty | Listing | Notes |
|---|---|---|
| 3 | **achard 403040 500 mAh** ([B0CHBGZ778](https://www.amazon.com/Polymer-Rechargeable-Battery-Bracelet-403040-500mah/dp/B0CHBGZ778)) | Listing states a built-in protection PCB (over-charge, over-discharge, over-current, short). **Recommended** |
| (alt) | Liter Energy 403040 500 mAh with JST ([B09FLYNRPG](https://www.amazon.com/Liter-energybattery-Battery-Rechargeable-Connector/dp/B09FLYNRPG)) | JST plug: cut off and solder to J1. Check the polarity, as the listing warns |
| (alt) | HXJNLDC 403040 500 mAh, 2 wires ([B0CHYS7XFV](https://www.amazon.com/HXJNLDC-Rechargeable-Lithium-Polymer-Electronic/dp/B0CHYS7XFV)) | Listed as 41 × 30 × 4 mm: 1 mm longer than the nominal size, which still fits the bay. Confirm it has a PCM |

Marketplace cells vary: check thickness (≤ 4.2 mm), that a PCM board is under the tape, and polarity before
soldering (red = J1 pin 1). If you'd rather buy from Digi-Key: Adafruit **1578** (1528-1841-ND, 4.75 × 29 × 36 mm,
protected) fits once the case is 0.8 mm deeper (`BATT_T` in `hardware/mech/enclosure.py`).

## Not on Digi-Key / Mouser / Amazon (specialist suppliers)
| Qty | Part | Where |
|---|---|---|
| 5 | O-ring **90 × 1.5 mm**, ideally EPDM 70 Shore A | No EPDM ring in this exact size turned up at Digi-Key, Mouser or Amazon. Good alternatives in the exact size: **Tameson FKM 90 × 1.5 mm, 80 Sh A, 5 pcs** ([S26DT](https://tameson.com/products/s26dt-x5-fkm-o-ring-90-x-1p5mm-od-93mm-80-shore-a-5-pieces)) or **NBR 90 × 1.5 mm, 70 Sh A** ([Tameson S26DS, 20 pcs](https://tameson.com/products/s26ds-x20-nbr-o-ring-90-x-1p5mm-od-93mm-70-shore-a-20-pieces) / [Mutual Screw, 40 pcs](https://mutualscrew.com/products/1-5-mm-c-s-x-90-mm-id-buna-70-5-pk-with-cert-in-each-pack_zmush1-5x90b5)). FKM and NBR both handle 45 °C soapy water; FKM is the better of the two |
| 12 | Screw, thread-forming for plastic, flat head, stainless, ~M2 × 4 mm | McMaster-Carr: "Flat Head Thread-Forming Screws for Plastic", 18-8 stainless, **M2.2 × 4 mm**. That is 18-8, not A4, which is fine for tap water. M2.2 needs the case's clearance hole opened from 2.3 to 2.5 mm and the pilot from 1.6 to 1.8 mm (`SCREW_CLEAR` / `SCREW_PILOT` in `enclosure.py`) |
| 1 | PORON microcellular urethane, 1/16" (1.6 mm) | Zoro "Foam Sheet, Microcellular, 12 × 12 in, 1/16 in" ([G1984851](https://www.zoro.com/zoro-select-foam-sheet-microcellular-12-in-w-12-in-l-116-in-thick-black-zusa-mcp-101/i/G1984851)) or McMaster-Carr Poron. Cut Ø30 mm discs |
| 1 pack | Suction cups, 40 mm mushroom head | Bambu Lab HA011 (see `docs/enclosure.md` §2.7), also sold on Amazon |

## Mouser equivalents
If you'd rather order from Mouser, the coil is **810-WR303050-12F5-ID**. Mouser didn't show a stocked listing for
the PUI piezo (AB2063B-2-LW50), so get that one from Digi-Key.

Also needed: the enclosure prints (`hardware/mech/out/`, JLC3DP) and a USB-C cable for the first flash.
