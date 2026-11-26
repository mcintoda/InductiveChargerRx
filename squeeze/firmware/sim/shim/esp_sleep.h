#pragma once
#include <stdint.h>
#include "esp_err.h"
typedef enum { ESP_SLEEP_WAKEUP_UNDEFINED = 0, ESP_SLEEP_WAKEUP_TIMER = 4 } esp_sleep_wakeup_cause_t;
esp_err_t esp_sleep_enable_timer_wakeup(uint64_t time_in_us);
void esp_deep_sleep_start(void) __attribute__((noreturn));
esp_err_t esp_light_sleep_start(void);
esp_sleep_wakeup_cause_t esp_sleep_get_wakeup_cause(void);
