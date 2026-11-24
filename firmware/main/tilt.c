#include "tilt.h"

#include <math.h>

float tilt_angle_deg(const float a[3], const float b[3])
{
    float na = sqrtf(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]), nb = sqrtf(b[0] * b[0] + b[1] * b[1] + b[2] * b[2]);
    if (na < 1e-3f || nb < 1e-3f) return 0;
    float c = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (na * nb);
    c = fmaxf(-1.0f, fminf(1.0f, c));
    return acosf(c) * 57.29578f;
}

void tilt_learn(tilt_t *t, const float g[3])
{
    float n = sqrtf(g[0] * g[0] + g[1] * g[1] + g[2] * g[2]);
    if (n < 0.7f || n > 1.3f) return;                  // moving: not a clean gravity reading
    for (int i = 0; i < 3; i++) t->ref[i] = g[i] / n;
    t->ref_valid = true;
    t->tilted_since = -1;
    t->sent = false;
}

bool tilt_update(tilt_t *t, const float g[3], double now_s)
{
    if (!t->ref_valid) { tilt_learn(t, g); return false; }
    float n = sqrtf(g[0] * g[0] + g[1] * g[1] + g[2] * g[2]);
    if (n < 0.7f || n > 1.3f) return false;            // being moved: decide when it settles
    if (tilt_angle_deg(g, t->ref) <= TILT_LIMIT_DEG) {
        t->tilted_since = -1;
        t->sent = false;                               // back upright: re-arm
        return false;
    }
    if (t->tilted_since < 0) t->tilted_since = now_s;
    if (!t->sent && now_s - t->tilted_since >= TILT_CONFIRM_S) { t->sent = true; return true; }
    return false;
}

bool tilt_is_tilted(const tilt_t *t) { return t->ref_valid && t->tilted_since >= 0; }
