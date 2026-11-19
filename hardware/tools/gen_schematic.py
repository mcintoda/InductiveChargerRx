#!/usr/bin/env python3
"""Generate the Bath Monitor KiCad 7 schematic from a single netlist description.

The schematic is "label-connected": every pin ends in a net label (or a
no-connect flag), so the design intent lives in the PARTS table below and the
drawing can be regenerated at any time.

    python3 hardware/tools/gen_schematic.py
    kicad-cli sch erc hardware/kicad/bath_monitor.kicad_sch

Requires the KiCad 7 symbol libraries (/usr/share/kicad/symbols).
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
NS = uuid.UUID("6f1d3c1e-0b5a-4d8e-9a57-6a3b8f2e1c00")  # stable UUIDs


def uid(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


ROOT = uid("root")

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
TP = "TestPoint:TestPoint_Pad_D1.5mm"

# ---------------------------------------------------------------------------
# Parts: ref, lib_id, value, footprint, (x, y) on sheet in mm, {pin: net},
#        extra fields.  Net None = no-connect flag.  Pins not listed = NC.
# ---------------------------------------------------------------------------
PARTS = []


def part(ref, lib, value, fp, at, pins, **fields):
    PARTS.append(dict(ref=ref, lib=lib, value=value, fp=fp, at=at, pins=pins, fields=fields))


def R(ref, value, at, a, b, fp=R0402, **f):
    part(ref, "Device:R", value, fp, at, {"1": a, "2": b}, **f)


def C(ref, value, at, a, b, fp=C0402, **f):
    part(ref, "Device:C", value, fp, at, {"1": a, "2": b}, **f)


# --- Block A: Qi receiver + Li-ion charger (top-left) ----------------------
X, Y = 55, 72
part("U2", "Battery_Management:BQ51050BRHL", "BQ51050BRHLR", "Package_DFN_QFN:Texas_VQFN-RHL-20_ThermalVias",
     (X, Y), {"1": "GND", "20": "GND", "21": "GND", "2": "AC1", "19": "AC2",
              "3": "BOOT1", "17": "BOOT2", "5": "CLAMP1", "16": "CLAMP2",
              "6": "COMM1", "15": "COMM2", "18": "RECT", "4": "VBAT",
              "7": "CHG_N", "8": None, "9": "GND", "10": "TERM", "11": "GND",
              "12": "ILIM", "14": "FOD", "13": "NTC"},
     MPN="BQ51050BRHLR")
part("J2", "Connector_Generic:Conn_01x02", "Qi_Rx_coil_11uH", "Connector_Wire:SolderWire-0.1sqmm_1x02_P3.6mm_D0.4mm_OD1mm",
     (20, 30), {"1": "COIL_A", "2": "AC2"}, Note="Qi Rx coil ~11uH, ferrite backed, <=32 mm (hand-soldered leads)")
C("C1", "100n 50V X7R", (45, 30), "AC1", "COIL_A", fp=C0805, Note="Series resonant C1 (sum ~233 nF, tune)")
C("C2", "100n 50V X7R", (60, 30), "AC1", "COIL_A", fp=C0805)
C("C3", "33n 50V C0G", (75, 30), "AC1", "COIL_A", fp=C0805)
C("C4", "2.7n 50V C0G", (90, 30), "AC1", "AC2", fp=C0603, Note="Parallel 1 MHz detection cap C2 (tune)")
C("C5", "10n 25V", (15, 115), "BOOT1", "AC1", Note="BOOT1")
C("C6", "10n 25V", (27, 115), "BOOT2", "AC2", Note="BOOT2")
C("C7", "470n 25V", (39, 115), "CLAMP1", "AC1", fp=C0603)
C("C8", "470n 25V", (51, 115), "CLAMP2", "AC2", fp=C0603)
C("C9", "22n 25V", (63, 115), "COMM1", "AC1")
C("C10", "22n 25V", (75, 115), "COMM2", "AC2")
C("C11", "10u 25V", (87, 115), "RECT", "GND", fp=C0805)
C("C12", "100n 25V", (99, 115), "RECT", "GND")
C("C13", "1u 10V", (111, 115), "VBAT", "GND", fp=C0402)
R("R1", "1.05k 1%", (123, 115), "ILIM", "FOD", Note="R_ILIM = R1+R2 = K_ILIM/I_BULK; target 250 mA, verify K_ILIM")
R("R2", "196 1%", (135, 115), "FOD", "GND", Note="R_FOD")
R("R3", "DNP_TBD", (147, 115), "TERM", "GND", Note="R_TERM: set I_TERM ~10% per datasheet")
part("J1", "Connector_Generic:Conn_01x03", "LiPo_500mAh_PCM_NTC", "Connector_Wire:SolderWire-0.1sqmm_1x03_P3.6mm_D0.4mm_OD1mm",
     (105, 70), {"1": "VBAT", "2": "NTC", "3": "GND"},
     Note="1S Li-ion pouch ~500 mAh with protection PCM and 10k NTC lead")

# --- Block B: Qi-present detector + charge status --------------------------
R("R4", "100k", (20, 155), "RECT", "QI_GATE")
R("R5", "100k", (35, 155), "QI_GATE", "GND")
part("Q1", "Transistor_FET:BSS138", "BSS138", "Package_TO_SOT_SMD:SOT-23", (60, 155),
     {"1": "QI_GATE", "2": "GND", "3": "QI_DET_N"})
R("R6", "1M", (80, 155), "+3V3", "QI_DET_N")

# --- Block C: 3.3 V LDO + battery sense ------------------------------------
part("U4", "Regulator_Linear:XC6220B331MR", "XC6220B331MR", "Package_TO_SOT_SMD:SOT-23-5",
     (150, 50), {"1": "VBAT", "3": "VBAT", "2": "GND", "5": "+3V3"},
     Note="1 A, 8 uA Iq. Alt: RT9080-33GJ5")
C("C14", "1u 10V", (120, 50), "VBAT", "GND")
C("C15", "1u 10V", (172, 50), "+3V3", "GND")
R("R7", "1M 1%", (130, 85), "VBAT", "VBAT_SENSE")
R("R8", "1M 1%", (145, 85), "VBAT_SENSE", "GND")
C("C16", "100n", (160, 85), "VBAT_SENSE", "GND")

# --- Block D: ESP32-S3 module ---------------------------------------------
U1 = {"1": "GND", "2": "GND", "3": "+3V3", "45": "EN", "4": "IO0",
      "5": "TOUCH1", "6": "TOUCH2", "7": "TOUCH3", "8": "TOUCH4", "9": "TOUCH5", "10": "TOUCH6",
      "18": "SHIELD_DRV", "13": "VBAT_SENSE", "14": "SDA", "15": "SCL", "16": "SENSE_3V3",
      "17": "QI_DET_N", "19": "CHG_N", "25": "LED_DRV", "23": "USB_DN", "24": "USB_DP"}
U1.update({str(n): "GND" for n in range(42, 66) if n not in (44, 45)})
part("U1", "MCU_Espressif:ESP32-S3-MINI-1", "ESP32-S3-MINI-1-N8", "RF_Module:ESP32-S2-MINI-1",
     (230, 85), U1, MPN="ESP32-S3-MINI-1-N8",
     Note="S2-MINI-1 and S3-MINI-1 share the 15.4x20.5 mm LGA-65 land pattern; verify vs. S3 datasheet")
C("C17", "10u 10V", (270, 50), "+3V3", "GND", fp=C0603)
C("C18", "100n", (285, 50), "+3V3", "GND")
R("R9", "10k", (270, 80), "+3V3", "EN")
C("C19", "1u", (285, 80), "EN", "GND")
R("R10", "1k", (270, 110), "LED_DRV", "LED_A")
part("D1", "Device:LED", "Green", "LED_SMD:LED_0603_1608Metric", (295, 125), {"2": "LED_A", "1": "GND"})

# --- Block E: capacitive level ladder (through-wall, non-contact) ---------
for i in range(1, 7):
    x = 190 + (i - 1) * 14
    R(f"R{10 + i}", "510", (x, 165), f"TOUCH{i}", f"PAD{i}", Note="Espressif-recommended series R")
    part(f"E{i}", "Connector:TestPoint", f"PAD{i}", "BathMonitor:TouchPad_25x8mm", (x, 182),
         {"1": f"PAD{i}"}, Note=f"Level electrode {i} (1 = bottom/wake, 6 = default alarm)")
R("R17", "510", (274, 165), "SHIELD_DRV", "SHIELD")
part("E7", "Connector:TestPoint", "SHIELD", "BathMonitor:ShieldTap", (274, 182), {"1": "SHIELD"},
     Note="Driven shield: L1 hatch around pads + L2 plane behind them")

# --- Block F: TMP117 on isolated tongue ------------------------------------
part("U3", "Sensor_Temperature:TMP117xxDRV", "TMP117AIDRVR", "Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
     (150, 160), {"5": "SENSE_3V3", "2": "GND", "1": "SCL", "6": "SDA", "4": "GND", "3": None},
     MPN="TMP117AIDRVR", Note="I2C 0x48. Powered from GPIO12 only while measuring")
C("C20", "100n", (120, 155), "SENSE_3V3", "GND")
R("R18", "10k", (130, 185), "SENSE_3V3", "SDA")
R("R19", "10k", (145, 185), "SENSE_3V3", "SCL")

# --- Block G: test pads + power flags -------------------------------------
for i, net in enumerate(["+3V3", "GND", "EN", "IO0", "USB_DP", "USB_DN", "VBAT", "RECT"], 1):
    part(f"TP{i}", "Connector:TestPoint", net, TP, (330 + (i - 1) % 4 * 15, 40 + (i - 1) // 4 * 20), {"1": net})
for i, net in enumerate(["GND", "SENSE_3V3"], 1):
    part(f"#FLG0{i}", "power:PWR_FLAG", "PWR_FLAG", "", (330 + (i - 1) * 15, 90), {"1": net})

TEXTS = [
    ("A. Qi receiver + Li-ion charger (BQ51050B)", 15, 15),
    ("B. Qi-present wake detector", 15, 135),
    ("C. 3.3 V LDO + battery sense", 115, 15),
    ("D. ESP32-S3-MINI-1 (Wi-Fi, touch, native USB via test pads)", 190, 15),
    ("E. Level ladder: 6 electrodes behind the front wall + driven shield", 185, 140),
    ("F. TMP117 water temperature (isolated PCB tongue, bottom)", 115, 135),
    ("G. Pogo test pads / ERC flags", 325, 15),
]

# ---------------------------------------------------------------------------
_libcache = {}


def load_symbol(lib_id):
    lib, name = lib_id.split(":")
    if lib not in _libcache:
        _libcache[lib] = parse(open(os.path.join(SYMDIR, lib + ".kicad_sym")).read())
    syms = {s[1]: s for s in find(_libcache[lib], "symbol")}
    s = syms[name]
    ext = find(s, "extends")
    if ext:  # flatten: parent graphics/pins + child properties
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
        body += list(props.values())
        s = [Sym("symbol"), name] + body
    return [Sym("symbol"), lib_id] + [e for e in s[2:]]


def pins_of(sym):
    out = {}
    for u in find(sym, "symbol"):
        for p in find(u, "pin"):
            at = find(p, "at")[0]
            out.setdefault(find(p, "number")[0][1], (float(at[1]), float(at[2]), int(float(at[3])) if len(at) > 3 else 0))
    return out


def eff(size=1.27, justify=None, hide=False):
    e = [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]
    if justify:
        e.append([Sym("justify")] + [Sym(j) for j in justify.split()])
    if hide:
        e.append(Sym("hide"))
    return e


def main():
    lib_symbols, items, nets = {}, [], {}
    for p in PARTS:
        if p["lib"] not in lib_symbols:
            lib_symbols[p["lib"]] = load_symbol(p["lib"])
        sym = lib_symbols[p["lib"]]
        pins = pins_of(sym)
        x0, y0 = p["at"]
        x0, y0 = round(x0 / 2.54) * 2.54, round(y0 / 2.54) * 2.54  # snap to grid
        unknown = set(p["pins"]) - set(pins)
        assert not unknown, (p["ref"], unknown)
        power = p["ref"].startswith("#")
        props = [
            [Sym("property"), "Reference", p["ref"], [Sym("at"), x0 + 3, y0 - 2, 0], eff(justify="left", hide=power)],
            [Sym("property"), "Value", p["value"], [Sym("at"), x0 + 3, y0 + 2, 0], eff(justify="left", hide=power)],
            [Sym("property"), "Footprint", p["fp"], [Sym("at"), x0, y0, 0], eff(hide=True)],
            [Sym("property"), "Datasheet", "~", [Sym("at"), x0, y0, 0], eff(hide=True)],
        ]
        for k, v in p["fields"].items():
            props.append([Sym("property"), k, v, [Sym("at"), x0, y0, 0], eff(hide=True)])
        items.append([Sym("symbol"), [Sym("lib_id"), p["lib"]], [Sym("at"), x0, y0, 0], [Sym("unit"), 1],
                      [Sym("in_bom"), Sym("no" if power else "yes")], [Sym("on_board"), Sym("no" if power else "yes")],
                      [Sym("dnp"), Sym("no")], [Sym("uuid"), uid(p["ref"])]] + props +
                     [[Sym("pin"), n, [Sym("uuid"), uid(p["ref"], n)]] for n in sorted(pins)] +
                     [[Sym("instances"), [Sym("project"), "bath_monitor",
                                          [Sym("path"), "/" + ROOT, [Sym("reference"), p["ref"]], [Sym("unit"), 1]]]]])
        done = set()
        for num, (px, py, ang) in pins.items():
            sx, sy = round(x0 + px, 2), round(y0 - py, 2)
            if (sx, sy) in done:
                continue  # stacked pins (e.g. module GND)
            done.add((sx, sy))
            net = p["pins"].get(num)
            if net is None:
                items.append([Sym("no_connect"), [Sym("at"), sx, sy], [Sym("uuid"), uid("nc", p["ref"], num)]])
                continue
            nets.setdefault(net, []).append(f"{p['ref']}.{num}")
            la = (ang + 180) % 360
            just = "right bottom" if la in (180, 270) else "left bottom"
            items.append([Sym("label"), net, [Sym("at"), sx, sy, la], [Sym("fields_autoplaced")],
                          eff(justify=just), [Sym("uuid"), uid("lbl", p["ref"], num)]])
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

    single = [n for n, v in nets.items() if len(v) < 2]
    if single:
        print("WARNING single-pin nets:", single)

    # JLCPCB-style BOM grouped by value+footprint
    groups = {}
    for p in PARTS:
        if p["ref"].startswith("#") or p["ref"].startswith(("E", "TP")):
            continue
        groups.setdefault((p["value"], p["fp"]), []).append(p["ref"])
    with open(os.path.join(HW, "bom_jlc.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, fp), refs in sorted(groups.items(), key=lambda g: g[1][0]):
            w.writerow([val, ",".join(sorted(refs, key=lambda r: (r.rstrip("0123456789"), int(''.join(c for c in r if c.isdigit()) or 0)))), fp.split(":")[-1], ""])
    print(f"wrote {OUT}: {len(PARTS)} symbols, {len(nets)} nets")


if __name__ == "__main__":
    main()
