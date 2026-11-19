#!/usr/bin/env python3
"""Generate the Bath Monitor KiCad 7 schematic (wired, human-style layout).

Conventions used in the drawing
  * signal flows left -> right; series parts horizontal, shunt parts vertical
  * power is shown with power ports (GND, +3V3, VBAT); everything else is
    drawn as wires.  Net labels are used only for the few signals that travel
    between functional blocks (CHG_N, QI_DET_N, VBAT_SENSE, SDA, SCL, SENSE_3V3)

Each part also carries its *intended* pin->net map.  After writing the file,
run `verify_netlist.py`, which exports the netlist with kicad-cli and checks
that the drawn connectivity is exactly the intended one.

    python3 hardware/tools/gen_schematic.py && python3 hardware/tools/verify_netlist.py
"""
import csv
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from sexp import Sym, dump, find, parse  # noqa: E402

SYMDIR = os.environ.get("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols")
HW = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(HW, "kicad", "bath_monitor.kicad_sch")
NS = uuid.UUID("6f1d3c1e-0b5a-4d8e-9a57-6a3b8f2e1c00")


def uid(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


ROOT = uid("root")
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
TPFP = "TestPoint:TestPoint_Pad_D1.5mm"

# Canonical part values: every resistor/capacitor in the design is one of these,
# so the JLC BOM has as few unique lines as possible.
C100N = ("100nF", "50V X7R", C0603)
C22N = ("22nF", "50V X7R", C0402)
C10N = ("10nF", "50V X7R", C0402)
C470N = ("470nF", "25V X7R", C0603)
C2N7 = ("2.7nF", "50V C0G", C0603)
C1U = ("1uF", "25V X5R", C0402)
C10U = ("10uF", "25V X5R", C0805)
R1K, R10K, R1M, R196 = "1k 1%", "10k 1%", "1M 1%", "196R 1%"

# ---------------------------------------------------------------------------
# symbol library helpers
# ---------------------------------------------------------------------------
_libcache = {}


def load_symbol(lib_id):
    lib, name = lib_id.split(":")
    if lib not in _libcache:
        _libcache[lib] = parse(open(os.path.join(SYMDIR, lib + ".kicad_sym")).read())
    syms = {s[1]: s for s in find(_libcache[lib], "symbol")}
    s = syms[name]
    ext = find(s, "extends")
    if ext:  # flatten derived symbol
        parent = syms[ext[0][1]]
        props = {p[1]: p for p in find(s, "property")}
        body = []
        for e in parent[2:]:
            if isinstance(e, list) and e[0] == "property" and e[1] in props:
                body.append(props.pop(e[1]))
            elif isinstance(e, list) and e[0] == "symbol":
                body.append([e[0], e[1].replace(parent[1], name, 1)] + e[2:])
            else:
                body.append(e)
        s = [Sym("symbol"), name] + body + list(props.values())
    return [Sym("symbol"), lib_id] + list(s[2:])


def pins_of(sym):
    out = {}
    for u in find(sym, "symbol"):
        for p in find(u, "pin"):
            at = find(p, "at")[0]
            out.setdefault(find(p, "number")[0][1], (float(at[1]), float(at[2])))
    return out


def rot(dx, dy, r):
    """Library offset (y up) -> sheet offset (y down) for symbol rotation r (CCW)."""
    x, y = dx, -dy
    return {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}[r]


def q(v):
    return round(v, 2)


# ---------------------------------------------------------------------------
# drawing primitives
# ---------------------------------------------------------------------------
PARTS, WIRES, LABELS, NCS, TEXTS = [], [], [], [], []
_pwr = [0]


def P(ref, lib, value, fp, x, y, r=0, nets=None, text="r", **fields):
    p = dict(ref=ref, lib=lib, value=value, fp=fp, x=x, y=y, r=r, nets=nets or {}, text=text, fields=fields)
    PARTS.append(p)
    return p


def pin(ref, num):
    p = next(p for p in PARTS if p["ref"] == ref)
    dx, dy = pins_of(load_symbol(p["lib"]))[num]
    ox, oy = rot(dx, dy, p["r"])
    return (q(p["x"] + ox), q(p["y"] + oy))


def W(*pts):
    pts = [tuple(map(q, p)) for p in pts]
    for a, b in zip(pts, pts[1:]):
        assert a[0] == b[0] or a[1] == b[1], ("non-orthogonal wire", a, b)
        if a != b:
            WIRES.append((a, b))


def R(ref, value, x, y, r, a, b, fp=R0402, text=None, **f):
    return P(ref, "Device:R", value, fp, x, y, r, {"1": a, "2": b}, text or ("r" if r == 0 else "h"), **f)


def C(ref, value, x, y, r, a, b, fp=None, text=None, **f):
    value, rating, fp = value if isinstance(value, tuple) else (value, "", fp or C0402)
    if rating:
        f["Rating"] = rating
    return P(ref, "Device:C", value, fp, x, y, r, {"1": a, "2": b}, text or ("r" if r == 0 else "h"), **f)


def PWR(kind, x, y, r=0, value=None):
    _pwr[0] += 1
    lib = {"GND": "power:GND", "+3V3": "power:+3V3", "VBAT": "power:+BATT", "FLAG": "power:PWR_FLAG"}[kind]
    val = value or {"VBAT": "VBAT", "FLAG": "PWR_FLAG"}.get(kind, kind)
    P(f"#PWR{_pwr[0]:03d}" if kind != "FLAG" else f"#FLG{_pwr[0]:03d}", lib, val, "", x, y, r, text="pwr")


def GND(x, y, r=0):
    PWR("GND", x, y, r)


def LBL(name, x, y, angle):
    LABELS.append((name, q(x), q(y), angle))


def NC(ref, *nums):
    for n in nums:
        NCS.append(pin(ref, n))


def TP(ref, net, x, y, r, text="tp"):
    """Test pad. r=0 body up, 90 body left, 180 body down, 270 body right."""
    P(ref, "Connector:TestPoint", net, TPFP, x, y, r, {"1": net}, text=text)


G = 2.54

# ===========================================================================
# A. Qi receiver + charger
# ===========================================================================
UX, UY = 101.6, 76.2
P("U2", "Battery_Management:BQ51050BRHL", "BQ51050BRHLR", "Package_DFN_QFN:Texas_VQFN-RHL-20",
  UX, UY, 0, {"1": "GND", "20": "GND", "21": "GND", "2": "AC1", "19": "AC2", "3": "BOOT1", "17": "BOOT2",
              "5": "CLAMP1", "16": "CLAMP2", "6": "COMM1", "15": "COMM2", "18": "RECT", "4": "VBAT",
              "7": "CHG_N", "9": "GND", "10": "TERM", "11": "GND", "12": "ILIM", "14": "FOD", "13": "NTC"},
  text=((0, -21.6, None), (-3.81, 24.13, "right")), MPN="BQ51050BRHLR")
XL, XR = UX - 12.7, UX + 12.7
XB = XL - 33.02          # AC1 / AC2 vertical buses
XC = XL - 22.86          # centre of the BOOT/COMM/CLAMP capacitors

NC("U2", "8")            # AD-EN unused
W(pin("U2", "9"), (XL - G, pin("U2", "9")[1])); GND(XL - G, pin("U2", "9")[1], 270)   # AD -> GND
GND(*pin("U2", "1"))     # PGND

# fan-out of the bootstrap / comm / clamp pins to their capacitors
for pnum, col, row, ref, val, net, fp in [
        ("5", 7.62, -27.94, "C7", C470N, "CLAMP1", None),
        ("6", 10.16, -20.32, "C9", C22N, "COMM1", None),
        ("3", 12.7, -12.7, "C5", C10N, "BOOT1", None),
        ("17", 12.7, 20.32, "C6", C10N, "BOOT2", None),
        ("15", 10.16, 27.94, "C10", C22N, "COMM2", None),
        ("16", 7.62, 35.56, "C8", C470N, "CLAMP2", None)]:
    px, py = pin("U2", pnum)
    ac = "AC1" if row < 0 else "AC2"
    C(ref, val, XC, UY + row, 90, ac, net, fp=fp)
    W((px, py), (XL - col, py), (XL - col, UY + row), pin(ref, "2"))
    W(pin(ref, "1"), (XB, UY + row))
W(pin("U2", "2"), (XB, UY), (XB, UY - 27.94))           # AC1 bus
W(pin("U2", "19"), (XB, UY + 10.16), (XB, UY + 35.56))  # AC2 bus

# resonant tank: series C1 (3 caps in parallel) + parallel C2, Rx coil
C("C4", C2N7, XB - 7.62, UY + 3.81, 0, "AC1", "AC2", Note="Parallel detection cap C_d (~1 MHz, tune)")
W(pin("C4", "2"), (XB - 7.62, UY + 10.16))
for ref, val, dy in [("C1", C100N, 0), ("C2", C100N, -7.62), ("C3", C22N, -15.24)]:
    C(ref, val, 38.1, UY + dy, 90, "COIL_A", "AC1", Note="Series resonant cap C_s = 100n+100n+22n = 222 nF (tune to coil)")
    W(pin(ref, "2"), (43.18, UY + dy)); W(pin(ref, "1"), (33.02, UY + dy))
W((XB, UY), pin("C1", "2")); W((43.18, UY - 15.24), (43.18, UY)); W((33.02, UY - 15.24), (33.02, UY))
P("L1", "Device:L", "Qi Rx coil 11uH", "Connector_Wire:SolderWire-0.1sqmm_1x02_P3.6mm_D0.4mm_OD1mm",
  25.4, UY + 3.81, 0, {"1": "COIL_A", "2": "AC2"}, text=((0, 8.89, None), (0, 11.43, None)), Note="Qi receiver coil ~11 uH, ferrite backed, <=32 mm; leads hand-soldered")
W(pin("C1", "1"), pin("L1", "1")); W(pin("L1", "2"), (25.4, UY + 10.16), (XB, UY + 10.16))

# right side of the BQ51050B
BAT_Y = pin("U2", "4")[1]
W(pin("U2", "7"), (XR + G, pin("U2", "7")[1])); LBL("CHG_N", XR + G, pin("U2", "7")[1], 0)
W(pin("U2", "11"), (XR + G, pin("U2", "11")[1])); GND(XR + G, pin("U2", "11")[1], 90)     # EN2 -> GND
R("R21", R196, 137.16, pin("U2", "12")[1], 90, "ILIM", "ILIM2", text="hh")
R("R1", R196, 157.48, pin("U2", "12")[1], 90, "ILIM2", "FOD", text="hh",
  Note="R_ILIM = R21 + R1 + R2 = 588R -> I_BULK = 314 AOhm / 588R = 534 mA (K_ILIM spec'd for 500-1500 mA)")
W(pin("U2", "12"), pin("R21", "1")); W(pin("R21", "2"), pin("R1", "1")); W(pin("R1", "2"), (165.1, pin("R1", "2")[1]), (165.1, pin("U2", "14")[1]))
W(pin("U2", "14"), (165.1, pin("U2", "14")[1]))
R("R2", R196, 165.1, pin("U2", "14")[1] + 3.81, 0, "FOD", "GND", Note="R_FOD (TI: start at ~200R before FOD calibration)"); GND(*pin("R2", "2"))
RECT_Y = pin("U2", "18")[1]
W(pin("U2", "18"), (157.48, RECT_Y), (157.48, 104.14))
for ref, val, x in [("C11", C10U, 127.0), ("C21", C10U, 137.16), ("C12", C100N, 147.32)]:
    C(ref, val, x, RECT_Y + 3.81, 0, "RECT", "GND"); GND(*pin(ref, "2"))
W(pin("U2", "10"), (XR + G, pin("U2", "10")[1]))
R("R3", R10K, XR + G, pin("U2", "10")[1] + 3.81, 0, "TERM", "GND", Note="R_TERM = 240 Ohm/% x %: 10k -> 41.7 % of 534 mA = 222 mA (min 120 mA)")
GND(*pin("R3", "2"))
TP("TP8", "RECT", 157.48, 99.06, 270, text=((3.0, 2.54, "left"), (0, 0, None)))

# battery (with NTC) and VBAT rail
P("J1", "Connector_Generic:Conn_01x03", "Li-ion 1000mAh", "Connector_Wire:SolderWire-0.1sqmm_1x03_P3.6mm_D0.4mm_OD1mm",
  154.94, pin("U2", "13")[1], 0, {"1": "VBAT", "2": "NTC", "3": "GND"},
  Note="1S Li-ion pouch 1000 mAh (603450), protection PCM, 10k B3380 NTC lead to TS/CTRL")
W(pin("U2", "13"), pin("J1", "2"))
W((147.32, BAT_Y), (147.32, pin("J1", "1")[1]), pin("J1", "1"))
W(pin("J1", "3"), (144.78, pin("J1", "3")[1])); GND(144.78, pin("J1", "3")[1])
TP("TP7", "VBAT", 121.92, BAT_Y, 0, text=((-1.5, -4.5, "right"), (0, 0, None)))
PWR("VBAT", 127.0, BAT_Y)
C("C13", C1U, 129.54, BAT_Y + 3.81, 0, "VBAT", "GND"); GND(*pin("C13", "2"))
C("C22", C100N, 137.16, BAT_Y + 3.81, 0, "VBAT", "GND"); GND(*pin("C22", "2"))

# ===========================================================================
# B. Qi-present wake detector
# ===========================================================================
R("R4", R1M, 157.48, 107.95, 0, "RECT", "QI_GATE")
R("R5", R1M, 157.48, 115.57, 0, "QI_GATE", "GND"); GND(*pin("R5", "2"))
P("Q1", "Transistor_FET:BSS138", "BSS138", "Package_TO_SOT_SMD:SOT-23", 180.34, 111.76, 0,
  {"1": "QI_GATE", "2": "GND", "3": "QI_DET_N"}, text=((5.08, -1.27, "left"), (5.08, 1.27, "left")))
W(pin("R4", "2"), pin("Q1", "1")); GND(*pin("Q1", "2"))
R("R6", R1M, 182.88, 97.79, 0, "+3V3", "QI_DET_N"); PWR("+3V3", *pin("R6", "1"))
W(pin("Q1", "3"), pin("R6", "2"), (190.5, 101.6)); LBL("QI_DET_N", 190.5, 101.6, 0)

# ===========================================================================
# C. 3.3 V LDO
# ===========================================================================
P("U4", "Regulator_Linear:XC6220B331MR", "XC6220B331MR", "Package_TO_SOT_SMD:SOT-23-5", 193.04, BAT_Y + 2.54, 0,
  {"1": "VBAT", "3": "VBAT", "2": "GND", "5": "+3V3"}, text=((0, -10.16, None), (0, -7.62, None)), Note="1 A, 8 uA Iq. Alt: RT9080-33GJ5")
W(pin("U2", "4"), pin("U4", "1"))
W(pin("U4", "3"), (177.8, pin("U4", "3")[1]), (177.8, BAT_Y))
C("C14", C1U, 172.72, BAT_Y + 3.81, 0, "VBAT", "GND", text="l"); GND(*pin("C14", "2"))
GND(*pin("U4", "2")); NC("U4", "4")
W(pin("U4", "5"), (220.98, BAT_Y)); PWR("+3V3", 220.98, BAT_Y)
C("C15", C1U, 213.36, BAT_Y + 3.81, 0, "+3V3", "GND"); GND(*pin("C15", "2"))

# battery voltage divider
PWR("VBAT", 236.22, 50.8)
R("R7", R1M, 236.22, 54.61, 0, "VBAT", "VBAT_SENSE")
R("R8", R1M, 236.22, 62.23, 0, "VBAT_SENSE", "GND"); GND(*pin("R8", "2"))
C("C16", C100N, 246.38, 62.23, 0, "VBAT_SENSE", "GND"); GND(*pin("C16", "2"))
W(pin("R7", "2"), (246.38, 58.42), pin("C16", "1"), (254.0, 58.42)); LBL("VBAT_SENSE", 254.0, 58.42, 0)

# ===========================================================================
# F. TMP117
# ===========================================================================
P("U3", "Sensor_Temperature:TMP117xxDRV", "TMP117AIDRVR", "Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
  203.2, 152.4, 0, {"5": "SENSE_3V3", "2": "GND", "1": "SCL", "6": "SDA", "4": "GND"}, text=((3.0, -8.0, "left"), (3.0, 13.5, "left")),
  MPN="TMP117AIDRVR", Note="I2C 0x48, on isolated PCB tongue; powered from GPIO12 only while measuring")
RAIL = 134.62
W(pin("U3", "5"), (203.2, RAIL)); W((215.9, RAIL), (167.64, RAIL)); LBL("SENSE_3V3", 167.64, RAIL, 180)
C("C20", C100N, 215.9, RAIL + 3.81, 0, "SENSE_3V3", "GND"); GND(*pin("C20", "2"))
R("R18", R10K, 187.96, RAIL + 3.81, 0, "SENSE_3V3", "SDA")
R("R19", R10K, 172.72, RAIL + 3.81, 0, "SENSE_3V3", "SCL")
W(pin("R18", "2"), (187.96, pin("U3", "6")[1])); W(pin("U3", "6"), (182.88, pin("U3", "6")[1]))
LBL("SDA", 182.88, pin("U3", "6")[1], 180)
W(pin("R19", "2"), (172.72, pin("U3", "1")[1])); W(pin("U3", "1"), (167.64, pin("U3", "1")[1]))
LBL("SCL", 167.64, pin("U3", "1")[1], 180)
W(pin("U3", "4"), (190.5, pin("U3", "4")[1])); GND(190.5, pin("U3", "4")[1])
GND(*pin("U3", "2")); NC("U3", "3")
PWR("FLAG", 198.12, RAIL)

# ===========================================================================
# D. ESP32-S3 + E. level ladder
# ===========================================================================
MX, MY = 317.5, 114.3
U1 = {"1": "GND", "2": "GND", "3": "+3V3", "45": "EN", "4": "IO0",
      "5": "TOUCH1", "6": "TOUCH2", "7": "TOUCH3", "8": "TOUCH4", "9": "TOUCH5", "10": "TOUCH6",
      "18": "SHIELD_DRV", "13": "VBAT_SENSE", "14": "SDA", "15": "SCL", "16": "SENSE_3V3",
      "17": "QI_DET_N", "11": "TOUCH7", "36": "CHG_N", "25": "LED_DRV", "23": "USB_DN", "24": "USB_DP"}
U1.update({str(n): "GND" for n in range(42, 66) if n not in (44, 45)})
P("U1", "MCU_Espressif:ESP32-S3-MINI-1", "ESP32-S3-MINI-1-N8", "RF_Module:ESP32-S2-MINI-1", MX, MY, 0, U1,
  text=((5.08, -32.0, "left"), (-5.08, 34.0, "right")), MPN="ESP32-S3-MINI-1-N8",
  Note="S2-MINI-1 and S3-MINI-1 share the 15.4x20.5 mm LGA-65 land pattern; verify vs. S3 datasheet")
ML = MX - 15.24
# 3V3 and decoupling
W(pin("U1", "3"), (MX, 76.2), (363.22, 76.2)); PWR("+3V3", MX, 76.2)
for ref, val, x in [("C17", C10U, 340.36), ("C18", C100N, 353.06)]:
    C(ref, val, x, 80.01, 0, "+3V3", "GND"); GND(*pin(ref, "2"))
TP("TP1", "+3V3", 363.22, 76.2, 0)
GND(*pin("U1", "1"))
TP("TP2", "GND", 327.66, 147.32, 0); GND(327.66, 147.32); PWR("FLAG", 335.28, 147.32); GND(335.28, 147.32)
# EN: RC reset
EN_Y = pin("U1", "45")[1]
R("R9", R10K, 299.72, EN_Y - 3.81, 0, "+3V3", "EN", text=((2.54, -2.54, "left"), (2.54, 0, "left"))); PWR("+3V3", *pin("R9", "1"))
C("C19", C1U, 284.48, EN_Y, 90, "GND", "EN", text="hh"); GND(*pin("C19", "1"), 270)
W(pin("U1", "45"), pin("C19", "2"))
TP("TP3", "EN", 292.1, EN_Y, 0)
W(pin("U1", "4"), (294.64, pin("U1", "4")[1])); TP("TP4", "IO0", 294.64, pin("U1", "4")[1], 90)
# capacitive level ladder: fan-out of IO1..IO7 to 1k series resistors and electrodes.
# E1..E6 = level pads (E1 bottom / wake, E6 default alarm); E8 = dry reference pad on IO7.
for i in range(1, 8):
    px, py = pin("U1", str(4 + i))
    col, row = 266.7 + G * (i - 1), 116.84 + 7.62 * (i - 1)
    ref_r, ref_e = (f"R{10 + i}", f"E{i}") if i < 7 else ("R20", "E8")
    net = f"PAD{i}" if i < 7 else "PAD_REF"
    fp, note = (("BathMonitor:TouchPad_30x9mm", f"Level electrode {i} (1 = bottom / wake, 6 = default alarm)") if i < 7 else
                ("BathMonitor:RefPad_30x6mm", "Dry reference electrode above the ladder (drift compensation)"))
    R(ref_r, R1K, 254.0, row, 90, net, f"TOUCH{i}")
    W((px, py), (col, py), (col, row), pin(ref_r, "2"))
    P(ref_e, "Connector:TestPoint", net if i < 7 else "REF", fp, 243.84, row, 90, {"1": net}, text="tp", Note=note)
    W(pin(ref_r, "1"), (243.84, row))
# driven shield
SH_Y = pin("U1", "18")[1]
R("R17", R1K, 294.64, SH_Y, 90, "SHIELD", "SHIELD_DRV", text=((0, 2.54, None), (0, 4.45, None)))
W(pin("U1", "18"), pin("R17", "2")); W(pin("R17", "1"), (287.02, SH_Y))
P("E7", "Connector:TestPoint", "SHIELD", "BathMonitor:ShieldTap", 287.02, SH_Y, 90, {"1": "SHIELD"}, text=((-3.0, 2.54, "right"), (0, 0, None)),
  Note="Driven shield: L1 hatch around pads + L2 plane behind them")
# inter-block signals
for num, net in [("13", "VBAT_SENSE"), ("14", "SDA"), ("15", "SCL"), ("16", "SENSE_3V3"), ("17", "QI_DET_N")]:
    x, y = pin("U1", num); W((x, y), (x - G, y)); LBL(net, x - G, y, 180)
x, y = pin("U1", "36"); W((x, y), (x + G, y)); LBL("CHG_N", x + G, y, 0)
# USB test pads
W(pin("U1", "23"), (355.6, pin("U1", "23")[1])); TP("TP6", "USB_DN", 355.6, pin("U1", "23")[1], 270)
W(pin("U1", "24"), (365.76, pin("U1", "24")[1])); TP("TP5", "USB_DP", 365.76, pin("U1", "24")[1], 270)
# status LED
LX, LY = 340.36, pin("U1", "25")[1]
W(pin("U1", "25"), (LX, LY))
R("R10", R1K, LX, LY + 3.81, 0, "LED_DRV", "LED_A")
P("D1", "Device:LED", "Green", "LED_SMD:LED_0603_1608Metric", LX, LY + 11.43, 90, {"2": "LED_A", "1": "GND"}, text=((3.81, -1.27, "left"), (3.81, 1.27, "left")))
GND(*pin("D1", "1"))
used = set(U1) | {"36"}
NC("U1", *[n for n in pins_of(load_symbol("MCU_Espressif:ESP32-S3-MINI-1")) if n not in used])

TEXTS += [
    ("Qi receiver + Li-ion charger", 20.32, 40.64),
    ("Qi-present wake detector", 137.16, 127.0),
    ("3.3 V LDO", 175.26, 45.72),
    ("Battery sense", 228.6, 43.18),
    ("TMP117 water temperature", 167.64, 172.72),
    ("ESP32-S3-MINI-1", 304.8, 66.04),
    ("Level ladder electrodes (behind front wall)", 228.6, 172.72),
]


# ===========================================================================
# writer
# ===========================================================================
def eff(size=1.27, justify=None, hide=False):
    e = [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]
    if justify:
        e.append([Sym("justify")] + [Sym(j) for j in justify.split()])
    if hide:
        e.append(Sym("hide"))
    return e


def field_layout(p, sym):
    """Return ((rx, ry, just), (vx, vy, just), hide_ref, hide_val)."""
    x, y, r, t = p["x"], p["y"], p["r"], p["text"]
    if isinstance(t, tuple):
        (rdx, rdy, rj), (vdx, vdy, vj) = t
        return (x + rdx, y + rdy, rj), (x + vdx, y + vdy, vj), False, (vdx, vdy) == (0, 0)
    if t == "l":
        return (x - 2.54, y - 1.27, "right"), (x - 2.54, y + 1.27, "right"), False, False
    if t == "r":
        return (x + 2.54, y - 1.27, "left"), (x + 2.54, y + 1.27, "left"), False, False
    if t == "h":
        return (x, y - 2.54, None), (x, y + 2.54, None), False, False
    if t == "hh":
        return (x, y - 4.45, None), (x, y - 2.54, None), False, False
    if t == "tp":
        if r in (90, 270):
            return (x - 3 if r == 90 else x + 3, y - 2.54, "right" if r == 90 else "left"), (0, 0, None), False, True
        return (x + 1.5, y - 4.5, "left"), (0, 0, None), False, True
    if t == "pwr":
        dx, dy = rot(0, -3.6 if "GND" in p["lib"] else 3.6, r)
        just = None if dx == 0 else ("left" if dx > 0 else "right")
        flag = "FLAG" in p["lib"]
        return (x, y, None), (x + dx, y + dy + (0 if not flag else -1), just), True, flag
    # ic: reference above top-left, value below
    ys = [rot(px, py, r)[1] for px, py in pins_of(sym).values()]
    return (x, y + min(ys) - 3.2, None), (x, y + max(ys) + 3.2, None), False, False


def main():
    lib_symbols, items, pts = {}, [], []
    for p in PARTS:
        if p["lib"] not in lib_symbols:
            lib_symbols[p["lib"]] = load_symbol(p["lib"])
        sym = lib_symbols[p["lib"]]
        allpins = pins_of(sym)
        assert not set(p["nets"]) - set(allpins), (p["ref"], set(p["nets"]) - set(allpins))
        for n in allpins:
            pts.append(pin(p["ref"], n))
        (rx, ry, rj), (vx, vy, vj), hr, hv = field_layout(p, sym)
        virtual = p["ref"].startswith("#")
        # KiCad shows field text rotated with the symbol; give rotated symbols a
        # compensating field angle so all text reads horizontally.
        fa = p["r"] if p["r"] in (90, 270) else 0
        flip = {"left": "right", "right": "left"}
        fj = lambda j: (flip.get(j, j) if p["r"] else j)  # noqa: E731
        props = [
            [Sym("property"), "Reference", p["ref"], [Sym("at"), q(rx), q(ry), fa], eff(justify=fj(rj), hide=hr)],
            [Sym("property"), "Value", p["value"], [Sym("at"), q(vx), q(vy), fa], eff(justify=fj(vj), hide=hv)],
            [Sym("property"), "Footprint", p["fp"], [Sym("at"), p["x"], p["y"], 0], eff(hide=True)],
            [Sym("property"), "Datasheet", "~", [Sym("at"), p["x"], p["y"], 0], eff(hide=True)],
        ] + [[Sym("property"), k, v, [Sym("at"), p["x"], p["y"], 0], eff(hide=True)] for k, v in p["fields"].items()]
        items.append([Sym("symbol"), [Sym("lib_id"), p["lib"]], [Sym("at"), q(p["x"]), q(p["y"]), p["r"]], [Sym("unit"), 1],
                      [Sym("in_bom"), Sym("no" if virtual else "yes")], [Sym("on_board"), Sym("no" if virtual else "yes")],
                      [Sym("dnp"), Sym("no")], [Sym("uuid"), uid(p["ref"])]] + props +
                     [[Sym("pin"), n, [Sym("uuid"), uid(p["ref"], n)]] for n in sorted(allpins)] +
                     [[Sym("instances"), [Sym("project"), "bath_monitor",
                                          [Sym("path"), "/" + ROOT, [Sym("reference"), p["ref"]], [Sym("unit"), 1]]]]])

    # split wires wherever another connection point lands on them, then add junctions
    conn = set(pts) | {(lx, ly) for _, lx, ly, _ in LABELS} | {e for w in WIRES for e in w}
    segs = []
    for a, b in WIRES:
        cuts = sorted([c for c in conn if c not in (a, b) and
                       ((a[0] == b[0] == c[0] and min(a[1], b[1]) < c[1] < max(a[1], b[1])) or
                        (a[1] == b[1] == c[1] and min(a[0], b[0]) < c[0] < max(a[0], b[0])))],
                      key=lambda c: abs(c[0] - a[0]) + abs(c[1] - a[1]))
        chain = [a] + cuts + [b]
        segs += list(zip(chain, chain[1:]))
    count = {}
    for a, b in segs:
        for e in (a, b):
            count[e] = count.get(e, 0) + 1
    for pt in set(pts):
        if pt in count:
            count[pt] += pts.count(pt)
    junctions = sorted(pt for pt, c in count.items() if c >= 3)

    for i, (a, b) in enumerate(segs):
        items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), *a], [Sym("xy"), *b]],
                      [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]], [Sym("uuid"), uid("w", a, b, i)]])
    for j in junctions:
        items.append([Sym("junction"), [Sym("at"), *j], [Sym("diameter"), 0], [Sym("color"), 0, 0, 0, 0], [Sym("uuid"), uid("j", j)]])
    for name, x, y, a in LABELS:
        items.append([Sym("label"), name, [Sym("at"), x, y, a], [Sym("fields_autoplaced")],
                      eff(justify="right bottom" if a == 180 else "left bottom"), [Sym("uuid"), uid("l", name, x, y)]])
    for x, y in NCS:
        items.append([Sym("no_connect"), [Sym("at"), x, y], [Sym("uuid"), uid("nc", x, y)]])
    for t, x, y in TEXTS:
        items.append([Sym("text"), t, [Sym("at"), x, y, 0], eff(size=2.0, justify="left bottom"), [Sym("uuid"), uid("t", t)]])

    sch = [Sym("kicad_sch"), [Sym("version"), 20230121], [Sym("generator"), Sym("eeschema")],
           [Sym("uuid"), ROOT], [Sym("paper"), "A3"],
           [Sym("title_block"), [Sym("title"), "Bath Monitor"], [Sym("date"), "2026-11-19"], [Sym("rev"), "A"],
            [Sym("comment"), 1, "Generated by hardware/tools/gen_schematic.py - edit the script, not this file"]],
           [Sym("lib_symbols")] + list(lib_symbols.values())] + items + \
          [[Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]]]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(dump(sch) + "\n")

    groups = {}
    for p in PARTS:
        if not p["ref"].startswith(("#", "E", "TP")):
            groups.setdefault((" ".join(filter(None, [p["value"], p["fields"].get("Rating")])), p["fp"]), []).append(p["ref"])
    key = lambda r: (r.rstrip("0123456789"), int("".join(c for c in r if c.isdigit()) or 0))  # noqa: E731
    with open(os.path.join(HW, "bom_jlc.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, fp), refs in sorted(groups.items(), key=lambda g: key(sorted(g[1], key=key)[0])):
            w.writerow([val, ",".join(sorted(refs, key=key)), fp.split(":")[-1], ""])
    print(f"wrote {OUT}: {len(PARTS)} symbols, {len(segs)} wires, {len(junctions)} junctions, {len(LABELS)} labels")


if __name__ == "__main__":
    main()
