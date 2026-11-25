/* shaper: partner's squeeze level 0..1 -> servo angle.
 *
 *  - Linear plate travel: the oval cam's lift is not linear in angle, so the
 *    level is mapped through the cam's inverse (cam_a_mm/cam_b_mm; 0 = off).
 *  - Slew limit: smooth, quiet motion, and no jolt if packets jump.
 *  - Hold limit: after max_hold_s of continuous squeeze the plates relax until
 *    the partner lets go (protects the servo from stalling hot against a hand).
 *
 * Pure C, host-tested.
 */
#pragma once
#include <stdbool.h>

typedef struct {
    float rest_deg;   /* plates retracted (cam minor axis on the plates) */
    float full_deg;   /* plates at this unit's maximum swell */
    float slew_dps;   /* max servo speed */
    float max_hold_s; /* relax after this long */
    float on_level;   /* levels below this count as "not squeezing" */
    float cam_a_mm;   /* oval cam semi-major axis (lift at full) */
    float cam_b_mm;   /* semi-minor axis (lift at rest) */
} shaper_cfg_t;

typedef struct {
    shaper_cfg_t cfg;
    float angle;
    float hold_s;
    bool limited;
} shaper_t;

void shaper_init(shaper_t *s, const shaper_cfg_t *cfg);

/* Fraction of the 90 deg cam stroke that gives a fraction x of the plate travel. */
float shaper_cam_inverse(float x, float a, float b);

/* target = partner's level 0..1 (0 when not playing). Returns the servo angle. */
float shaper_update(shaper_t *s, float target, float dt_s);

/* The plates are away from rest (so this unit's own pressure reading is not the holder's). */
bool shaper_busy(const shaper_t *s);
