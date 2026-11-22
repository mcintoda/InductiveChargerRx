// SHTC3 humidity / temperature sensor on the switched rail: measures the air INSIDE the sealed case.
#pragma once
#include "esp_err.h"

esp_err_t shtc3_read(float *temp_c, float *rh);   // wakes the sensor, one normal-mode measurement, sleep
