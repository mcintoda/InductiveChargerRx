// Wi-Fi, ntfy notifications, setup page and over-the-air updates.
#pragma once
#include <stdbool.h>

#include "esp_err.h"
#include "settings.h"

typedef struct {
    int battery_pct;
    bool charging;
    float temp_c;
    float level_mm;
} net_status_t;

esp_err_t net_init(void);
bool net_wifi_connect(const settings_t *s, int timeout_ms);
void net_wifi_stop(void);
esp_err_t net_ntfy(const settings_t *s, const char *title, const char *msg, int priority, const char *tags);

// First-time setup: access point "brim-setup-XXXX" with a form at http://192.168.4.1.
// Returns after the user saved settings (caller restarts) or after `timeout_ms`.
bool net_provision(settings_t *s, int timeout_ms);
// Settings + firmware update page in station mode (while on the charger).
esp_err_t net_web_start(settings_t *s, const net_status_t *status);
void net_web_stop(void);
bool net_web_saved(void);       // settings changed through the page
bool net_ota_done(void);        // a new firmware image was written (caller restarts)
