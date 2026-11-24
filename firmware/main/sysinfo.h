// Firmware version and unexpected restarts (crash, watchdog, brown-out), kept across power cycles.
#pragma once

void sysinfo_boot(void);                   // call once after nvs_flash_init: records an abnormal last reset
const char *sysinfo_version(void);         // git describe of the build, e.g. "a043b57-dirty"
int sysinfo_crashes(void);                 // unexpected restarts since the last factory reset
const char *sysinfo_last_crash(void);      // "brown-out", "crash", "watchdog", or "none"
void sysinfo_clear(void);                  // factory reset
