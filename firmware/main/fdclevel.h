// Level from the FDC1004 (pure logic, host-testable).
// TI's 3-electrode scheme: CIN1 = PAD1 (reference liquid: fully submerged once the water is above
// ~10 mm), CIN2 = PAD5, CIN3 = PAD6 (the alarm region, 40..59 mm), CIN4 = REF (reference environment, dry).
//   drift   d   = (C_ref - C_ref0) / C_ref0                      while REF is dry
//   live ref RL = max over this bath of (C_pad1 - C_pad1_0)      PAD1 plateaus once covered
//   f_k         = (C_k - C_k0 (1 + d)) / (RL * g_k)              g_k = wet gain of pad k relative to PAD1
//   level       = 40 + 10 (f5 + f6) - fringe   (valid in the alarm region only)
#pragma once
#include <stdbool.h>

#define FDC_CH 4
enum { FDC_PAD1 = 0, FDC_PAD5 = 1, FDC_PAD6 = 2, FDC_REF = 3 };

typedef struct {
    float base[FDC_CH];   // dry capacitance (pF, including the CAPDAC offset)
    float g5, g6;         // wet gain of PAD5 / PAD6 relative to PAD1 (default 1.05: PAD1 sits next to GND copper)
    float rl;             // reference-liquid change for this bath (pF)
    bool valid;
} fdc_cal_t;

typedef struct {
    float f5, f6, ref_frac, drift, rl;
    float level_mm;       // valid only when in_window
    bool pad1_wet, in_window, ref_wet;
    int top_full;         // 5 or 6 when that pad is >= 90 % wet, else 0
} fdc_result_t;

void fdc_cal_init(fdc_cal_t *c, const float pf[FDC_CH]);
void fdc_bath_start(fdc_cal_t *c);          // forget the previous bath's reference-liquid value
fdc_result_t fdc_level(fdc_cal_t *c, const float pf[FDC_CH]);
