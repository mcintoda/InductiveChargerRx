# squeeze: virtual bring-up and usability experiments

Before the boards are ordered, both experiments were run on the real firmware: unmodified, compiled twice
(the parent's and the child's build), in a simulated world with two units and two people. The bench, its models
and its limits are described in [`firmware/sim/README.md`](../firmware/sim/README.md). It runs in seconds:

```
cd squeeze/firmware/sim && make && make before
python3 experiments.py --tag after --sim sim            # this firmware
python3 experiments.py --tag before --sim sim_before    # the firmware as it was before these experiments (git HEAD)
python3 ../../hardware/tools/erc.py                     # static electrical checks
```

**Outcome:** the first round found **11 real problems**; ten were fixed at once. A second round
([section 4](#4-round-2-the-open-problems)) solved the rest: overlapping squeezes, battery life, the hug limit,
the low-battery rail warning, a pickup calling the partner (found by making the simulated people messier), and
it compiled the firmware with the real ESP-IDF.

| # | Found | Experiment | Fix |
|---|---|---|---|
| 1 | `bmp280.c` used `false` without `<stdbool.h>` (it would only compile by accident of the ESP-IDF include chain) | first compile | include added |
| 2 | Nothing on the bench says whether the hardware works: no report, servo never exercised | B1 | **self-test** at power-on with USB attached |
| 3 | The LED's perceptual curve squared each channel: the child's orange showed as **red** (the low-battery colour) | B2, U2 | curve on the brightness, not per channel |
| 4 | "Connected" and "charging" were ~0.2 % PWM: **invisible** | B5, smoke test | visible floor; charging is now green |
| 5 | Asleep, the unit sampled pressure once per 2 s: a quick squeeze woke it **7 times in 30** | U4 | 10 Hz sampling in light sleep: **30/30** |
| 6 | After waking by a squeeze, a lagging baseline (the hand warms the air) made a **phantom 10 s squeeze** that swallowed the real ones | U2 trace | baseline from the 10 Hz doze samples, frozen during a rise |
| 7 | Squeezes made while the partner was waking were **lost**, and the 0.4 s "hello" swell was mistaken for a squeeze | U1, U2 | squeezes are **kept and replayed** with their rhythm; hello swell removed |
| 8 | A call nobody answers gave no feedback | U6 | "nobody answered": 3 quick blinks of own colour |
| 9 | The partner's low battery was invisible on the other unit | U7 | short red flash every 4 s |
| 10 | A gentle 3 N squeeze could not wake a dozing unit | U9 | wake threshold 250 → 150 Pa (no false wakes in 1 h, U11) |
| 11 | A squeeze starting ≤ 0.25 s after the partner's is lost | U5 | first documented as inherent; **solved in round 2** (duplex sensing, section 4) |

![before / after: the child starts while both sleep](img/sim_child_wakes.png)

*U2 before and after. The child squeezes 3 times while both units sleep, then 3 times more. **Before**, the parent
felt only two things: the hello swell and a phantom squeeze. The LEDs showed red-looking colours. **After**, the parent
felt all six squeezes with their rhythm, the first three replayed ~1–1.8 s late. The child's LED shows calling, then
blue (connected); the parent's LED shows the orange invite.*

---

## 1. Bring-up

### 1a. On paper: `hardware/tools/erc.py` (31 checks on `parts.py`)
**31 pass, 0 warnings, 0 fail** (round 1 had one warning, now resolved: see the last bullet). It checks:
- **ESP32 boot:** EN reset delay 10 ms, GPIO2 and GPIO8 strapping pins held high, GPIO9 only on a test pad, USB D+/D− straight to the pins, CC pull-downs present.
- **Pin voltages:** VBUS sense 3.04–3.37 V (above the 2.48 V logic-high threshold, below the 3.6 V maximum); battery sense 2.10 V at 4.2 V (inside the 2.5 V ADC range).
- **Power:** boost output 4.95 V, enable defaults off; charge current 201 mA; NTC and termination resistor present.
- **Parts:** decoupling on every rail; LED currents 5.9 mA each; I2C pull-ups; BMP280 address pin to GND (0x76); hardware standby current 7.2 µA.

- **3.3 V rail at the cut-off:** round 1 only warned that the RT9080 has ~100 mV of headroom below 3.5 V. The check
  is now numeric and reads the thresholds from `main.c`: at the firmware's 3.30 V cut-off, a 350 mA Wi-Fi burst
  through the RT9080's dropout (250 mV max at 600 mA, ~0.42 Ω) leaves **3.15 V**, above the ESP32-C3's 3.0 V
  minimum. The servo stops at 3.40 V, so the boost never loads the cell below that.

### 1b. Simulated first power-up (`scenarios/bringup_*.txt`)
| Run | Before | After |
|---|---|---|
| **B1** USB attached, nobody holding | Boots, stays awake, LED calling. No report; servo never moved | **Self-test:** `battery 3980 mV: PASS`, `charger CHG: not charging`, `pressure sensor: 101322 Pa: PASS`, LED red/green/blue, servo rest → full → rest then 5 V off, `SELF-TEST PASSED (0 failures)`. Never dozes on USB |
| **B2** BMP280 not answering | Logs the error; still receives (felt 130 ms after the partner's squeeze). LED shows the partner's orange as red | Same, plus `pressure sensor: FAIL (no BMP280 at 0x76: check U4 soldering)`; colours correct |
| **B3** both powered, one squeeze each, then idle | Felt 110 ms (A→B) and 130 ms (B→A) after the squeeze started; boost on during playback, off ~1.2 s later; both sleep 90 s after the last squeeze | Same latencies and power-down; both doze 90 s after the last squeeze |
| **B5** on a Qi pad, charging | LED dark (faint amber at ~0.2 % PWM) | Faint **green** |

The bring-up checklist in [design.md](design.md) section 9 now starts with the self-test and points each `FAIL` at
a part.

---

## 2. Usability

**People:**
- **Parent:** holds their unit, squeezes firmly (20 N), and sends 3 patterns (2 squeezes; short-short-long; long + 3 quick). After a reply, they wait 2 s and send the next pattern.
- **Child:** copies what it felt, with the same count and ±20 % durations and gaps, at 8 N, 0.6–1.2 s after the pattern ends.

Unless stated otherwise, both units start dozing, as at bedtime.

| Run | What it tests | Before | After |
|---|---|---|---|
| **U1** the game (5 seeds) | 3 rounds from sleep | parent→child **6/9** felt, child→parent **4/6**, 2 of 3 rounds completed | **9/9 and 9/9, 3/3 rounds**, every seed; median 110–130 ms |
| **U2** the child starts, both asleep | 3 squeezes, then 3 more 10 s later | **2/6** felt (one was really the hello swell) | **6/6**: first three replayed 1.8 / 1.4 / 1.0 s late, then 105–125 ms |
| **U3** parent's unit on the table | Child calls; parent picks up 25 s later | Child's squeezes never woke its own unit (2 s sampling): nothing happened until pick-up; reply 665 ms | Parent's unit **glows the child's orange** from the call until picked up; reply felt in **120 ms** |
| **U4** a quick squeeze (0.25 s) while asleep, 30 random times | Wake reliability | **7/30** woke | **30/30** |
| **U5** both squeeze 0.1 s / 0.25 s apart | Overlap | Parent's felt 2/2; child's **0/2** | Round 1: same. Round 2: **2/2 and 2/2** (section 4) |
| **U6** child out of range | Feedback | Red-looking breathing, then dark | Own colour breathing (calling), then **3 quick blinks**: nobody answered |
| **U7** child's battery at 5 % | Low battery | Child's unit blinks red; parent's unit shows nothing | Child's unit blinks red; **parent's unit flashes red every 4 s** |
| **U9** gentle squeezes 2–10 N (80 Pa/N) | Detection, asleep / awake | Asleep: only the hello swell counted; awake: missed up to 8 N (the phantom squeeze) | **All delivered from 2 N up**, asleep and awake |
| **U10** a 6 s hug squeeze | Hold limit | Plates relax after 4.07 s | Round 2: felt for the **whole 6 s** (eases to 40 % after 4 s) |
| **U11** held for 1 h, nobody squeezing | False wake-ups at the lower threshold | 0 calls | **0 calls** |
| **U8** battery | Standby / play | 2.58 mA dozing; 9.4 mAh per 5-min session; **4.4 days** at 3 sessions/day | Round 1: 2.76 mA dozing (10 Hz sampling), **4.1 days**. Round 2: 2.17 mA for 10 min after play, then 1.40 mA; **6.2 days** |

---

## 3. Limits of a virtual experiment

- **The ESP-IDF calls are stand-ins.** They copy the real names and signatures (ESP-IDF 5.3), so the firmware's
  logic runs, but they are not the real drivers. The same source now also **builds with the real ESP-IDF v5.3.2**
  for both roles with no warnings (section 4). Still to verify on hardware:
  - the light sleep ↔ `esp_wifi_stop/start` ↔ `esp_now_deinit/init` sequence and its timing (modelled at 35 ms);
  - the light-sleep current (modelled at 130 µA);
  - the BMP280 forced-x1 timing (datasheet 5.5 ms typical, 6.4 ms maximum).
- **The physics is modelled, not measured:**
  - squeeze pressure 80 Pa per newton (sized to the CAD's 0.6–2.2 kPa);
  - plate push into a held hand 250 Pa/mm, felt at 4 N/mm, felt above 1 N;
  - warming air +0.34 kPa/°C;
  - servo speed 600°/s;
  - current figures per state.

  Bring-up step 5 of design.md section 9 measures the real squeeze pressure; retune `WAKE_PA` and `on_pa` with it.
- **The people are still models.** Round 2 gave them a steady grip when they pick a unit up and a hand tremor
  (U12, U13), but they still never drop, shake or throw it. A real 6-year-old will. The thresholds now learn each
  holder's tremor, but the 80 Pa/N figure still needs measuring (bring-up step 5).
- **Deep sleep** (now used only at a flat battery) keeps RAM in the simulator. On the chip only `RTC_DATA_ATTR`
  survives it. The firmware no longer relies on anything else across a deep sleep.

---

## 4. Round 2: the open problems

Round 1 left six things open. This round solved each one in the firmware and checked it on the bench, again
against the previous firmware (`make before` = commit `34f31c2`). Making the simulated people messier, with a
grip and a tremor, found one more problem (U12, U13).

| Problem | Fix | Before (34f31c2) | After |
|---|---|---|---|
| **Overlap** (U5): a squeeze within 0.25 s of the partner's is lost, because the plates' own push looks like a squeeze | **Duplex sensing:** while its own plates move, a unit subtracts their pressure (cam lift × a learned Pa/mm, plus a margin). Whatever is left is the holder. The learned Pa/mm only moves up slowly, so a squeeze during playback can't teach it. A squeeze pressed against moving plates is sent at no less than 25 %, so it can still be felt | child's 0/2 | **2/2**, arriving 0.5–0.7 s later (after the partner's) |
| **Battery** (U8): 4.1 days | **10 Hz forced-mode samples** (5.5 ms) in light sleep. Listens every 2 s for the first 10 min after play, then every 4 s (`SQZ_DEEP_PERIOD_MS`, `SQZ_RECENT_S`). The "call" lasts long enough to reach a slow listener | 2.77 mA dozing, 4.2 days | **2.17 → 1.40 mA, 6.2 days** at 3 sessions/day |
| **Thresholds were guesses**: tuned for a model, not a hand | **Self-calibrating:** the on/off thresholds are max(configured, 4σ / 2.5σ) of the idle noise this holder makes. The wake threshold is max(100 Pa, 8σ) of the doze samples. Gentle squeezes still count from 2 N (U9) | — | U9 all forces; U11 0 false calls in 1 h |
| **Hug** (U10): plates let go at 4 s | **Hold easing:** after 4 s they ease to 40 % over 1 s and hold until 12 s, which still protects the servo | felt 4.1 s | **felt 6.05 s** (the whole hug) |
| **RT9080 warning** | Numeric check against the firmware's own cut-off (section 1a) | WARN | **PASS** (3.15 V worst case) |
| **Never compiled for real** | ESP-IDF v5.3.2 installed and both roles built (`idf.py build`, see the README). The C3-MINI-1U's 4 MB flash is now set in `sdkconfig.defaults` | — | **0 warnings, 0 errors**; 610 kB code |
| **New: a pickup calls the partner** (U12, U13). Picking the unit up (3–4 N grip and a tremor) woke it, and the tremor's peaks were sent as squeezes. Each tidy-up at night made the other unit swell | **Confirm before sending:** frames are held (≤ 10 s) until the squeeze is confirmed: 0.5 average level, or 0.6 for 40 ms, or a gentle squeeze released within 0.12–1.5 s. A weak rise held for 3 s is a grip: re-zero, learn its tremor, drop the held frames | U12 parent→child 6/9, pickup felt 1–2; U13 3 calls, felt 1 | U12 **9/9 and 9/9, 0 pickup calls**; U13 **0 calls** |
| **New: fast patterns merge** (seen in U1 once the child had a tremor): a gap under ~0.1 s between two squeezes was played as one | Playback keeps every pause between squeezes at **≥ 120 ms**. The queue catches up in the next long pause | (1 in 45) | U1 **9/9 and 9/9**, all 5 seeds |

**The cost:** latency from squeeze to felt is now **155–185 ms** (it was 110–130 ms), because a squeeze has to be
confirmed before it is sent. A faster rule (one sample above 0.7) saved 20 ms, but lost the overlap case again,
so it was not kept. For a game of copying patterns, the rhythm is what counts, and it is unchanged.

**Building the real firmware**
```
. ~/esp/esp-idf/export.sh            # ESP-IDF v5.3.2
cd squeeze/firmware
idf.py -B build-parent -D SDKCONFIG=build-parent/sdkconfig -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.parent" set-target esp32c3 build
idf.py -B build-child  -D SDKCONFIG=build-child/sdkconfig  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.child"  set-target esp32c3 build
```
