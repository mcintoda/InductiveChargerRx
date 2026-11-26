// Water level from the capacitive electrode ladder (pure logic, host-testable).
//
// Model (docs/placement-and-electrodes.md): each pad's reading rises linearly as water climbs it.
//   delta_k = raw_k - base_k * (1 + drift)      drift from the dry REF pad
//   f_k     = clamp(delta_k / full_k, 0, 1)      full_k learned per pad as the water passes it
//   ratiometric (default): f_k = delta_k / (delta_j * full_k / full_j), j = a fully-wet pad below k.
//   Anything that scales every wet pad together (water-to-ground return path, a person in the bath,
//   water conductivity, wall temperature) cancels in the ratio.
//   level   = sum(f_k) * pitch - fringe offset    (only counting pad k if pad k-1 is >= 90 % wet)
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define LVL_PADS 6                 // level pads, index 0 = bottom (PAD1)
#define LVL_CH (LVL_PADS + 1)      // + REF (index 6)
#define LVL_REF 6

#define LVL_PITCH_MM 10.0f
#define LVL_PAD_H_MM 9.0f
#define LVL_FRINGE_MM 1.7f
#define LVL_RANGE_MM 60.0f
#define LVL_DEFAULT_FULL_FRAC 0.25f   // first guess: wet adds ~25 % to the raw count (learned later)
#define LVL_WET_FRAC 0.70f            // per-pad wet decision (above the worst water-film case)
#define LVL_CHAIN_FRAC 0.90f          // pad k+1 only counts once pad k is this wet (rejects films)

typedef struct {
    float base[LVL_CH];      // dry raw counts
    float full[LVL_CH];      // raw-count increase when fully wet
    uint8_t learned[LVL_CH]; // number of times full[] was learned
    bool valid;
    bool ratiometric;        // divide by a fully-wet pad below (live reference) instead of the learned full[]
    float rgain[LVL_PADS];   // wet gain of pad k relative to pad k-1, learned with both covered (scale-free)
} lvl_cal_t;

typedef struct {
    float frac[LVL_CH];      // 0..1 wet fraction per pad (after chaining for level pads)
    float raw_frac[LVL_CH];  // 0..1 before chaining (for diagnostics)
    float level_mm;          // 0..60 mm above the bottom of PAD1 (valid only when wet)
    float drift;             // relative drift seen on REF
    bool wet;                // PAD1 is wet: a bath is in progress
    bool ref_wet;            // the dry reference is wet: water far above the alarm level, or submerged
    bool all_wet;            // every pad including REF wet
    int top_full;            // highest pad (1..6) that is >= 90 % wet, 0 if none: "water reached the top of pad n"
} lvl_result_t;

void lvl_cal_init(lvl_cal_t *cal, const uint32_t raw[LVL_CH]);
// slow baseline tracking while everything is dry (alpha ~0.05)
void lvl_track_dry(lvl_cal_t *cal, const uint32_t raw[LVL_CH], float alpha);
// compute the level; learns full[] values as the water passes each pad
lvl_result_t lvl_compute(lvl_cal_t *cal, const uint32_t raw[LVL_CH]);
// FDC build: PAD2..PAD4 stay on touch, the FDC1004 sees PAD1 (covered / not) and PAD5..6. Below the FDC's 40 mm
// window this gives the level from PAD2..4 (9..39 mm; 9 = only PAD1 covered), so the fill rate and the
// "nearly full" estimate start ~30 mm earlier. Learned-only (no live reference): a few mm, enough for a rate.
float lvl_lower_mm(const lvl_result_t *r);
// top edge of pad n (1..6) in mm above the bottom of PAD1: the alarm level for "alarm at pad n"
float lvl_pad_top_mm(int pad);
// raw-count threshold for pad n (1..6) used as the deep-sleep wake threshold (50 % wet)
uint32_t lvl_wake_threshold(const lvl_cal_t *cal, int pad);
