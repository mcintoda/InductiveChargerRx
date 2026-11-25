# BOM: parts JLC does not supply

One list for everything that is not on the JLC assembly BOM (`hardware/fab/bom_jlc.csv`): the hand-fitted parts and
the enclosure consumables. Quantities cover **3 prototype builds** plus spares. The source of truth is
[`hardware/bom_hand_parts.csv`](../hardware/bom_hand_parts.csv) (open it in a spreadsheet, or upload the Digi-Key
rows to Digi-Key's BOM Manager, which matches on the manufacturer part number).

| # | Qty | Part | MPN | Supplier | Supplier # | ~US$ | Where / notes |
|---|---|---|---|---|---|---|---|
| 1 | 3 | LiPo cell 3.7 V 320 mAh (300 mAh min), 25.5 x 36 x 4.3 mm, protection PCM (overcharge, overdischarge, overcurrent, short), 2 wires, ~6 g | 320 mAh 25.5 × 36 × 4.3 mm LiPo | Amazon | [listing](https://a.co/d/00saOwxL) | ~6 | Behind the electrodes, wires to J1 (red = pin 1). Cut off the plug and solder: J1 is pads, not a connector, so plug model and size don't matter, only polarity. Check on arrival: <= 4.4 mm thick, PCM under the tape |
| 2 | 4 | Qi receiver coil 30 x 29.6 x 0.9 mm, 8.23 uH | TDK WR303050-12F5-ID | Digi-Key | [link](https://www.digikey.com/en/products/detail/tdk-corporation/WR303050-12F5-ID/6124579) | 4.5 | Behind the battery, leads to L1. Also Mouser 810-WR303050-12F5-ID |
| 3 | 5 | Piezo bender 20 mm, 6.3 kHz, wire leads | PUI Audio AB2063B-2-LW50 | Digi-Key | [link](https://www.digikey.com/en/products/detail/pui-audio-inc/AB2063B-2-LW50/22535104) | 0.66 | Bonded (cyanoacrylate) inside the plug at PCB (19, 23.5), leads to BZ1 |
| 4 | 1 | Thermal gap pad 40 x 40 x 0.5 mm, 16.6 W/m-K | t-Global Technology TG-A1660-40-40-0.5 | Digi-Key | [1168-TG-A1660-40-40-0.5-ND](https://www.digikey.com/en/products/detail/t-global-technology/TG-A1660-40-40-0-5/11617038) | 8 | Cut 10 x 7 mm pieces: TMP117 tab to the thermal window |
| 5 | 1 | Silicone grease, 85 ml | MG Chemicals 8462-85ML | Digi-Key | [473-1232-ND](https://www.digikey.com/en/products/detail/mg-chemicals/8462-85ML/6035523) | 10 | Thin film on the O-ring |
| 6 | 1 | Humidity indicator cards, 3-spot (can of 125) | SCS 3HIC125 | Digi-Key | [SCP667-ND](https://www.digikey.com/product-detail/en/scs/3HIC125/SCP667-ND/1621628) | 20 | Cut one spot, stick it inside the cup as the leak indicator |
| 7 | 1 | O-ring 90 mm ID × 1.5 mm cross-section (93 mm OD), nitrile (NBR) 70 Shore A, pack of 5–10 | any (uxcell or similar) | Amazon | [search](https://www.amazon.com/s?k=90mm+ID+1.5mm+nitrile+o-ring) | 8 | Plug groove. Must be exactly 1.5 mm cross-section: McMaster's 90 mm Viton rings (8683N269) are 2 mm and don't fit. NBR is fine in bath water and with silicone grease |
| 8 | 1 | Screw, flat head, thread-forming for plastic, 18-8 stainless, Torx drive, M2 x 6 mm (pack of 50; 4 per device) | McMaster-Carr 95893A165 | McMaster-Carr | [95893A165](https://www.mcmaster.com/95893A165/) | 13.33 | Side walls into the plug, 4 per device. Fits the existing M2 holes (2.3 mm clearance, 1.6 mm pilot). The tip reaches 1.5 mm past the plug skirt, 0.9 mm clear of the coil: checked in fit_and_render.py |
| 9 | 1 | Quick-recovery urethane foam (PORON-type), 1/16 in, 12 × 12 in, 18 psi (medium) | McMaster-Carr 86375K132 | McMaster-Carr | [86375K132](https://www.mcmaster.com/86375K132/) | 17 | Cut 30 mm discs: between the coil and the plug. Also the battery-swelling buffer |
| 10 | 1 | Suction cups 40 mm, clear PVC, mushroom head (pack of 12; leave the hooks off) | Flintronic | Amazon | [search](https://www.amazon.com/s?k=Flintronic+suction+cups+40mm+mushroom+head) | 10 | Bracket keyholes, 2 per device (docs/enclosure.md 2.7) |
| 11 | 3 | Qi wireless charging pad, 10 W (brim takes 5 W), USB powered. Needs a 5 V / 2 A USB charger, not included | Anker 313 Wireless Charger (Pad) A2503 | Amazon | [search](https://www.amazon.com/s?k=Anker+313+Wireless+Charger+Pad) | 15 | One per prototype. Any Qi pad works; avoid vertical stands |
| 12 | 1 | 0603 ceramic capacitor assortment incl. C0G 1–10 nF and X7R 10–220 nF | any | Amazon | [search](https://www.amazon.com/s?k=0603+ceramic+capacitor+assortment+C0G) | 12 | Qi tuning spares: C_d = C4 3.3 nF (try 2.7 / 3.9 nF); C_s = 3 × 100 nF + C23 10 nF (swap C23 for 22–47 nF) |
| 13 | 1 | 0402 resistor assortment, 1 % | any | Amazon | [search](https://www.amazon.com/s?k=0402+resistor+assortment+1%25) | 10 | FOD tuning spares: R2 = 196R (try 150–249R) |

**Three suppliers only:** Amazon (items 1, 7, 10–13), Digi-Key (items 2–6) and McMaster-Carr (items 8, 9). Approximate total: **about US$193** plus shipping. Prices are search snapshots: check them in the cart.

**Bundling a charger in production:** a plain 5 W Qi pad is a commodity part. OEM factories quote it per 1,000 units
(Alibaba / Global Sources listings for higher-power Qi2 pads sit around US$4.6–5.8 at 100–1,000 MOQ, so a basic 5 W pad
should land lower; get quotes, with FCC/CE/RoHS and Qi certification). A branded "brim nest" sized to the coil ring
makes alignment foolproof. Phones with Samsung Wireless PowerShare (Galaxy S10 and later S series, Z Fold / Z Flip) or
Google Pixel Battery Share (Pixel 5 to 9 series) can also charge brim back-to-back.

## Before ordering
- **Battery:** marketplace cells vary. On arrival check thickness (≤ 4.4 mm), that a protection board sits under the tape, and polarity (red to J1 pin 1). Cut the connector off and solder the wires to J1, so the listing's connector model, size and polarity warnings don't apply, as long as red goes to pin 1. The case is sized for 25.5 × 36 × 4.3 mm, with room for +10 % swelling (see enclosure.md).
- **Screws:** McMaster 95893A165 (M2 x 6 mm, 18-8, Torx, thread-forming for plastic, pack of 50). They fit the case's existing M2 holes.
- **O-ring:** nitrile (NBR) in the exact 90 mm ID × 1.5 mm size (93 mm OD). Check the cross-section in the listing: a 2 mm ring will not fit the groove. EPDM would be ideal but isn't sold in this size by these three suppliers; NBR is fine at bath temperatures. FKM (Tameson S26DT-X5) is the upgrade if you ever order elsewhere.
- **Foam:** McMaster 86375K132 is the same type of open-cell urethane as PORON; confirm the 1/16" thickness on the product page.
- **Suction cups:** marketplace listings drift; any 40 mm clear PVC mushroom-head cup fits the keyholes (head ≤ 12 mm, neck ≤ 5.8 mm).

Not in this list: the PCB and its SMD parts (JLC PCBA), the enclosure prints (`hardware/mech/out/`, JLC3DP), and a USB-C cable for the first flash.
