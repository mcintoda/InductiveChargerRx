# Security review: Wi-Fi, web pages, alerts, firmware update

Scope: `firmware/main/net.c`, `settings.c`, the Wi-Fi and charger parts of `main.c`, and `sdkconfig.defaults`
(rev C firmware, 2026-11-22). Method: code read of every network entry point, then fuzzing the two parsers that
take attacker bytes (setup-mode DNS responder, HTML escaping) on the host under AddressSanitizer/UBSan
(2 M random packets, 100 k random strings: clean).

**Why it matters here:** brim is a safety reminder. The worst realistic outcome isn't data theft, it's someone
silently stopping the BATH FULL alarm (pointing alerts at another server, changing the Wi-Fi, or flashing other
firmware) so the owner trusts a device that no longer warns.

## Entry points

| Where | When it's reachable | Who can reach it |
|---|---|---|
| Setup access point `brim-setup-XXXX` (open), DNS on :53, web form on :80 | First power-up, after a factory reset, or when saved Wi-Fi fails; up to 15 min per wake | Anyone within Wi-Fi range |
| Settings page on the home network (:80): `/`, `/save`, `/test`, `/update` | 10 min after each placement on a Qi pad | Any device on the home network, and (indirectly) any web page open in a browser on it |
| Outbound HTTPS to the ntfy server | Alerts | Network path (TLS-protected) |
| USB-Serial/JTAG test pads, flash chip | Case opened | Physical |

