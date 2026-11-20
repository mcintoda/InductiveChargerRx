#include "rate.h"

#include <string.h>

void rate_init(rate_t *r, float window_s)
{
    memset(r, 0, sizeof(*r));
    r->window_s = window_s;
}

void rate_add(rate_t *r, float t_s, float level_mm)
{
    r->t[r->head] = t_s;
    r->y[r->head] = level_mm;
    r->head = (r->head + 1) % RATE_N;
    if (r->n < RATE_N) r->n++;
}

bool rate_mm_per_min(const rate_t *r, float *out)
{
    if (r->n < 3) return false;
    int newest = (r->head - 1 + RATE_N) % RATE_N;
    float t_end = r->t[newest];
    double st = 0, sy = 0, stt = 0, sty = 0, t_min = t_end;
    int n = 0;
    for (int i = 0; i < r->n; i++) {
        float t = r->t[i];
        if (t_end - t > r->window_s) continue;
        double tt = t - t_end;
        st += tt; sy += r->y[i]; stt += tt * tt; sty += tt * r->y[i]; n++;
        if (t < t_min) t_min = t;
    }
    if (n < 3 || (t_end - t_min) < r->window_s / 2) return false;
    double den = n * stt - st * st;
    if (den <= 0) return false;
    *out = (float)((n * sty - st * sy) / den * 60.0);
    return true;
}

float rate_eta_s(const rate_t *r, float level_mm, float target_mm)
{
    float v;
    if (!rate_mm_per_min(r, &v) || v <= 0.05f) return -1;
    if (level_mm >= target_mm) return 0;
    return (target_mm - level_mm) / v * 60.0f;
}
