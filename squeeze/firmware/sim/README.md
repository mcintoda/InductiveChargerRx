# squeeze virtual test bench

The real firmware (`../main/*.c`, unmodified) is compiled **twice**, once as the parent's build and once as the
child's (`sdkconfig.in.h`). Each build is linked against stand-ins for every ESP-IDF call it makes (`shim/`, `shim.c`),
and the two copies run together in one simulated world (`world.c`). Results and findings:
[docs/virtual-experiments.md](../../docs/virtual-experiments.md).

```
make                    # ./sim         (the working tree's firmware)
make before             # ./sim_before  (the firmware in git HEAD, for before/after)
./sim scenarios/game_from_sleep.txt out/game      # -> out/game.events.csv, out/game.log
python3 experiments.py --tag after                # all bring-up and usability runs, summary on stdout
python3 plot_timeline.py child_wakes 128.5 145 ../../docs/img/sim_child_wakes.png
```

## How it works
- **Two copies of one firmware.** `ld -r` joins each build into one object. `objcopy` then prefixes every symbol
  (`uA_`, `uB_`) except the ones it imports, so both copies, statics included, link into one program.
- **Time.** Each unit runs in its own thread, but a lockstep scheduler lets only one run at a time, and only between
  blocking calls (`vTaskDelay`, queue waits, sleep). A seed makes a run repeatable. `esp_timer` restarts at 0 after a
  deep-sleep reboot (`longjmp` back to `app_main`).
- **BMP280:** a register model. ID 0x58; calibration bytes from Bosch's worked example; forced and normal modes with
  the datasheet's t_meas; raw values found by inverting the firmware's own compensation, so `bmp280_comp.c` is
  exercised end to end.
- **ADC, GPIO, PWM.** Battery voltage comes from state of charge. CHG and VBUS are inputs. The servo angle is decoded
  from the real LEDC duty (500–2400 µs). The LEDs are read from the inverted PWM (common anode) and classified as a
  colour and a level.
- **Servo, cam, plates.** The servo follows at 600°/s when its 5 V is enabled, and returns to rest when unpowered.
  Plate lift comes from the oval cam (8 × 5 mm).
- **Hand and air:**
  - a squeeze adds 80 Pa per newton;
  - plates pushing into a held hand add 250 Pa/mm, or 20 Pa/mm in free air;
  - the holder feels the plates at 4 N/mm, and a squeeze counts as felt above 1 N;
  - a held unit's air warms towards +5 °C (300 s time constant), adding +0.34 kPa/°C;
  - 2 Pa of sensor noise.
- **Radio:** ESP-NOW broadcast, delivered in ~2 ms only if the receiver's radio is on, on the same channel, in range, and
  not lost (`loss`).
- **Battery current, by state:**
  - deep sleep 12 µA; light sleep 130 µA, plus ~1.2 ms at 20 mA per wake;
  - CPU 20 mA, radio receiving 65 mA;
  - LED up to 6 mA per channel;
  - servo 8 / 180 / +40 mA per mm at 5 V (idle / moving / pushing a hand), through a boost at 88 % efficiency.

  A 400 mAh cell with a LiPo voltage curve.
- **People** (`A parent t force rounds`, `B child force`): the parent sends 3 kinds of pattern and waits for the reply.
  The child copies what it felt, with ±20 % timing.

## Scenario files
```
duration 230            # s
seed 1
loss 0.02               # radio frame loss
out_of_range 20 60      # s
A start 0               # power on (A = parent's build, B = child's)
A usb 1 | A charging 1 | A sensor 0 | A battery 0.05 | A held 155 1e9
B squeeze 130.0 0.3 8   # t, duration s, force N
A parent 130 20 3       # start t, force N, rounds
B child 8               # copies what it feels, at 8 N
```

## Limits
These are stand-ins and models, not the chip: see [virtual-experiments.md](../../docs/virtual-experiments.md),
section 3.