## Findings and status

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | **Unauthenticated firmware upload on the home network.** Any LAN device could POST any image to `/update`; a malicious web page could do it through the owner's browser (a `fetch` with a plain binary body is a "simple" cross-site request). No signature check on the image. | High | **Mitigated:** needs a per-page key in a custom header (cross-site pages can't send it), the Host must be the device's IP (blocks DNS rebinding), and **a double-tap on the device** in the last 2 min. Size checked against the partition, stalled uploads abort. **Still open:** image signing (below) |
| 2 | **Unauthenticated settings change (`/save`), also by cross-site form POST.** Changing the ntfy server or Wi-Fi silently disables every alert. | High | **Fixed:** per-page key in the form, Host check, and double-tap unlock (physical presence) on the home network |
| 3 | **Stored XSS / broken form from unescaped values.** SSID, ntfy host and topic were written into `value='…'` raw. A real SSID like `Dan's Wi-Fi` broke the form, and re-saving it then cut the SSID at the apostrophe and knocked brim off the network. | Medium (also a real bug) | **Fixed:** all values HTML-escaped |
| 4 | **DNS rebinding could read the settings page**, exposing the ntfy topic (anyone with the topic can read your bath times and send fake alerts). | Medium | **Fixed:** Host header must be the device IP (192.168.4.1 in setup) |
| 5 | **Weak randomness for the ntfy topic.** It was generated before the radio started, when `esp_random()` is only a pseudo-random generator. | Medium | **Fixed:** topic and page key are made after `esp_wifi_start()` |
| 6 | **ntfy host not validated.** `user@`, `/path` or other characters could reshape the alert URL. | Low | **Fixed:** host name characters and optional port only |
| 7 | **Form parsing truncation.** A 512-byte body and 96-byte field buffer dropped long or special-character Wi-Fi passwords (URL encoding triples them) without telling the user. | Low (functional) | **Fixed:** whole body read (1 kB cap, rejected above), 200-byte field buffer |
| 8 | **Every firmware update would have been rolled back.** Rollback is enabled but the app never marked itself valid, so the first deep-sleep reset after an update returned to the old image. | Functional | **Fixed:** `esp_ota_mark_app_valid_cancel_rollback()` once startup succeeds |
| 9 | **Home Wi-Fi password travelled over an open setup network.** Someone in radio range during setup could sniff it, or configure the unit first. | Medium | **Fixed:** the setup network is WPA2 (with PMF) using a per-unit password from `tools/provision.py`, stored in its own `fctry` flash partition (a factory reset can't erase it) and printed on the quick start card with a Wi-Fi QR code. Release builds refuse to open a setup network without it; dev builds without factory data stay open and log a warning |
| 10 | **Firmware images weren't signed.** | Medium | **Fixed (release builds):** `sdkconfig.release` requires RSA-3072-signed images at boot and on every upload; the running image's key checks the new one, so an unsigned or foreign upload is rejected. Burns no eFuses. Production adds Secure Boot V2 (below). Verified: the signed build verifies with the key, the unsigned one fails |
| 11 | **Secrets in plain flash; JTAG enabled.** | Low–Medium (physical) | **Fixed (production builds):** `sdkconfig.production` turns on flash encryption (release mode, secure download mode), NVS encryption with an on-chip HMAC key (Wi-Fi password, ntfy topic) and Secure Boot V2, which also disables JTAG. Irreversible eFuse step at first boot: production units only. The setup password in `fctry` stays readable to someone with the opened unit and a flash reader; it is also printed on the card, so that is accepted |
| 12 | **The settings page is plain HTTP on the home network.** Retyping the Wi-Fi password on it is visible to a LAN sniffer. | Low | Accepted (needs a LAN attacker; HTTPS with a self-signed cert would just teach users to click through warnings) |
| 13 | **Alerts go to a public ntfy server by topic name only.** The topic (≈100 bits random) is the only secret; the "brim is charging" alert includes the device's LAN IP. | Low (privacy) | Accepted. Self-hosting ntfy is already supported (server field); an ntfy access-token field would be the next step |

Checked and fine: TLS to ntfy uses the ESP-IDF CA bundle with verification on; the Wi-Fi password is never sent back
to the browser (placeholder "unchanged") and never logged; station auth is WPA2 or better when a password is set;
the DNS responder never writes past its buffer and replies are at most 16 bytes larger than the query (no useful
amplification, and only on the setup network); factory reset needs the device in hand.

## Behaviour the user sees

- **Changing settings or updating firmware:** put brim on its pad, tap the "brim is charging" notification,
  **double-tap brim** (two quick green flashes), then press Save or Upload within 2 minutes. Without the tap the page
  says "Locked". On a board without the accelerometer, the first 2 minutes on the pad count as the unlock.
- **First setup** needs no tap: there is nothing to protect yet, and the device is in the owner's hand.
- A page left open from an earlier session says "Stale page: reload it", because each session gets a new key.

## Builds

| Build | Command | For |
|---|---|---|
| Development | `idf.py build` | Bench boards. Unsigned, open setup network if no factory data |
| Signed release | `idf.py -B build-release -D SDKCONFIG=build-release/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.release" build` | Beta units. Signed images only; no eFuses burned |
| Production | same with `sdkconfig.production` and `-B build-prod` | Units you sell. Secure Boot V2 + flash and NVS encryption; **irreversible** |

All three share one flash layout (partition table at 0xC000, `fctry` at 0x16000), so a unit can move from a signed
release to production by flashing. Boards flashed before 2026-11-23 need a full erase once (`idf.py erase-flash`),
because the partition table moved to make room for the 40 KB production bootloader.

## Signing key

```
espsecure.py generate_signing_key --version 2 --scheme rsa3072 firmware/keys/brim_signing_key.pem
```
`firmware/keys/` is gitignored. Keep the key in a password manager and an offline backup: units only accept images
signed with it, so **losing it means those units can never be updated**, and anyone holding it can sign firmware.

## Production line, per unit

1. Flash the development image through the USB tab, run the functional test (bring-up checklist).
2. `python3 tools/provision.py --port <port> --serial <S/N>`: writes the setup password and serial to `fctry`,
   prints the card text and saves a Wi-Fi QR code (`labels/`). Print the card; delete the label files.
3. Flash the production image (`build-prod`: bootloader, partition table, app). Its first boot burns the eFuses,
   encrypts the flash in place and generates the NVS key. From then on, updates are signed OTA uploads only.
4. Snap off the USB tab, assemble, leak test.
