#include "shaper.h"

#include <math.h>

static float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }

void shaper_init(shaper_t *s, const shaper_cfg_t *cfg)
{
    *s = (shaper_t){ .cfg = *cfg, .angle = cfg->rest_deg };
}

/* Flat-faced follower on an ellipse: the lift at cam angle t (0 = minor axis
 * on the plate) is h(t) = sqrt(b^2 cos^2 t + a^2 sin^2 t). Solve h = b + x(a-b)
 * for t and return t / 90 deg. */
float shaper_cam_inverse(float x, float a, float b)
{
    x = clampf(x, 0.0f, 1.0f);
    if (a <= b || b <= 0.0f)
        return x;
    float h = b + x * (a - b);
    float s2 = (h * h - b * b) / (a * a - b * b);
    float t = asinf(sqrtf(clampf(s2, 0.0f, 1.0f)));
    return t / (float)M_PI_2;
}

float shaper_update(shaper_t *s, float target, float dt_s)
{
    const shaper_cfg_t *c = &s->cfg;
    target = clampf(target, 0.0f, 1.0f);

    if (target > c->on_level) {
        s->hold_s += dt_s;
        if (s->hold_s > 3.0f * c->max_hold_s)
            s->limited = true;
    } else {
        s->hold_s = 0.0f;
        s->limited = false;
    }
    if (s->limited || target <= c->on_level) {
        target = 0.0f;
    } else if (s->hold_s > c->max_hold_s) {
        float k = clampf(s->hold_s - c->max_hold_s, 0.0f, 1.0f);   /* ease over 1 s */
        float cap = 1.0f + (c->hold_level - 1.0f) * k;
        if (target > cap)
            target = cap;
    }

    float f = shaper_cam_inverse(target, c->cam_a_mm, c->cam_b_mm);
    float want = c->rest_deg + (c->full_deg - c->rest_deg) * f;
    float step = c->slew_dps * dt_s;
    float d = want - s->angle;
    s->angle += clampf(d, -step, step);
    return s->angle;
}

float shaper_lift_mm(const shaper_t *s)
{
    const shaper_cfg_t *c = &s->cfg;
    if (c->cam_a_mm <= c->cam_b_mm)
        return 0.0f;
    float span = c->full_deg - c->rest_deg;
    float f = span != 0.0f ? (s->angle - c->rest_deg) / span : 0.0f;   /* 0..1 of the stroke used */
    float travel = fabsf(span) / 90.0f;                                 /* this unit's stroke, of 90 deg */
    float t = clampf(f * travel, 0.0f, 1.0f) * (float)M_PI_2;
    return sqrtf(c->cam_b_mm * c->cam_b_mm * cosf(t) * cosf(t) + c->cam_a_mm * c->cam_a_mm * sinf(t) * sinf(t))
           - c->cam_b_mm;
}

bool shaper_busy(const shaper_t *s)
{
    return fabsf(s->angle - s->cfg.rest_deg) > 0.5f;
}
