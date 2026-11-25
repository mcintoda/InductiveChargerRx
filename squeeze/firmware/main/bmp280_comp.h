/* BMP280 compensation (Bosch BMP280 datasheet BST-BMP280-DS001, section 8.1, double precision).
 * Pure C: host-tested against the datasheet's worked example (section 3.12). */
#pragma once
#include <stdint.h>

typedef struct {
    uint16_t t1;
    int16_t t2, t3;
    uint16_t p1;
    int16_t p2, p3, p4, p5, p6, p7, p8, p9;
} bmp280_calib_t;

/* 24 bytes read from 0x88..0x9F */
void bmp280_parse_calib(const uint8_t b[24], bmp280_calib_t *c);
/* 20-bit raw readings -> Pa (and deg C via *temp_c when not NULL). */
double bmp280_compensate(const bmp280_calib_t *c, int32_t adc_p, int32_t adc_t, double *temp_c);
