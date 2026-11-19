# Branding and industrial design (rev B)

![brim logo](img/brand_logo.png)

**brim**: *bath level monitor*. "Alert before it brims."
The name is a working name. It's set in one place (`NAME` in `hardware/mech/brand.py`), and every
asset and the CAD regenerate from it. Do a trademark search before using it publicly.

![Mockup](img/brand_mockup.png)

## The mark (rev B): a pebble dropped in still water
Concentric ripples seen at a low angle (flattened ellipses). The centre is the "plop", the outer ring breaks
at the sides where the ripple fades, and a single splash droplet sits above. It says *water, calm, a
level surface*, and stays legible as a 12–13 mm deboss. Stroke weights are 0.6–0.8 mm on the part, which prints
cleanly in SLA and MJF. CAD and SVG come from the same geometry (`ripple_solid()` in `brand.py`).

## Palette (muted)
| Name | Hex | Use |
|---|---|---|
| mist | `#E8ECEA` | Cup: soft warm white / natural translucent PP. The LED glows through |
| slate | `#61798A` | Plug and bracket, the logo mark |
| ink | `#2F3A45` | Wordmark in print / docs |
| sea glass | `#9CC3B9` | Quiet accent (LED glow, highlights). Use sparingly |

On the device the branding is **unpainted deboss**: it reads as a soft shadow in the same colour as the part,
which keeps it understated. The mockup shows it that way.

## Typography
**Inter Medium** (SIL Open Font License), lowercase wordmark. The smallest debossed text is 2.2 mm.

## Case styling and functional markings

![CAD faces](img/brand_cad_faces.png)

| Where | Feature | Purpose |
|---|---|---|
| Front edge | **2.5 mm soft round** (was 1.5) | Pebble-like, comfortable to handle. The flat sensing wall sits entirely inside the round |
| Front, dry top band | Ripple mark + wordmark | Branding above the waterline, over the electronics |
| Front, electrode band | **The electrodes are the graphic.** Through the translucent mist cup, the six level pads and the REF pad show as soft grey panels: copper under a **white solder mask** on the PCB front. No numbers, no ticks | Shows exactly where each detection level is, with no extra marks and nothing cut into the sensing wall |
| Front, both margins | Small **alarm arrows** at the default alarm level (top of pad 6), outside the electrodes | Where the alarm triggers by default |
| Both long sides | **Waterline groove** (0.8 × 0.3 mm) at the default alarm level, wrapping the side walls | Styling line plus a visible alarm level when looking at the device edge-on in the bracket |
| Back (Qi face) | **Coil outline**: one plain 30 mm ring exactly over the Ø30 coil, with "Qi" and "charge this side" inside | Shows where the coil is. A round Qi coil works at any rotation, so there are no orientation marks |
| Back | Ripple mark, wordmark, "bath level monitor", rating line "Li-ion 3.7 V 500 mAh · IP68 · rev B" | Identity and rating |
| Front, electrode band | **No relief** | A flat, even 1.2 mm wall. Relief would thin the wall unevenly and trap water films (see the electrode study) |

Details that keep the markings from hurting function:
- The panels need a translucent cup (natural PP, or frosted clear/white resin) and a white solder mask. If the contrast is too faint on the first prototype, use a slightly thinner frosted finish rather than adding marks.
- Deboss depth is 0.35 mm. The front wall stays ≥ 0.85 mm under the arrows and the back wall ≥ 1.15 mm under the coil outline.
- The fit check still reports **0 interference** between the cup, plug and all internal parts.

## Making it look right
| Build | Cup (mist) | Plug + bracket (slate) |
|---|---|---|
| JLC3DP SLA prototype | White or clear resin (a light sanding gives a frosted mist look) | Grey resin, or spray slate on the outside only (keep paint off the O-ring bore and groove) |
| JLC3DP MJF PP | Natural PP (translucent grey-white) | Natural or dyed grey |
| Production (injection-molded PP) | Natural PP, light matte texture (VDI 24) except the sensing wall, which stays smooth | PP with a slate masterbatch matched to `#61798A` |

Leave the debosses unpainted for the quiet look.

## Files
- `hardware/mech/brand.py`: name, palette, ripple mark, alarm arrows, waterline, coil outline (used by `enclosure.py`; set `BRANDING = False` for plain parts)
- `hardware/mech/brand_render.py`: regenerates `docs/img/brand_logo.svg/.png`, `brand_mockup.svg/.png` and `brand_cad_faces.png`
