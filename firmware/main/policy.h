// Notification policy: what to tell the phone, when (pure logic, host-testable).
//
// Bath-night behaviour it has to get right (firmware/test/scenarios.c plays each one):
//   - splashing near the line is not "full": the level is a short trend line through the last ~20 s, and it must be
//     confidently past the line (by more than its own scatter)
//   - people climbing in raise the water in a step; a tap raises it steadily. Repeats and "filling again" need a
//     steady rise over 40-120 s (the "sustained" test), so displacement never sounds like a running tap
//   - a double-tap only silences an alarm that is sounding (a toddler's taps during the fill don't pre-silence it)
//   - "too hot" and "nearly full" re-arm (cooled by 1 C / the fill paused 2 min)
//   - 2 min below the lowest pad ends the bath (drain + refill for the next child is a new bath)
//   - every sensor going under at once with the accelerometer saying brim is no longer upright (no accelerometer:
//     a jump of 15 mm or more between samples) is brim falling in: "brim is under water", no bath-full alarms
//     while it stays under
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

#define POLICY_RING 10      // last samples (2 s apart) for the level trend line
#define POLICY_SNAPS 7      // trend-line snapshots, ~20 s apart, for the sustained-rise test

typedef struct {
    // settings
    float alarm_mm;            // alarm level (top of the chosen pad)
    float temp_limit_c;
    float temp_cool_c;         // 0 = off
    bool notify_filling;
    // session state
    bool active, nearly_sent, hot_sent, lowbat_sent, alarm_active, was_warm, cool_sent, submerged;
    double alarm_first_s, alarm_last_s;   // s (double: wall-clock seconds keep 1 s resolution)
    double dry_since;          // first dry sample of a dry spell (0 = wet)
    double still_since;        // alarm reached and the water stopped rising at this time (0 = not still)
    double paused_since;       // below the line, not rising since (re-arms "nearly full")
    float ref_snap;            // above 60 mm the dry REF pad tells whether water is still rising
    double ref_snap_t;
    bool ref_rising;
    bool acked;                // double-tap on the case: no more repeats (or local beeps) this bath
    double acked_s;            // when (a rise is judged only from then on)
    // level trend
    float ring_v[POLICY_RING];
    double ring_t[POLICY_RING];
    int ring_n, ring_head;
    float snap_v[POLICY_SNAPS];
    double snap_t[POLICY_SNAPS];
    int snap_n;
    float trend_mm, trend_se;  // trend-line value now and its uncertainty (mm)
    float trend_slope;         // mm/s
    double trend_t;
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
    int upright;               // accelerometer: 1 upright in its bracket, 0 tilted / lying, -1 unknown
} policy_in_t;

typedef struct {
    policy_event_t ev;
    int priority;              // ntfy priority 1..5
    char title[48];
    char msg[160];
    char tags[32];
} policy_out_t;

#define POLICY_REPEAT_S 60.0f          // alarm repeat interval while the water keeps rising steadily
#define POLICY_REPEAT_MAX_S (15 * 60.0f)
#define POLICY_RISING_MM_MIN 0.3f      // below this the tap is considered off (main.c's sleep rules)
#define POLICY_REF_RISE 0.02f          // REF change per minute that still counts as rising (above range)
#define POLICY_NEARLY_S 120.0f
#define POLICY_SESSION_END_S 120.0     // below the lowest pad this long: the bath was drained
#define POLICY_LOW_BATT_PCT 20
#define POLICY_REFILL_STILL_S 120.0    // after the alarm, a steady rise once the water had been still this long re-arms it
#define POLICY_HOT_REARM_C 1.0f        // "too hot" again after cooling this far below the limit
#define POLICY_PAUSE_REARM_S 120.0     // "nearly full" again after the fill paused this long
#define POLICY_FALL_FROM_MM 15.0f      // no accelerometer: everything under after a jump this big = it fell in

void policy_init(policy_t *p, float alarm_mm, float temp_limit_c, bool notify_filling);
void policy_set_cool(policy_t *p, float temp_cool_c);   // 0 = off; kept across baths
// returns true and fills `out` when a notification should be sent now (one per call)
bool policy_step(policy_t *p, const policy_in_t *in, policy_out_t *out);
// the user double-tapped the case: silences the alarm that is sounding (no-op when none is). true if it did
bool policy_ack(policy_t *p);
// steady rise over the last 40-120 s, still going, counting only trend snapshots from `since_s` on
// (a running tap, not people getting in); exposed for tests
bool policy_sustained_rise(const policy_t *p, double since_s);
