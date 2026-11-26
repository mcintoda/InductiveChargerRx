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
        .steady_s = 3.0f,
        .steady_level = 0.35f,
    };
}

void grip_init(grip_t *g, const grip_cfg_t *cfg)
{
    *g = (grip_t){ .cfg = *cfg, .range = cfg->min_range_pa, .noise_var = 10.0f * 10.0f };
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

    g->rezeroed = false;
    float d = pa - g->baseline;
    /* thresholds follow this holder's idle noise (sensor + hand tremor), never below the configured ones */
    float sigma = sqrtf(g->noise_var);
    float on = fmaxf(c->on_pa, 4.0f * sigma), off = fmaxf(c->off_pa, 2.5f * sigma);
    if (!g->active) {
        if (!g->freeze && d < on)
            g->noise_var += (d * d - g->noise_var) * step_frac(dt_s, 2.0f);
        if (d > on) {
            g->active = true;
            g->active_s = 0.0f;
        } else if (!g->freeze) {
            g->baseline += d * step_frac(dt_s, d < 0.0f ? c->base_fall_tau_s : c->base_tau_s);
            d = pa - g->baseline;
        }
    } else {
        g->active_s += dt_s;
        /* the wobble while held (tremor): becomes the idle noise if this turns out to be a pickup */
        if (g->active_s <= dt_s * 1.5f) {
            g->d_avg = d;
            g->act_var = 0.0f;
        }
        g->d_avg += (d - g->d_avg) * step_frac(dt_s, 0.3f);
        g->act_var += ((d - g->d_avg) * (d - g->d_avg) - g->act_var) * step_frac(dt_s, 0.5f);
        if (d < off) {
            g->active = false;
        } else if (g->active_s > c->max_squeeze_s ||
                   (c->steady_s > 0 && g->active_s > c->steady_s && g->level_avg < c->steady_level && !g->freeze)) {
            /* picked up / grip changed (a weak steady rise held 3 s), or 10 s of "squeeze": warming air
             * or a weather front. Re-zero. */
            g->active = false;
            g->rezeroed = true;
            g->baseline = pa;
            if (g->act_var > g->noise_var)
                g->noise_var = g->act_var;
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

    g->level = g->active ? clampf((d - off) / (g->range - off), 0.0f, 1.0f) : 0.0f;
    g->level_avg += (g->level - g->level_avg) * step_frac(dt_s, 0.5f);
    return g->level;
}
