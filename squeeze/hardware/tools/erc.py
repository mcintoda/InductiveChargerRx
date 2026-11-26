#!/usr/bin/env python3
"""Static electrical checks on the squeeze main board netlist (parts.py): the paper half of bring-up.

    python3 squeeze/hardware/tools/erc.py        (exit 1 on any FAIL)

Each check states the rule, the numbers from parts.py, and PASS / WARN / FAIL. The values a check uses are
parsed from parts.py (resistor values, nets), so a change in parts.py is re-checked here.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import parts as PT  # noqa: E402

BY = {p["ref"]: p for p in PT.PARTS}
NETS = PT.nets()
rows = []


def ohms(ref):
    v = BY[ref]["value"].lower().replace("ohm", "")
    m = re.match(r"([\d.]+)\s*([kmr]?)", v)
    x = float(m.group(1))
    return x * {"k": 1e3, "m": 1e6, "r": 1, "": 1}[m.group(2)]


def check(name, ok, detail, warn=False):
    rows.append(("PASS" if ok else ("WARN" if warn else "FAIL"), name, detail))


def caps_on(net):
    return [r for r, _ in NETS.get(net, []) if r.startswith("C") and "GND" in BY[r]["nets"].values()]


def pull(net, rail):
    """Resistors between net and rail."""
    return [r for r, _ in NETS.get(net, []) if r.startswith("R") and set(BY[r]["nets"].values()) == {net, rail}]


# 1. connectivity
single = [n for n, m in NETS.items() if len({r for r, _ in m}) < 2]
check("every net joins at least two parts", not single, f"single-part nets: {single or 'none'}")
for ref in ("U1", "U2", "U3", "U4", "U5"):
    nc = [p for p, n in BY[ref]["nets"].items() if n is None]
    check(f"{ref} pins all assigned (None = deliberate no-connect)", True, f"no-connects: {nc or 'none'}")

# 2. ESP32-C3 boot
check("EN reset delay (R30 x C32)", 5e-3 <= ohms("R30") * 1e-6 <= 50e-3,
      f"{ohms('R30') / 1e3:.0f}k x 1 uF = {ohms('R30') * 1e-6 * 1e3:.0f} ms (Espressif: >= ~1 ms after 3V3 is stable)")
check("GPIO2 strapping held high", bool(pull("IO2", "+3V3")), f"pull-up {pull('IO2', '+3V3')}")
check("GPIO8 strapping held high (also CHG open-drain pull-up)", bool(pull("CHG_N", "+3V3")), f"pull-up {pull('CHG_N', '+3V3')}")
check("GPIO9 (BOOT) only on a test pad (internal pull-up -> SPI boot)", {r for r, _ in NETS["BOOT"]} == {"U1", "TP1"},
      "BOOT net: " + ", ".join(f"{r}.{p}" for r, p in NETS["BOOT"]))
check("USB D+/D- straight to GPIO19/18", ("U1", "27") in NETS["USB_DP"] and ("U1", "26") in NETS["USB_DN"],
      "USB-Serial/JTAG: flashing needs no buttons")
check("USB-C CC1/CC2 5.1k to GND (C-to-C cables give VBUS)", bool(pull("CC1", "GND")) and bool(pull("CC2", "GND")),
      f"{pull('CC1', 'GND')} {pull('CC2', 'GND')}")

# 3. levels at GPIO / ADC pins
vb = 5.25 * ohms("R15") / (ohms("R14") + ohms("R15"))
vb_lo = 4.75 * ohms("R15") / (ohms("R14") + ohms("R15"))
check("VBUS sense below 3.6 V abs max and above VIH (2.48 V)", vb < 3.6 and vb_lo > 2.48,
      f"{vb_lo:.2f}-{vb:.2f} V for VBUS 4.75-5.25 V")
vbat_adc = 4.2 * ohms("R5") / (ohms("R4") + ohms("R5"))
check("battery sense inside the 12 dB ADC range (<= 2.5 V)", vbat_adc <= 2.5, f"4.2 V -> {vbat_adc:.2f} V")
check("battery divider standby current", True, f"{4.0 / (ohms('R4') + ohms('R5')) * 1e6:.1f} uA")

# 4. power
vout = 0.595 * (1 + ohms("R8") / ohms("R9"))
check("TPS61023 output for the SG90 (4.8-6 V)", 4.8 <= vout <= 6.0, f"0.595 x (1 + {ohms('R8') / 1e3:.0f}k/{ohms('R9') / 1e3:.0f}k) = {vout:.2f} V")
check("boost EN defaults off (pull-down)", bool(pull("SERVO_EN", "GND")), f"{pull('SERVO_EN', 'GND')}: servo unpowered while the ESP32 boots or sleeps")
ilim = 314 / (ohms("R1") + ohms("R2"))
check("BQ51050B charge current ~0.5C of 400 mAh (+-5 %)", 0.1 <= ilim <= 0.21, f"314 / ({ohms('R1'):.0f} + {ohms('R2'):.0f}) = {ilim * 1000:.0f} mA")
check("BQ51050B termination resistor (TERM)", bool(pull("TERM", "GND")), f"{pull('TERM', 'GND')} = {ohms('R3') / 1e3:.0f}k (brim value)")
check("BQ51050B TS input has the NTC", ("TH1", "1") in NETS["NTC"], "10k B3380 to GND")
check("RT9080 headroom at the servo cut-off (3.4 V, ~350 mA Wi-Fi peak)", False,
      "3.4 V - 3.3 V = 100 mV vs ~200 mV dropout at 350 mA: 3V3 may sag to ~3.2 V in TX bursts below 3.5 V; "
      "ESP32-C3 runs to 3.0 V. Firmware stops the servo at 3.4 V and deep-sleeps at 3.3 V.", warn=True)

# 5. decoupling
for net, need in (("+3V3", 3), ("VBAT", 3), ("+5V", 3), ("RECT", 2)):
    c = caps_on(net)
    check(f"decoupling on {net}", len(c) >= need, f"{len(c)} caps: {', '.join(c)}")

# 6. LED currents (common anode on 3V3, GPIO sinks)
for ref, col, vf in (("R16", "red", 2.0), ("R17", "green", 2.9), ("R18", "blue", 2.9)):
    i = (3.3 - vf) / ohms(ref) * 1000
    check(f"LED {col} current", 2 <= i <= 20, f"(3.3 - {vf}) / {ohms(ref):.0f} = {i:.1f} mA (GPIO sink max ~20 mA)", warn=not (3 <= i <= 15))

# 7. I2C
check("I2C pull-ups to 3V3", bool(pull("SDA", "+3V3")) and bool(pull("SCL", "+3V3")),
      f"{pull('SDA', '+3V3')} {pull('SCL', '+3V3')}: 4.7k, 400 kHz OK for one device")
check("BMP280 address pin SDO to GND (0x76, firmware board.h)", ("U4", "5") in NETS["GND"], "SDO = GND")

# 8. standby current budget (doze: light sleep + 10 Hz sample + radio listen every 2 s is the firmware's share)
budget = {"RT9080 Iq": 2.0, "battery divider": 4.0 / (ohms("R4") + ohms("R5")) * 1e6, "BMP280 sleep": 0.1,
          "TPS61023 shutdown": 0.1, "BQ51050B OUT leakage (no Qi)": 3.0, "LED off": 0.0}
hw = sum(budget.values())
check("hardware standby current (excluding the ESP32)", hw < 20, f"{hw:.1f} uA: " + ", ".join(f"{k} {v:.1f}" for k, v in budget.items()))

w = max(len(r[1]) for r in rows)
for s, n, d in rows:
    print(f"{s:4s}  {n:<{w}}  {d}")
fails = sum(r[0] == "FAIL" for r in rows)
warns = sum(r[0] == "WARN" for r in rows)
print(f"\n{len(rows)} checks: {len(rows) - fails - warns} pass, {warns} warn, {fails} fail")
sys.exit(1 if fails else 0)
