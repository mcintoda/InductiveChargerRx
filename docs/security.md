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
| 9 | **Home Wi-Fi password travels over an open setup network.** The setup AP has no password and the form is plain HTTP, so someone in radio range during setup could sniff the password, or configure the device before the owner does. | Medium | **Open.** Window is short (only during setup). Fix options: a WPA2 setup network with a per-device password printed on a card in the box (simplest), or ESP-IDF unified provisioning (SRP6a + proof-of-possession), which needs an app |
| 10 | **Firmware images aren't signed.** Even with the unlock, a LAN attacker who catches the 2-minute window (or the owner tricked into uploading a bad file) can flash anything. | Medium | **Open (release step).** Turn on `CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT` + `CONFIG_SECURE_SIGNED_ON_UPDATE_NO_SECURE_BOOT` (ECDSA) with a signing key kept **outside the repo**; for production use Secure Boot v2 |
| 11 | **Secrets in plain flash.** Wi-Fi password and topic are stored unencrypted in NVS; USB-JTAG is enabled. Anyone who opens a discarded unit can read the home Wi-Fi password. | Low–Medium (physical) | **Open (release step).** Flash encryption + NVS encryption, disable JTAG by eFuse in production. Tell users to factory-reset before giving a unit away |
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

## Before shipping units to other people

1. Signed app images (finding 10), signing key in a password manager, not the repo.
2. Flash + NVS encryption and JTAG disabled (finding 11).
3. WPA2 setup network with a printed per-device password (finding 9).
