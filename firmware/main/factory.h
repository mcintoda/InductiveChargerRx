// Per-unit factory data written once at production (tools/flash_unit.py), in its own small flash partition
// "fctry" so a factory reset (which erases the settings NVS) never removes it.
// Format: text, first line "brim-fctry-1", then key=value lines (ap_pass=..., serial=...).
#pragma once
#include <stdbool.h>
#include <stddef.h>

bool factory_get(const char *key, char *out, size_t n);   // false if the partition or key is missing

// Release builds (signed images, or secure boot) refuse to open an unprotected setup network.
#if defined(CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT) || defined(CONFIG_SECURE_BOOT)
#define BRIM_RELEASE 1
#else
#define BRIM_RELEASE 0
#endif
