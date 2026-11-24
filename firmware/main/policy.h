// Notification policy: what to tell the phone, when (pure logic, host-testable).
#pragma once
#include <stdbool.h>
#include <stddef.h>

typedef enum {
    EV_NONE = 0,
    EV_FILLING,        // bath started (optional)
    EV_NEARLY_FULL,    // ~2 min to the alarm level
    EV_ALARM,          // alarm level reached (repeats while still rising)
    EV_TOO_HOT,        // above the temperature limit
    EV_TOO_COOL,       // cooled below the "too cool" level after being warm (optional)
    EV_SUBMERGED,      // every pad incl. REF wet at once: it fell into the bath
    EV_LOW_BATTERY,
} policy_event_t;

typedef struct {
    // settings
    float alarm_mm;            // alarm level (top of the chosen pad)
    float temp_limit_c;
    float temp_cool_c;         // 0 = off
    bool notify_filling;
    // session state
    bool active, nearly_sent, hot_sent, lowbat_sent, alarm_active, was_warm, cool_sent;
    double alarm_first_s, alarm_last_s, last_wet_s;   // s (double: wall-clock seconds keep 1 s resolution)
    bool prev_wet;
    float ref_snap;              // above 60 mm the dry REF pad tells whether water is still rising
    double ref_snap_t;
    double still_since;          // alarm reached and the water stopped rising at this time (0 = not still)
    bool ref_rising;
    bool acked;                // double-tap on the case: no more repeats (or local beeps) this bath
} policy_t;

typedef struct {
    double now_s;
    bool wet;                  // PAD1 wet
    bool all_wet;
    float level_mm;
    float ref_frac;            // REF pad wet fraction (0..1), above the 60 mm range
    bool at_alarm;             // water reached the top of the alarm pad (lvl_result_t.top_full >= alarm pad)
    bool rate_ok;
    float rate_mm_min;         // fill rate
    float eta_s;               // to the alarm level, < 0 if unknown
    float temp_c;              // NAN if not available
    int battery_pct;           // -1 if unknown
} policy_in_t;

typedef struct {
    policy_event_t ev;
    int priority;              // ntfy priority 1..5
    char title[48];
    char msg[160];
    char tags[32];
} policy_out_t;

#define POLICY_REPEAT_S 60.0f          // alarm repeat interval while the level keeps rising
#define POLICY_REPEAT_MAX_S (15 * 60.0f)
#define POLICY_RISING_MM_MIN 0.3f      // below this the tap is considered off
#define POLICY_REF_RISE 0.02f          // REF change per minute that still counts as rising (above range)
#define POLICY_NEARLY_S 120.0f
#define POLICY_SESSION_END_S (10 * 60.0f)  // all dry this long: the bath was drained
#define POLICY_LOW_BATT_PCT 20
#define POLICY_REFILL_MM_MIN 1.0f     // after the alarm, a fresh rise this fast (a top-up) re-arms it
#define POLICY_REFILL_STILL_S 120.0   // ...once the water had stopped rising for this long

void policy_init(policy_t *p, float alarm_mm, float temp_limit_c, bool notify_filling);
void policy_set_cool(policy_t *p, float temp_cool_c);   // 0 = off; kept across baths
// returns true and fills `out` when a notification should be sent now (one per call)
bool policy_step(policy_t *p, const policy_in_t *in, policy_out_t *out);
// the user acknowledged the alarm on the device (double tap): stop the repeats for this bath
void policy_ack(policy_t *p);
