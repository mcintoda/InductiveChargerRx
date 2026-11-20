// Fill-rate estimator: least-squares slope of level over the last ~60 s (pure logic, host-testable).
#pragma once
#include <stdbool.h>

#define RATE_N 40

typedef struct {
    float t[RATE_N], y[RATE_N];
    int n, head;
    float window_s;
} rate_t;

void rate_init(rate_t *r, float window_s);
void rate_add(rate_t *r, float t_s, float level_mm);
// slope in mm/min; false if not enough samples spanning at least half the window
bool rate_mm_per_min(const rate_t *r, float *out);
// seconds until `target_mm` at the current rate; < 0 if not rising
float rate_eta_s(const rate_t *r, float level_mm, float target_mm);
