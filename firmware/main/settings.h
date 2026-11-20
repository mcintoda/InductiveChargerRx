// User settings in NVS.
#pragma once
#include <stdbool.h>

#include "esp_err.h"

typedef struct {
    char ssid[33];
    char pass[65];
    char topic[33];        // ntfy topic (random, generated at setup)
    char ntfy_host[64];    // default ntfy.sh; a self-hosted server works too
    int alarm_pad;         // 1..6, default 6 (top)
    float temp_limit_c;    // default 42
    bool notify_filling;   // default off
} settings_t;

esp_err_t settings_load(settings_t *s);   // fills defaults if nothing stored
esp_err_t settings_save(const settings_t *s);
esp_err_t settings_erase(void);
bool settings_provisioned(const settings_t *s);
void settings_new_topic(char *out, int len);
