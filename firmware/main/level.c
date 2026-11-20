#include "level.h"

#include <math.h>
#include <string.h>

static float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

void lvl_cal_init(lvl_cal_t *cal, const uint32_t raw[LVL_CH])
{
    memset(cal, 0, sizeof(*cal));
    for (int k = 0; k < LVL_CH; k++) {
        cal->base[k] = (float)raw[k];
        // REF is 6 mm tall vs 9 mm pads: proportionally smaller full-wet change
        float area = (k == LVL_REF) ? 6.0f / 9.0f : 1.0f;
        cal->full[k] = cal->base[k] * LVL_DEFAULT_FULL_FRAC * area;
    }
    cal->valid = true;
}

void lvl_track_dry(lvl_cal_t *cal, const uint32_t raw[LVL_CH], float alpha)
{
    for (int k = 0; k < LVL_CH; k++)
        cal->base[k] += alpha * ((float)raw[k] - cal->base[k]);
}

float lvl_pad_top_mm(int pad)
{
    if (pad < 1) pad = 1;
    if (pad > LVL_PADS) pad = LVL_PADS;
    return (pad - 1) * LVL_PITCH_MM + LVL_PAD_H_MM;
}

uint32_t lvl_wake_threshold(const lvl_cal_t *cal)
{
    return (uint32_t)(cal->full[0] * 0.5f);   // the sleep FSM compares (raw - benchmark) to this
}

static void learn_full(lvl_cal_t *cal, int k, float delta)
{
    // accept only plausible values (30 %..300 % of the current estimate)
    if (delta < 0.3f * cal->full[k] || delta > 3.0f * cal->full[k]) return;
    float a = cal->learned[k] < 4 ? 0.5f : 0.1f;   // learn fast at first, then settle
    cal->full[k] += a * (delta - cal->full[k]);
    if (cal->learned[k] < 255) cal->learned[k]++;
}

lvl_result_t lvl_compute(lvl_cal_t *cal, const uint32_t raw[LVL_CH])
{
    lvl_result_t r;
    memset(&r, 0, sizeof(r));
    // drift: relative change on the dry reference (temperature, humidity, hands nearby)
    float ref_delta = (float)raw[LVL_REF] - cal->base[LVL_REF];
    float ref_frac = clampf(ref_delta / cal->full[LVL_REF], 0, 1);
    r.raw_frac[LVL_REF] = ref_frac;
    r.ref_wet = ref_frac >= LVL_WET_FRAC;
    r.drift = (ref_frac < 0.1f && cal->base[LVL_REF] > 0) ? ref_delta / cal->base[LVL_REF] : 0.0f;

    float delta[LVL_PADS];
    for (int k = 0; k < LVL_PADS; k++) {
        delta[k] = (float)raw[k] - cal->base[k] * (1.0f + r.drift);
        r.raw_frac[k] = clampf(delta[k] / cal->full[k], 0, 1);
    }
    // learn each pad's full-wet value once the water is clearly above it
    for (int k = 0; k < LVL_PADS - 1; k++)
        if (r.raw_frac[k + 1] > 0.3f && r.raw_frac[k] > 0.8f) learn_full(cal, k, delta[k]);
    // the top pad has nothing above it: use the mean of the learned middle pads
    // (relative gain full/base, so pads with different baselines compare)
    float sum = 0; int n = 0;
    for (int k = 1; k < LVL_PADS - 1; k++)
        if (cal->learned[k] && cal->base[k] > 0) { sum += cal->full[k] / cal->base[k]; n++; }
    if (n >= 2) {
        float gain = sum / n;
        cal->full[LVL_PADS - 1] = gain * cal->base[LVL_PADS - 1];
        cal->full[LVL_REF] = gain * (6.0f / 9.0f) * cal->base[LVL_REF];
    }
    // chained fractions: pad k+1 only counts when pad k is nearly full (films and splashes are ignored)
    float level = 0;
    for (int k = 0; k < LVL_PADS; k++) {
        float f = r.raw_frac[k];
        if (k > 0 && r.frac[k - 1] < LVL_CHAIN_FRAC) f = 0;
        r.frac[k] = f;
        level += f * LVL_PITCH_MM;
    }
    r.frac[LVL_REF] = ref_frac;
    r.wet = r.raw_frac[0] >= 0.5f;
    r.level_mm = r.wet ? clampf(level - LVL_FRINGE_MM, 0, LVL_RANGE_MM) : 0;
    for (int k = 0; k < LVL_PADS; k++)
        if (r.frac[k] >= LVL_CHAIN_FRAC) r.top_full = k + 1;
    if (r.frac[LVL_PADS - 1] >= LVL_CHAIN_FRAC) r.level_mm = LVL_RANGE_MM;   // top pad full: at or above 60 mm
    r.all_wet = r.ref_wet;
    for (int k = 0; k < LVL_PADS; k++) r.all_wet = r.all_wet && r.raw_frac[k] >= LVL_WET_FRAC;
    return r;
}
