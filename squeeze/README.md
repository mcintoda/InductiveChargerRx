# squeeze: pass a squeeze across the house

Two soft, glowing pebbles, one for a parent and one for a child. Squeeze yours and the other one squeezes
its holder's hand with the same rhythm and strength, live. Squeeze a pattern; get it squeezed back.
It doesn't judge or score; it just passes squeezes back and forth.

![outside, inside, exploded](docs/img/unit_views.png)

- **Sense:** the whole pebble is a sealed air volume under a 2 mm silicone skin. A squeeze raises the pressure
  0.6–2+ kPa, read by a BMP390. Auto-ranging, so a child's squeeze counts as much as an adult's.
- **Squeeze back:** an SG90 servo turns an oval cam that pushes two curved plates 3 mm out into the palm and
  fingers, in proportion to the partner's squeeze.
- **Link:** ESP-NOW between two XIAO ESP32-C3s: no router, no app, ~5 ms. Turn-taking: whoever squeezes first
  has the floor.
- **Power:** Qi charging (brim's BQ51050B block and coil), 400 mAh LiPo. Sleeps by itself and wakes on a squeeze or when the
  partner calls.
- **Enclosure:** 52 × 42 × 70 mm. Cast Dragon Skin 10 skin in each person's colour, glowing from inside. The 3D-printed
  mold is included.

| | |
|---|---|
| [`docs/design.md`](docs/design.md) | Requirements, sensing, mechanism, electronics, radio, behaviour and LED legend, enclosure and casting, build plan, safety, risks |
| [`docs/bom.md`](docs/bom.md) | Stage 1 breadboard BOM (~$55) and stage 2 keeper BOM |
| [`firmware/`](firmware/) | ESP-IDF 5.3 (ESP32-C3). Pure logic host-tested: `make -C firmware/test` |
| [`hardware/mech/`](hardware/mech/) | CadQuery model, fit check and renders. STEP/STL in `out/` |

```
# host tests (no hardware)
make -C squeeze/firmware/test

# firmware: one build per unit (same code, different role/colour/strength)
cd squeeze/firmware
idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.parent" -B build-parent build
idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.child"  -B build-child  build
idf.py -B build-parent -p /dev/ttyACM0 flash monitor
# set the same "Pair secret" on both first: idf.py menuconfig -> Squeeze pair

# enclosure
python3 squeeze/hardware/mech/squeeze_unit.py     # STEP/STL
python3 squeeze/hardware/mech/fit_and_render.py   # interference check at rest and full swell, renders
```

Status: **rev A design.** CAD fit-checked. Firmware written and logic tested, but not yet compiled with ESP-IDF or run
on hardware. Next: stage 1 breadboard (design.md §9).
