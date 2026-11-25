#include "grip.h"

#include <math.h>

static float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }
static float step_frac(float dt, float tau) { return tau <= 0.0f ? 1.0f : fminf(1.0f, dt / tau); }

grip_cfg_t grip_default_cfg(void)
{
    return (grip_cfg_t){
        .base_tau_s = 4.0f,
        .base_fall_tau_s = 1.0f,
        .on_pa = 150.0f,
        .off_pa = 80.0f,
        .min_range_pa = 800.0f,
        .range_tau_s = 30.0f,
        .max_squeeze_s = 10.0f,
    };
}

void grip_init(grip_t *g, const grip_cfg_t *cfg)
{
    *g = (grip_t){ .cfg = *cfg, .range = cfg->min_range_pa };
}

float grip_update(grip_t *g, float pa, float dt_s, bool masked)
{
    const grip_cfg_t *c = &g->cfg;
    if (!g->init) {
        g->init = true;
        g->baseline = pa;
        g->level = 0.0f;
        return 0.0f;
    }
    if (masked) {
        g->active = false;
        g->active_s = 0.0f;
        g->level = 0.0f;
        return 0.0f;
    }

    float d = pa - g->baseline;
    if (!g->active) {
        if (d > c->on_pa) {
            g->active = true;
            g->active_s = 0.0f;
        } else {
            g->baseline += d * step_frac(dt_s, d < 0.0f ? c->base_fall_tau_s : c->base_tau_s);
            d = pa - g->baseline;
        }
    } else {
        g->active_s += dt_s;
        if (d < c->off_pa) {
            g->active = false;
        } else if (g->active_s > c->max_squeeze_s) {
            /* Nobody squeezes for 10 s: this is warming air or a weather front. */
            g->active = false;
            g->baseline = pa;
            d = 0.0f;
        }
    }

    /* Auto-range: instant attack, slow release toward the minimum. */
    if (d > g->range)
        g->range = d;
    else
        g->range += (c->min_range_pa - g->range) * step_frac(dt_s, c->range_tau_s);
    if (g->range < c->min_range_pa)
        g->range = c->min_range_pa;

    g->level = g->active ? clampf((d - c->off_pa) / (g->range - c->off_pa), 0.0f, 1.0f) : 0.0f;
    return g->level;
}
