#include "bmp280_comp.h"

void bmp280_parse_calib(const uint8_t b[24], bmp280_calib_t *c)
{
#define U16(i) ((uint16_t)(b[i] | b[(i) + 1] << 8))
#define S16(i) ((int16_t)U16(i))
    c->t1 = U16(0);
    c->t2 = S16(2);
    c->t3 = S16(4);
    c->p1 = U16(6);
    c->p2 = S16(8);
    c->p3 = S16(10);
    c->p4 = S16(12);
    c->p5 = S16(14);
    c->p6 = S16(16);
    c->p7 = S16(18);
    c->p8 = S16(20);
    c->p9 = S16(22);
#undef U16
#undef S16
}

double bmp280_compensate(const bmp280_calib_t *c, int32_t adc_p, int32_t adc_t, double *temp_c)
{
    double v1 = ((double)adc_t / 16384.0 - (double)c->t1 / 1024.0) * (double)c->t2;
    double v2 = ((double)adc_t / 131072.0 - (double)c->t1 / 8192.0);
    v2 = v2 * v2 * (double)c->t3;
    double t_fine = v1 + v2;
    if (temp_c)
        *temp_c = t_fine / 5120.0;

    v1 = t_fine / 2.0 - 64000.0;
    v2 = v1 * v1 * (double)c->p6 / 32768.0;
    v2 = v2 + v1 * (double)c->p5 * 2.0;
    v2 = v2 / 4.0 + (double)c->p4 * 65536.0;
    v1 = ((double)c->p3 * v1 * v1 / 524288.0 + (double)c->p2 * v1) / 524288.0;
    v1 = (1.0 + v1 / 32768.0) * (double)c->p1;
    if (v1 == 0.0)
        return 0.0;
    double p = 1048576.0 - (double)adc_p;
    p = (p - v2 / 4096.0) * 6250.0 / v1;
    v1 = (double)c->p9 * p * p / 2147483648.0;
    v2 = p * (double)c->p8 / 32768.0;
    return p + (v1 + v2 + (double)c->p7) / 16.0;
}
