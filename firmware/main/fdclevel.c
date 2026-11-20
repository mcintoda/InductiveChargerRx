#include "fdclevel.h"

#include <string.h>

#define WINDOW_BOTTOM_MM 40.0f
#define FRINGE_MM 1.7f
#define WET_PF_MIN 1.0f       // PAD1 must gain at least this much to count as wet (~20 % of full)

static float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

void fdc_cal_init(fdc_cal_t *c, const float pf[FDC_CH])
{
    memset(c, 0, sizeof(*c));
    memcpy(c->base, pf, sizeof(c->base));
    c->g5 = c->g6 = 1.05f;
    c->valid = true;
}

void fdc_bath_start(fdc_cal_t *c) { c->rl = 0; }

fdc_result_t fdc_level(fdc_cal_t *c, const float pf[FDC_CH])
{
    fdc_result_t r;
    memset(&r, 0, sizeof(r));
    float d_ref = pf[FDC_REF] - c->base[FDC_REF];
    // REF is 6 mm tall vs 9 mm pads: its full-wet change is ~2/3 of PAD1's
    float ref_full = (c->rl > WET_PF_MIN ? c->rl : 5.0f) * (6.0f / 9.0f);
    r.ref_frac = clampf(d_ref / ref_full, 0, 1);
    r.ref_wet = r.ref_frac >= 0.7f;
    r.drift = (r.ref_frac < 0.1f && c->base[FDC_REF] > 0) ? d_ref / c->base[FDC_REF] : 0;

    float d1 = pf[FDC_PAD1] - c->base[FDC_PAD1] * (1 + r.drift);
    float d5 = pf[FDC_PAD5] - c->base[FDC_PAD5] * (1 + r.drift);
    float d6 = pf[FDC_PAD6] - c->base[FDC_PAD6] * (1 + r.drift);
    if (d1 > c->rl) c->rl = d1;              // PAD1 rises, then plateaus once it is covered
    r.rl = c->rl;
    r.pad1_wet = d1 > WET_PF_MIN;
    if (c->rl < WET_PF_MIN) return r;

    r.f5 = clampf(d5 / (c->rl * c->g5), 0, 1);
    r.f6 = clampf(d6 / (c->rl * c->g6), 0, 1);
    if (r.f5 < 0.9f) r.f6 = 0;                // chaining: films above the waterline are ignored
    // learn PAD5's gain once the water is clearly above it (PAD5 fully covered)
    float raw6 = d6 / (c->rl * c->g6);
    if (raw6 > 0.3f && d5 > 0.5f * c->rl) {
        float g = d5 / c->rl;
        if (g > 0.6f && g < 1.6f) { c->g5 += 0.3f * (g - c->g5); c->g6 = c->g5; }
    }
    r.in_window = r.f5 > 0.02f;
    if (r.in_window)
        r.level_mm = clampf(WINDOW_BOTTOM_MM + 10.0f * (r.f5 + r.f6) - FRINGE_MM, WINDOW_BOTTOM_MM - FRINGE_MM, 60.0f);
    if (r.f6 >= 0.9f) { r.top_full = 6; r.level_mm = 60.0f; }
    else if (r.f5 >= 0.9f) r.top_full = 5;
    return r;
}
