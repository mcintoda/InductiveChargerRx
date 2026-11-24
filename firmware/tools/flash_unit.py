#!/usr/bin/env python3
"""Flash a unit in one pass: firmware and its factory data (setup-network password, serial number), and make its card.

    python3 tools/flash_unit.py --port /dev/ttyACM0 --serial A1            # everything, one write (normal case)
    python3 tools/flash_unit.py --port /dev/ttyACM0 --serial A1 --factory-only   # re-provision a flashed unit
    python3 tools/flash_unit.py --mac 7c:df:a1:00:12:34 --serial A1 --dry-run    # card + image only

One esptool write covers the bootloader, partition table, OTA data, app (from --build, default build/: run
`idf.py build` first, or point it at build-prod for production) and the 4 KB 'fctry' image at 0x16000. After that a
unit needs no more cable flashing: bring-up runs over the USB console on the same image, and later firmware goes
over the air (or `idf.py app-flash` while the flash tab is still on).
The password lives only on the unit and its printed card. Labels go to labels/.
"""
import argparse, os, re, secrets, subprocess, sys

FCTRY_OFFSET, FCTRY_SIZE = 0x16000, 0x1000
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no look-alikes (0/o, 1/l/i)


def read_mac(port):
    out = subprocess.run([sys.executable, "-m", "esptool", "--port", port, "read_mac"],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(r"MAC:\s*([0-9a-f:]{17})", out, re.I)
    if not m:
        sys.exit("could not read the MAC address:\n" + out)
    return m.group(1)


def softap_ssid(base_mac):
    b = [int(x, 16) for x in base_mac.split(":")]
    v = int.from_bytes(bytes(b), "big") + 1          # ESP32-S3: soft-AP MAC = base MAC + 1
    b = list(v.to_bytes(6, "big"))
    return "brim-setup-%02X%02X" % (b[4], b[5])


def wifi_qr_text(ssid, pw):
    esc = lambda s: re.sub(r'([\;,:"])', r"\\\1", s)
    return f"WIFI:T:WPA;S:{esc(ssid)};P:{esc(pw)};;"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--mac", help="base (station) MAC, if not reading it from --port")
    ap.add_argument("--serial", required=True)
    ap.add_argument("--dry-run", action="store_true", help="make the image and label, don't flash")
    ap.add_argument("--build", default="build", help="ESP-IDF build directory whose firmware goes in the same write")
    ap.add_argument("--factory-only", action="store_true", help="write only the factory data (unit already flashed)")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]{1,16}", a.serial):
        sys.exit("serial: letters, digits and '-' only, up to 16")
    mac = a.mac or (read_mac(a.port) if a.port else sys.exit("give --port or --mac"))
    ssid = softap_ssid(mac)
    pw = "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3))   # ~59 bits
    text = f"brim-fctry-1\nap_pass={pw}\nserial={a.serial}\n".encode()
    img = text + b"\xff" * (FCTRY_SIZE - len(text))

    os.makedirs("labels", exist_ok=True)
    binp = os.path.join("labels", f"{a.serial}-fctry.bin")
    open(binp, "wb").write(img)
    qr = wifi_qr_text(ssid, pw)
    try:
        import qrcode, qrcode.image.svg
        qrcode.make(qr, image_factory=qrcode.image.svg.SvgPathImage).save(os.path.join("labels", f"{a.serial}-wifi.svg"))
        qr_note = f"labels/{a.serial}-wifi.svg"
    except ImportError:
        qr_note = "(pip install qrcode for an SVG; QR text below)"
    card = (f"brim {a.serial}\nSetup network: {ssid}\nPassword:      {pw}\nQR: {qr_note}\n{qr}\n")
    open(os.path.join("labels", f"{a.serial}-card.txt"), "w").write(card)
    print(card)
    if a.dry_run:
        print(f"dry run: image {binp} not flashed")
        return
    images = [hex(FCTRY_OFFSET), binp]
    opts = []
    if not a.factory_only:
        args_file = os.path.join(a.build, "flash_args")
        if not os.path.exists(args_file):
            sys.exit(f"{args_file} not found: run `idf.py build` (or pass --build / --factory-only)")
        lines = open(args_file).read().split("\n")
        opts = lines[0].split()                       # --flash_mode dio --flash_freq 80m --flash_size 8MB
        for line in lines[1:]:
            if line.strip():
                off, path = line.split(None, 1)
                images[:0] = [off, os.path.join(a.build, path.strip())]
        # secure-boot builds leave the bootloader out of flash_args (ESP-IDF flashes it separately): add the signed
        # one here so production is still a single write
        boot = os.path.join(a.build, "bootloader", "bootloader.bin")
        if "0x0" not in images[::2] and os.path.exists(boot):
            images[:0] = ["0x0", boot]
    subprocess.run([sys.executable, "-m", "esptool", "--chip", "esp32s3", "--port", a.port, "write_flash", *opts, *images],
                   check=True)
    os.remove(binp)                                   # the card is the only other copy
    print("written in one pass. Print the card; keep labels/*.txt only until it is printed.")


if __name__ == "__main__":
    main()
