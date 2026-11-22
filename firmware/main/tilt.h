// Is brim still upright in its bracket? (pure logic, host-testable)
// The reference gravity direction is learned at the start of a bath (PAD1 wet = it is on the tub wall).
#pragma once
#include <stdbool.h>

typedef struct {
    bool ref_valid;
    float ref[3];             // unit gravity vector when mounted
    float tilted_since;       // s, < 0 = upright
    bool sent;
} tilt_t;

#define TILT_LIMIT_DEG 30.0f
#define TILT_CONFIRM_S 20.0f

float tilt_angle_deg(const float a[3], const float b[3]);
void tilt_learn(tilt_t *t, const float g[3]);
// returns true once when the device has been tilted past the limit for TILT_CONFIRM_S
bool tilt_update(tilt_t *t, const float g[3], float now_s);
bool tilt_is_tilted(const tilt_t *t);
