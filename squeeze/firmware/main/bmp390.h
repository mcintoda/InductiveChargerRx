/* Bosch BMP390 barometric pressure sensor on I2C: the squeeze sensor. */
#pragma once
#include <stdbool.h>
#include "esp_err.h"

esp_err_t bmp390_init(void);          /* bus, probe, reset, calibration */
esp_err_t bmp390_start_stream(void);  /* normal mode, 50 Hz, x4 pressure oversampling */
esp_err_t bmp390_read(float *pa);     /* latest sample (normal mode) */
esp_err_t bmp390_one_shot(float *pa); /* forced mode: one sample, ~12 ms, then sleeps */
esp_err_t bmp390_sleep(void);         /* lowest power (~2 uA) */
