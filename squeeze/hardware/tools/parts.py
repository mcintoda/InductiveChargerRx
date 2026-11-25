"""squeeze main board: every part, its footprint, value, LCSC number and pin -> net map.

This file is the single source of truth for the electronics. gen_pcb.py builds the board from it,
jlc_outputs.py builds the JLC BOM from it, and netlist_doc.py renders it for review
(docs/schematic.md). The circuit blocks are explained in docs/design.md section 5.

LCSC numbers: the ICs, connectors and special parts were looked up on lcsc.com (Nov 2026).
Plain resistors and capacitors carry no number: JLC's BOM matcher fills them from the comment
(value, package, rating), and you confirm each line on the order page.
"""
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
WIRE2 = "Squeeze:Wire_1x02_P3.6mm_D0.5mm"
WIRE2_BIG = "Squeeze:Wire_1x02_P2.5mm_D0.8mm"
WIRE3 = "Squeeze:Wire_1x03_P2.0mm_D0.7mm"
WIRE4 = "Squeeze:Wire_1x04_P1.6mm_D0.5mm"
TP = "TestPoint:TestPoint_Pad_D1.0mm"

PARTS = []


def P(ref, fp, value, nets, lcsc="", rating="", note="", placed=True):
    PARTS.append(dict(ref=ref, fp=fp, value=value, nets=nets, lcsc=lcsc, rating=rating, note=note, placed=placed))


def R(ref, value, a, b, note=""):
    P(ref, R0402, value, {"1": a, "2": b}, rating="1% 0402", note=note)


def C(ref, value, a, b, fp=C0402, rating="", note=""):
    P(ref, fp, value, {"1": a, "2": b}, rating=rating, note=note)


GND = "GND"

# ---------------------------------------------------------------- ESP32-C3 module
ESP_GND = ["1", "2", "11", "14"] + [str(n) for n in range(36, 54)]
P("U1", "Squeeze:ESP32-C3-MINI-1U", "ESP32-C3-MINI-1U-N4",
  {**{n: GND for n in ESP_GND},
   "3": "+3V3", "8": "EN",
   "12": "VBAT_SENSE",   # GPIO0  ADC1_CH0
   "13": "VBUS_SENSE",   # GPIO1  USB plugged in (stay awake)
   "5": "IO2",           # GPIO2  strapping: pulled up, unused
   "6": "LED_R",         # GPIO3  (LED cathodes, active low)
   "18": "LED_G",        # GPIO4
   "19": "LED_B",        # GPIO5
   "20": "SDA",          # GPIO6
   "21": "SCL",          # GPIO7
   "22": "CHG_N",        # GPIO8  strapping: pulled up (also the charger's open-drain CHG)
   "23": "BOOT",         # GPIO9  strapping: internal pull-up, test pad to GND for recovery
   "16": "SERVO_PWM",    # GPIO10
   "26": "USB_DN",       # GPIO18
   "27": "USB_DP",       # GPIO19
   "30": "SERVO_EN",     # GPIO20
   "31": "TXD",          # GPIO21 U0TXD test pad
   },
  lcsc="C2911374", note="External antenna on the module's U.FL: adhesive 2.4 GHz FPC antenna (hand part)")
C("C30", "10uF", "+3V3", GND, fp=C0603, rating="10V X5R 0603")
C("C31", "100nF", "+3V3", GND, rating="16V X7R 0402")
R("R30", "10k", "+3V3", "EN", note="EN pull-up; with C32 a ~10 ms reset delay")
C("C32", "1uF", "EN", GND, rating="10V X5R 0402")
R("R31", "10k", "+3V3", "IO2")
R("R32", "10k", "+3V3", "CHG_N")

# ---------------------------------------------------------------- Qi receiver + charger (brim rev C block)
P("U2", "Package_DFN_QFN:Texas_VQFN-RHL-20", "BQ51050BRHLR",
  {"1": GND, "20": GND, "21": GND, "2": "AC1", "19": "AC2", "3": "BOOT1", "17": "BOOT2",
   "5": "CLAMP1", "16": "CLAMP2", "6": "COMM1", "15": "COMM2", "18": "RECT", "4": "VBAT",
   "7": "CHG_N", "8": None, "9": GND, "10": "TERM", "11": GND, "12": "ILIM", "14": "FOD", "13": "NTC"},
  lcsc="C133307", note="AD (9) and EN2 (11) grounded, AD-EN (8) open: as brim")
