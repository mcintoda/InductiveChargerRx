// Battery, charger and LED.
#pragma once
#include <stdbool.h>

#include "esp_err.h"

esp_err_t power_init(void);
int power_battery_mv(void);              // -1 on error
int power_battery_pct(int mv);           // rough Li-ion state of charge from voltage at light load
bool power_on_charger(void);             // QI_DET_N low: a Qi pad is powering the receiver
bool power_charging(void);               // CHG_N low: the BQ51050B is charging
void power_led(bool on);
