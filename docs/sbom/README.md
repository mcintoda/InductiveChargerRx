# brim firmware SBOM and vulnerability check

| File | Format |
|---|---|
| [`brim-firmware.spdx`](brim-firmware.spdx) | SPDX 2.3 tag-value |
| [`brim-firmware.cdx.json`](brim-firmware.cdx.json) | CycloneDX 1.6 JSON |
| [`nvd-check-2026-11-23.txt`](nvd-check-2026-11-23.txt) | NVD scan of the SBOM above |

Generated from the **production** build (`sdkconfig.production`) with Espressif's
[`esp-idf-sbom`](https://github.com/espressif/esp-idf-sbom) 1.5.0. The project builds only `main` and its
dependencies (`set(COMPONENTS main)` in `firmware/CMakeLists.txt`), so the SBOM lists exactly what ships: 66 packages.

## Third-party code in the image

| Package | Version | Role in brim |
|---|---|---|
| ESP-IDF | **5.3.6** | SDK, drivers, OTA, NVS, HTTP server/client |
| Mbed TLS | **3.6.7** | TLS 1.2/1.3 client to the ntfy server, image signature checks |
| wpa_supplicant (ESP port) | 2.10 | WPA2-PSK station and setup access point |
| lwIP | 2.1.3 | TCP/IP, DHCP server for the setup network |
| FreeRTOS | 10.5.1 | Kernel |
| newlib | 4.3.0 | C library |
| micro-ecc | 1.1 | Bootloader support (not used for signing; brim uses RSA-3072) |
| Espressif Wi-Fi / PHY / coexistence blobs | 5.3.6 | Binary radio libraries (no CPE: not checkable against NVD) |

## Result (2026-11-23)

**After upgrading ESP-IDF 5.3.2 → 5.3.6: 0 CVEs** (NVD REST API, 57 packages with CPEs; no CISA KEV entries).

Before the upgrade the same check found **25 CVEs** (6 critical, 7 high, 11 medium, 1 low) in Mbed TLS 3.6.2,
ESP-IDF 5.3.2 and wpa_supplicant 2.10. All are fixed in 5.3.6 (which bundles Mbed TLS 3.6.7). How they applied to brim:

| CVE(s) | Score | What | Reachable in brim before the fix? |
|---|---|---|---|
| CVE-2026-34874 | 7.5 | Mbed TLS NULL write in distinguished-name parsing | **Yes**: a man-in-the-middle could send a crafted certificate chain during the TLS handshake to the ntfy server (crash, before verification) |
| CVE-2026-25835, CVE-2026-34871 | 7.7, 6.7 | Mbed TLS PRNG seeding | **Possibly**: weaker randomness in TLS |
| CVE-2026-25834 | 6.5 | Mbed TLS algorithm downgrade | **Possibly**, in the TLS client |
| CVE-2025-27810 | 5.4 | Uninitialised Finished message after allocation failure | Low: needs out-of-memory mid-handshake |
| CVE-2026-25833 | 7.5 | Overflow in `x509_inet_pton_ipv6` | Only if the ntfy server is set as an IPv6 literal |
| CVE-2026-34872, -34875 | 9.1, 9.8 | Finite-field DH (DHE) issues | Low: needs a malicious server that holds a trusted certificate |
| CVE-2025-27809 | 5.4 | Hostname not checked unless set | No: esp-tls always sets the hostname |
| CVE-2026-34873, -34877, CVE-2025-47917, -48965, -49600, -49601, -52496, -52497, -54764, -59438, -66442, -49087, CVE-2026-34876 | 4.0–9.8 | Server-side session resumption, context serialisation, certificate writing, LMS, x86 AES-NI, PEM, local timing, LLVM-only, PKCS#7 CBC, multipart CCM API | No: features or platforms brim doesn't use |
| CVE-2025-66409, CVE-2025-55297 | 9.1, 8.8 | ESP-IDF Bluetooth AVRCP, BluFi example | No: Bluetooth isn't built |
| CVE-2023-52160 | 6.5 | wpa_supplicant PEAP bypass | No: WPA2-PSK only (enterprise Wi-Fi not used) |

Other sources checked:
- **OSV.dev** (by git tag): one lwIP hit, CVE-2026-8836, in the SNMPv3 agent, which ESP-IDF doesn't build. Not applicable.
- **Espressif security advisories**: AR2026-006 (ECDSA secure boot bypass) affects H2/C5/C61/P4/S31, not the S3,
  and brim uses RSA secure boot anyway. AR2026-005 (AES key recovery from the ESP32-S3's general-purpose AES block by
  voltage fault injection) needs the unit opened and glitching equipment; brim's stored secrets are protected by flash
  encryption (XTS) and the HMAC-derived NVS key rather than that block. AR2026-001 (XTS-AES side channel, "ESP32-C5 and
  other series") is a lab-grade power-analysis attack: accepted for a bath sensor, re-check if the S3 is listed.
- **Not covered by any CVE database**: Espressif's binary Wi-Fi/PHY libraries. Track Espressif's advisories for those.

## Re-running

```
cd firmware && . $IDF_PATH/export.sh && pip install esp-idf-sbom
idf.py -B build-prod -D SDKCONFIG=build-prod/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.production" build
python -m esp_idf_sbom create --rem-unused --files rem -o ../docs/sbom/brim-firmware.spdx build-prod/project_description.json
NVDAPIKEY=... python -m esp_idf_sbom check ../docs/sbom/brim-firmware.spdx     # free NVD key: ~10x faster
```
Re-run before each release and monthly while units are in the field, and move to each new ESP-IDF v5.3.x bug-fix
release (or v5.5.x) promptly: Espressif ships Mbed TLS and Wi-Fi fixes through them. ESP-IDF v5.3 is supported
until roughly mid-2027; plan the move to v5.5 before then.