P("L1", WIRE2, "TDK WR303050-12F5-ID", {"1": "COIL_A", "2": "AC2"}, lcsc="C6357742", placed=False,
  note="Qi coil on the base floor under the board; its two leads come up through these holes (hand-soldered)")
C("C1", "100nF", "COIL_A", "AC1", fp=C0603, rating="50V X7R 0603", note="series resonance: 3 x 100n + 10n = 310 nF")
C("C2", "100nF", "COIL_A", "AC1", fp=C0603, rating="50V X7R 0603")
C("C3", "100nF", "COIL_A", "AC1", fp=C0603, rating="50V X7R 0603")
C("C23", "10nF", "COIL_A", "AC1", rating="50V X7R 0402")
C("C4", "3.3nF", "AC1", "AC2", fp=C0603, rating="50V C0G 0603", note="parallel (detection) resonance ~1 MHz")
C("C5", "10nF", "AC1", "BOOT1", rating="50V X7R 0402")
C("C6", "10nF", "AC2", "BOOT2", rating="50V X7R 0402")
C("C7", "470nF", "AC1", "CLAMP1", fp=C0603, rating="25V X7R 0603")
C("C8", "470nF", "AC2", "CLAMP2", fp=C0603, rating="25V X7R 0603")
C("C9", "22nF", "AC1", "COMM1", rating="50V X7R 0402")
C("C10", "22nF", "AC2", "COMM2", rating="50V X7R 0402")
C("C11", "10uF", "RECT", GND, fp=C0805, rating="25V X5R 0805")
C("C21", "10uF", "RECT", GND, fp=C0805, rating="25V X5R 0805")
C("C12", "100nF", "RECT", GND, rating="50V X7R 0402")
R("R1", "1.37k", "ILIM", "FOD", note="R_ILIM = R1 + R2 = 1.566k -> I_BULK = 314 / 1566 = 200 mA (0.5C for 400 mAh)")
R("R2", "196", "FOD", GND, note="R_FOD, as brim")
R("R3", "10k", "TERM", GND, note="termination ~42 % of I_BULK, as brim")
P("TH1", R0402, "10k NTC B3380", {"1": "NTC", "2": GND}, lcsc="C77131", rating="",
  note="Murata NCP15XH103F03RC: board temperature for the charger's TS input")
C("C13", "1uF", "VBAT", GND, rating="10V X5R 0402")
C("C22", "100nF", "VBAT", GND, rating="16V X7R 0402")
P("J1", WIRE2_BIG, "Battery 503030", {"1": "VBAT", "2": GND}, placed=False,
  note="1S LiPo ~400 mAh with protection PCM: red to 1 (VBAT), black to 2")
R("R4", "1M", "VBAT", "VBAT_SENSE")
R("R5", "1M", "VBAT_SENSE", GND)
C("C24", "100nF", "VBAT_SENSE", GND, rating="16V X7R 0402")

# ---------------------------------------------------------------- 3.3 V
P("U3", "Package_TO_SOT_SMD:TSOT-23-5", "RT9080-33GJ5", {"1": "VBAT", "3": "VBAT", "2": GND, "5": "+3V3", "4": None},
  lcsc="C841192", note="600 mA LDO, 2 uA Iq (as brim)")
C("C14", "1uF", "VBAT", GND, rating="10V X5R 0402")
C("C15", "1uF", "+3V3", GND, rating="10V X5R 0402")

# ---------------------------------------------------------------- squeeze sensor
P("U4", "Package_LGA:Bosch_LGA-8_2x2.5mm_P0.65mm_ClockwisePinNumbering", "BMP280",
  {"1": GND, "2": "+3V3", "3": "SDA", "4": "SCL", "5": GND, "6": "+3V3", "7": GND, "8": "+3V3"},
  lcsc="C83291", note="I2C address 0x76 (SDO to GND), CSB high = I2C. Keep its vent hole free of coating")
C("C25", "100nF", "+3V3", GND, rating="16V X7R 0402")
R("R6", "4.7k", "+3V3", "SDA")
R("R7", "4.7k", "+3V3", "SCL")

