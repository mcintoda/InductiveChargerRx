#include "settings.h"

#include <string.h>

#include "esp_random.h"
#include "nvs.h"

#define NS "brim"

static void defaults(settings_t *s)
{
    memset(s, 0, sizeof(*s));
    strcpy(s->ntfy_host, "ntfy.sh");
    s->alarm_pad = 6;
    s->temp_limit_c = 42.0f;
}

void settings_new_topic(char *out, int len)
{
    static const char a[] = "abcdefghijkmnpqrstuvwxyz23456789";   // no look-alike characters
    const char *pre = "brim-";
    int n = 0;
    while (pre[n] && n < len - 1) { out[n] = pre[n]; n++; }
    while (n < len - 1 && n < 5 + 20) out[n++] = a[esp_random() % (sizeof(a) - 1)];
    out[n] = 0;
}

esp_err_t settings_load(settings_t *s)
{
    defaults(s);
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) return ESP_OK;
    size_t n;
    n = sizeof(s->ssid); nvs_get_str(h, "ssid", s->ssid, &n);
    n = sizeof(s->pass); nvs_get_str(h, "pass", s->pass, &n);
    n = sizeof(s->topic); nvs_get_str(h, "topic", s->topic, &n);
    n = sizeof(s->ntfy_host); nvs_get_str(h, "host", s->ntfy_host, &n);
    int32_t v;
    if (nvs_get_i32(h, "pad", &v) == ESP_OK && v >= 1 && v <= 6) s->alarm_pad = v;
    if (nvs_get_i32(h, "tlim10", &v) == ESP_OK && v > 200 && v < 600) s->temp_limit_c = v / 10.0f;
    uint8_t b;
    if (nvs_get_u8(h, "fill", &b) == ESP_OK) s->notify_filling = b;
    if (nvs_get_u8(h, "sense", &b) == ESP_OK && b <= SENSE_COMPARE) s->sense_mode = b;
    nvs_close(h);
    return ESP_OK;
}

esp_err_t settings_save(const settings_t *s)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    nvs_set_str(h, "ssid", s->ssid);
    nvs_set_str(h, "pass", s->pass);
    nvs_set_str(h, "topic", s->topic);
    nvs_set_str(h, "host", s->ntfy_host);
    nvs_set_i32(h, "pad", s->alarm_pad);
    nvs_set_i32(h, "tlim10", (int32_t)(s->temp_limit_c * 10));
    nvs_set_u8(h, "fill", s->notify_filling);
    nvs_set_u8(h, "sense", (uint8_t)s->sense_mode);
    err = nvs_commit(h);
    nvs_close(h);
    return err;
}

esp_err_t settings_erase(void)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    nvs_erase_all(h);
    err = nvs_commit(h);
    nvs_close(h);
    return err;
}

bool settings_provisioned(const settings_t *s) { return s->ssid[0] && s->topic[0]; }
