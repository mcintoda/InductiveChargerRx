# brim firmware (ESP-IDF 5.3, ESP32-S3)

| Module | What it does |
|---|---|
| `main.c` | State machine: **setup** (access point + form), **charger** (settings / OTA page, dry recalibration, factory-reset gesture), **bath** (sleep until PAD1 is wet, then track the fill every 2 s) |
| `level.c` | Level from the 6 electrodes + dry REF: per-pad learned full-wet value, REF drift compensation, chaining to reject water films, "top of pad n" detection. Pure C |
| `rate.c` | Least-squares fill rate over 60 s and time-to-alarm. Pure C |
| `policy.c` | What to send and when: filling (optional), nearly full (~2 min), **BATH FULL** (urgent, repeated every 60 s while still rising, max 15 min; above 60 mm the REF pad decides "still rising"), too hot, under water, low battery. Pure C |
| `sense_touch.c` | Touch peripheral: 7 channels, **driven shield on T14**, **idle channels high-impedance**, denoise; PAD1 as the deep-sleep wake channel |
| `tmp117.c` | One-shot ×8-averaged temperature over I²C, sensor powered from GPIO12 only while measuring |
| `power.c` | Battery voltage (ADC, 1M/1M divider), Qi-present, charge status, LED |
| `net.c` | Wi-Fi, ntfy HTTPS POST (CA bundle), setup / settings page, firmware upload (OTA) |
| `settings.c` | NVS settings: Wi-Fi, ntfy topic (random), alarm pad, hot-water limit, "notify when filling" |

## Build
```
. $IDF_PATH/export.sh          # ESP-IDF v5.3.x
idf.py set-target esp32s3
idf.py build
```
First flash over the USB test pads (D+/D−, hold IO0 low at reset): `idf.py -p /dev/ttyACM0 flash monitor`.
Later updates: put brim on its charger, open the settings page, upload `build/brim.bin`.

## Host tests (no hardware)
```
make -C test          # level estimation, film rejection, drift, fill rate, alarm policy
```

## Use
1. First power-up: join Wi-Fi **brim-setup-XXXX**, open http://192.168.4.1, enter Wi-Fi, pick the alarm pad.
   The page shows the ntfy topic: subscribe to it in the free ntfy iOS app.
2. While on the Qi charger, the same page is at the device's IP on your network for 10 minutes.
3. Factory reset: put it on the charger 3 times within 20 s.
4. Level sensing (settings page): `Touch` (ratiometric, default), `FDC1004` (boards with U5 fitted) or `Compare`.
   Compare logs `CMP,...` lines on the USB console for the bench protocol in `docs/sensing-options.md`.
