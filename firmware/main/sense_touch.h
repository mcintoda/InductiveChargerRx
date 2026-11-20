// ESP32-S3 touch peripheral: 7 electrodes, driven shield on T14, idle channels high-impedance.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "level.h"

esp_err_t sense_init(void);
// average `n` FSM readings of all 7 channels (raw counts rise with capacitance)
esp_err_t sense_read(uint32_t raw[LVL_CH], int n);
// arm PAD1 as the deep-sleep wake channel: wake when its count rises by `delta_counts`
esp_err_t sense_arm_wake(uint32_t delta_counts);
