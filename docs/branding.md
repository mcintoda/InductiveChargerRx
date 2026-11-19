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
| Front, left margin | **Level scale**: 7 equal, level horizontal ticks, one at every electrode boundary over the full 60 mm detection range, with **pad numbers 1–6** in the same column at the pad centres | Shows exactly where each detection level is, which matches the alarm-pad setting in the app ("alarm at pad 4") |
| Front, right margin | **Alarm chevron** at the default alarm level (top of pad 6) | Where the alarm triggers by default |
| Both long sides | **Waterline groove** (0.8 × 0.3 mm) at the default alarm level, wrapping the side walls | Styling line plus a visible alarm level when looking at the device edge-on in the bracket |
| Back (Qi face) | **Coil outline**: one plain 30 mm ring exactly over the Ø30 coil, with "Qi" and "charge this side" inside | Shows where the coil is. A round Qi coil works at any rotation, so there are no orientation marks |
| Back | Ripple mark, wordmark, "bath level monitor", rating line "Li-ion 3.7 V 500 mAh · IP68 · rev B" | Identity and rating |
| Front, electrode band | **No relief** | A flat, even 1.2 mm wall. Relief would thin the wall unevenly and trap water films (see the electrode study) |

Details that keep the markings from hurting function:
- The scale sits on the margin **outside** the 30 mm electrodes (|x| 15.9–18.5 mm; the electrodes end at 15.0) and
  stays clear of the edge round (flat face to |x| = 19.4 mm).
- The ticks are short (1.8 × 0.5 mm) and only 0.35 mm deep, so the drop of water one can hold is negligible next to a pad's signal.
- Deboss depth is 0.35 mm. The front wall stays ≥ 0.85 mm under the scale and the back wall ≥ 1.15 mm under the coil outline.
- The fit check still reports **0 interference** between the cup, plug and all internal parts.

## Making it look right
| Build | Cup (mist) | Plug + bracket (slate) |
|---|---|---|
| JLC3DP SLA prototype | White or clear resin (a light sanding gives a frosted mist look) | Grey resin, or spray slate on the outside only (keep paint off the O-ring bore and groove) |
| JLC3DP MJF PP | Natural PP (translucent grey-white) | Natural or dyed grey |
| Production (injection-molded PP) | Natural PP, light matte texture (VDI 24) except the sensing wall, which stays smooth | PP with a slate masterbatch matched to `#61798A` |

Leave the debosses unpainted for the quiet look. For more contrast on the scale only, wipe ink-coloured enamel into the
ticks and numbers and scrape off the excess.

## Files
- `hardware/mech/brand.py`: name, palette, ripple mark, scale, waterline, coil outline (used by `enclosure.py`; set `BRANDING = False` for plain parts)
- `hardware/mech/brand_render.py`: regenerates `docs/img/brand_logo.svg/.png`, `brand_mockup.svg/.png` and `brand_cad_faces.png`
