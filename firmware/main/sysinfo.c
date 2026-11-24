#include "sysinfo.h"

#include "esp_app_desc.h"
#include "esp_system.h"
#include "settings.h"

static int s_crashes = -1;
static uint8_t s_last;

static const char *reason_name(int r)
{
    switch (r) {
    case ESP_RST_BROWNOUT: return "brown-out";
    case ESP_RST_PANIC: return "crash";
    case ESP_RST_INT_WDT: case ESP_RST_TASK_WDT: case ESP_RST_WDT: return "watchdog";
    default: return "none";
    }
}

void sysinfo_boot(void)
{
    uint8_t rec[2] = {0, 0};                         // {count (saturating), last reason}
    store_load("crash", rec, sizeof(rec));
    esp_reset_reason_t r = esp_reset_reason();
    if (r == ESP_RST_BROWNOUT || r == ESP_RST_PANIC || r == ESP_RST_INT_WDT || r == ESP_RST_TASK_WDT || r == ESP_RST_WDT) {
        if (rec[0] < 255) rec[0]++;
        rec[1] = (uint8_t)r;
        store_save("crash", rec, sizeof(rec));
    }
    s_crashes = rec[0];
    s_last = rec[1];
}

const char *sysinfo_version(void) { return esp_app_get_description()->version; }
int sysinfo_crashes(void) { return s_crashes < 0 ? 0 : s_crashes; }
const char *sysinfo_last_crash(void) { return reason_name(s_last); }

void sysinfo_clear(void)
{
    uint8_t rec[2] = {0, 0};
    store_save("crash", rec, sizeof(rec));
    s_crashes = 0;
    s_last = 0;
}
