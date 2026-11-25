/* grip: turns the air pressure inside the unit into a squeeze level 0..1.
 *
 * The unit is one sealed air volume under a soft silicone skin. A squeeze pushes
 * the skin into a 1 mm air gap and raises the pressure by roughly 1-5 kPa.
 * Body heat and the weather move the pressure too, but slowly, so a tracked
 * baseline removes them. Each holder's strongest recent squeeze becomes full
 * scale (auto-range), so a child's squeeze and an adult's both reach 1.0.
 *
 * Pure C, no ESP-IDF: host-tested in test/test_logic.c.
 */
#pragma once
#include <stdbool.h>

typedef struct {
    float base_tau_s;      /* baseline follows the resting pressure with this time constant */
    float base_fall_tau_s; /* faster when the pressure drops below the baseline */
    float on_pa;           /* a squeeze starts when the rise exceeds this */
    float off_pa;          /* ...and ends when it falls below this */
    float min_range_pa;    /* the smallest rise that counts as a full squeeze */
    float range_tau_s;     /* full scale relaxes back to min_range_pa this slowly */
    float max_squeeze_s;   /* a "squeeze" longer than this is drift: re-zero */
} grip_cfg_t;

typedef struct {
    grip_cfg_t cfg;
    bool init;
    bool active;     /* a squeeze is in progress */
    float baseline;  /* Pa */
    float range;     /* Pa above baseline that maps to level 1.0 */
    float active_s;  /* duration of the current squeeze */
    float level;     /* last output, 0..1 */
} grip_t;

grip_cfg_t grip_default_cfg(void);
void grip_init(grip_t *g, const grip_cfg_t *cfg);

/* One sample. masked = the unit's own plates are moving (it is playing the
 * partner's squeeze), so the pressure says nothing about this holder: output 0
 * and freeze the baseline. Returns the squeeze level 0..1. */
float grip_update(grip_t *g, float pa, float dt_s, bool masked);
