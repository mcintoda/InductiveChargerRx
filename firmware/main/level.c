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
    cal->ratiometric = true;
    for (int k = 1; k < LVL_PADS; k++) cal->rgain[k] = cal->full[k] / cal->full[k - 1];
    cal->rgain[0] = 1.0f;
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

uint32_t lvl_wake_threshold(const lvl_cal_t *cal, int pad)
{
    if (pad < 1 || pad > LVL_PADS) pad = 1;
    return (uint32_t)(cal->full[pad - 1] * 0.5f);   // the sleep FSM compares (raw - benchmark) to this
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
    // live reference: the pad below is fully wet once the water is clearly into pad k (or k-1)
    float ratio_frac[LVL_PADS];
    for (int k = 0; k < LVL_PADS; k++) {
        ratio_frac[k] = r.raw_frac[k];
        if (!cal->ratiometric || k == 0) continue;
        int j = -1;
        if (r.raw_frac[k] > 0.25f) j = k - 1;
        else if (k >= 2 && r.raw_frac[k - 1] > 0.25f) j = k - 2;
        if (j >= 0 && delta[j] > 0.3f * cal->full[j]) {
            float g = 1.0f;
            for (int i = j + 1; i <= k; i++) g *= cal->rgain[i];
            ratio_frac[k] = clampf(delta[k] / (delta[j] * g), 0, 1);
        }
    }
    // PAD1 has no pad below it: as soon as pad 2 (index 1) sees water, PAD1 is full by definition
    if (cal->ratiometric && r.raw_frac[1] > 0.08f) ratio_frac[0] = 1.0f;
    // learn each pad's full-wet value once the water is clearly above it
    for (int k = 0; k < LVL_PADS - 1; k++)
        if (r.raw_frac[k + 1] > 0.3f && r.raw_frac[k] > 0.8f) learn_full(cal, k, delta[k]);
    // learn pad-to-pad gain ratios from simultaneous readings (independent of the return-path scale)
    for (int k = 1; k < LVL_PADS - 1; k++)
        if (r.raw_frac[k + 1] > 0.3f && delta[k - 1] > 0.3f * cal->full[k - 1]) {
            float g = delta[k] / delta[k - 1];
            if (g > 0.5f * cal->rgain[k] && g < 2.0f * cal->rgain[k]) cal->rgain[k] += 0.3f * (g - cal->rgain[k]);
        }
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
        float f = ratio_frac[k];
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

float lvl_lower_mm(const lvl_result_t *r)
{
    float level = 0, prev = 1.0f;
    for (int k = 1; k <= 3; k++) {                   // PAD2..PAD4, chained like lvl_compute
        float f = prev >= LVL_CHAIN_FRAC ? r->raw_frac[k] : 0;
        level += f * LVL_PITCH_MM;
        prev = f;
    }
    if (r->raw_frac[1] < 0.08f) return LVL_PAD_H_MM;
    return clampf(LVL_PITCH_MM + level - LVL_FRINGE_MM, LVL_PAD_H_MM, 4 * LVL_PITCH_MM - 1.0f);
}
