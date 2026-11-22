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
**First flash: plug in and flash.** Every board ships with a break-off USB-C tab on its right edge
(socket J2 + its own 3.3 V regulator U6). Plug a USB-C cable from the tab into the computer (no battery needed),
then run:

    idf.py -p /dev/ttyACM0 flash monitor      # Windows: -p COMx; macOS: /dev/cu.usbmodem*

No buttons and no pins to short. esptool resets the chip into its bootloader through the ESP32-S3's
built-in USB-Serial/JTAG, and a blank chip enumerates on its own. The firmware stays awake while a computer is
attached. Then snap the tab off (pliers, bend once along the slots) and assemble. No filing needed: the enclosure clears the rough stub.
The TP5/TP6 pads (D+/D−) still work for re-flashing a board without its tab. IO0 (TP4) is only for recovery.
Later updates: put brim on its charger, open the settings page, upload `build/brim.bin`.

## Host tests (no hardware)
```
make -C test          # level estimation, film rejection, drift, fill rate, alarm policy
```

## Use
1. First power-up: join Wi-Fi **brim-setup-XXXX**; the setup form pops up (captive portal; else http://192.168.4.1).
   Enter Wi-Fi, pick the alarm pad, **Copy** the ntfy topic and subscribe to it in the free ntfy app, then Save.
   brim joins the Wi-Fi and sends **"brim is connected"**. Wrong password: setup re-opens with an error (cyan blink).
2. On the Qi charger it sends a silent **"brim is charging"** alert; tap it for the settings page (10 minutes),
   which also has **Send a test alert** and the firmware upload. Saving or uploading there needs a **double-tap on
   brim** first (unlocks for 2 min; physical presence), see [`docs/security.md`](../docs/security.md).
3. Factory reset: put it on the charger 3 times within 20 s.
4. Level sensing (settings page): `FDC1004` (default; falls back to touch on boards without U5), `Touch` (ratiometric) or `Compare`.
   Compare logs `CMP,...` lines on the USB console for the bench protocol in `docs/sensing-options.md`.

## On the device (rev C)
The phone gets every alert through ntfy. The device also signals on its own, so a full bath is noticed even when
the phone is in another room or the Wi-Fi is down.

| LED (RGB, 5 mA per colour) | Meaning |
|---|---|
| Cyan blink | Waiting for Wi-Fi setup (join **brim-setup-XXXX**) |
| Amber breathing / green steady | On the charger: charging / charged |
| Dim blue blip every 4 s | Watching a bath |
| Yellow slow breathing | Nearly full (about 2 min to go) |
| Red fast blink + 3 × 3 beeps | Bath full. Repeats every minute while it keeps rising, for up to 15 min |
| Green steady | Alarm acknowledged on the device |
| Magenta breathing | Water above your temperature limit |
| Orange double blink | brim is tilted / out of its bracket |
| One 1 s flash (green / yellow / red) | Tapped or picked up while asleep: battery above 50 % / above 20 % / below |

| Gesture | Effect |
|---|---|
| **Double-tap the case** during an alarm | Acknowledge: no more repeats or beeps this bath (two green flashes + a chirp) |
| Tap or pick it up while it sleeps | Shows the battery colour, then back to sleep |

Other checks:
- **Tilt.** At the start of each bath brim learns which way is "up" in its bracket. If it is tilted more than
  30° for 20 s while the bath is filling, the phone gets "brim is tilted".
- The piezo tone defaults to 4 kHz (`BUZ_HZ` in `buzzer.c`). Tune it to the loudest frequency of the disc once it
  is bonded into the plug.