# ---------------------------------------------------------------- servo supply: 5 V boost, true shutdown
P("U5", "Package_TO_SOT_SMD:SOT-563", "TPS61023DRLR",
  {"1": "FB", "2": "SERVO_EN", "3": "VBAT", "4": GND, "5": "SW", "6": "+5V"},
  lcsc="C919459", note="EN low: output fully disconnected (0.1 uA), so no load switch is needed")
P("L2", "Inductor_SMD:L_Cenker_CKCS4030", "1uH", {"1": "VBAT", "2": "SW"}, lcsc="C5291823", rating="4030 shielded",
  note="CENKER CKCS4030-1uH/N, 4 x 4 x 3 mm")
C("C16", "10uF", "VBAT", GND, fp=C0603, rating="10V X5R 0603")
C("C17", "22uF", "+5V", GND, fp=C0805, rating="10V X5R 0805")
C("C18", "22uF", "+5V", GND, fp=C0805, rating="10V X5R 0805")
C("C19", "22uF", "+5V", GND, fp=C0805, rating="10V X5R 0805")
R("R8", "732k", "+5V", "FB", note="VOUT = 0.595 V x (1 + 732k/100k) = 4.95 V (TPS61023 datasheet eq. 4)")
R("R9", "100k", "FB", GND)
R("R10", "100k", "SERVO_EN", GND, note="servo supply off while the ESP32 boots or sleeps")
R("R11", "100", "SERVO_PWM", "SERVO_SIG")
P("J2", WIRE3, "Servo SG90", {"1": "+5V", "2": GND, "3": "SERVO_SIG"}, placed=False,
  note="cut the servo plug off: red to 1, brown to 2, orange to 3")

# ---------------------------------------------------------------- USB-C (flashing; also tells the firmware to stay awake)
P("J3", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", "TYPE-C-31-M-12",
  {"A1": GND, "B1": GND, "A12": GND, "B12": GND, "S1": GND, "A4": "VBUS", "B4": "VBUS", "A9": "VBUS", "B9": "VBUS",
   "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN", "A8": None, "B8": None},
  lcsc="C165948", note="data only: VBUS powers nothing, it is only sensed. Battery must be fitted to flash")
R("R12", "5.1k", "CC1", GND)
R("R13", "5.1k", "CC2", GND)
R("R14", "56k", "VBUS", "VBUS_SENSE", note="5 V -> 3.2 V: a clean logic high (ESP32-C3 VIH = 0.75 x 3.3 = 2.48 V), < 3.6 V at 5.25 V")
R("R15", "100k", "VBUS_SENSE", GND)

# ---------------------------------------------------------------- RGB LED (on the break-off tab, wired to J4)
R("R16", "220", "LED_R", "LED_RK")
R("R17", "68", "LED_G", "LED_GK")
R("R18", "68", "LED_B", "LED_BK")
P("J4", WIRE4, "LED wires", {"1": "+3V3", "2": "LED_RK", "3": "LED_GK", "4": "LED_BK"}, placed=False,
  note="4 thin wires up the chassis post to J5 on the LED tab")
P("D1", "Squeeze:LED_RGB_1615_XINGLIGHT", "XL-1615RGBC-RF",
  {"1": "TAB_A", "2": "TAB_R", "3": "TAB_G", "4": "TAB_B"}, lcsc="C965840", note="common anode, on the break-off tab")
P("J5", WIRE4, "LED tab wires", {"1": "TAB_A", "2": "TAB_R", "3": "TAB_G", "4": "TAB_B"}, placed=False)

# ---------------------------------------------------------------- test pads
for ref, net in (("TP1", "BOOT"), ("TP2", "TXD"), ("TP3", GND), ("TP5", "+3V3"), ("TP6", "+5V"),
                 ("TP7", "RECT")):
    P(ref, TP, net, {"1": net}, placed=False)


def nets():
    out = {}
    for p in PARTS:
        for pin, n in p["nets"].items():
            if n:
                out.setdefault(n, []).append((p["ref"], pin))
    return out


if __name__ == "__main__":
    ns = nets()
    for n in sorted(ns):
        print(f"{n:12s} {len(ns[n]):3d}  " + " ".join(f"{r}.{p}" for r, p in ns[n][:10]))
    bad = [n for n, m in ns.items() if len({r for r, _ in m}) < 2]
    print(len(PARTS), "parts,", len(ns), "nets; single-part nets:", bad)
