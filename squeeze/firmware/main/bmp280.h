/* Bosch BMP280 barometric pressure sensor on I2C: the squeeze sensor. */
#pragma once
#include "esp_err.h"

esp_err_t bmp280_init(void);          /* probe, reset, calibration */
esp_err_t bmp280_start_stream(void);  /* normal mode, ~70 Hz, x4 pressure oversampling */
esp_err_t bmp280_read(float *pa);     /* latest sample (normal mode) */
esp_err_t bmp280_one_shot(float *pa); /* forced mode: one sample, ~14 ms, then sleeps */
esp_err_t bmp280_sleep(void);         /* ~0.1 uA */
