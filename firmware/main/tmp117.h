// TMP117 water temperature (±0.1 °C), powered from a GPIO only while measuring.
#pragma once
#include "esp_err.h"

// one-shot conversion with 8x averaging; returns degrees C
esp_err_t tmp117_read(float *temp_c);
