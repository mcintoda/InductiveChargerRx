#include "policy.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

void policy_init(policy_t *p, float alarm_mm, float temp_limit_c, bool notify_filling)
{
    memset(p, 0, sizeof(*p));
    p->alarm_mm = alarm_mm;
    p->temp_limit_c = temp_limit_c;
    p->notify_filling = notify_filling;
}

static void temp_str(char *buf, size_t n, float t)
{
    if (isnan(t)) snprintf(buf, n, "--");
    else snprintf(buf, n, "%.1f \xC2\xB0" "C", t);
}

static bool emit(policy_out_t *o, policy_event_t ev, int prio, const char *title, const char *tags, const char *msg)
{
    o->ev = ev;
    o->priority = prio;
    snprintf(o->title, sizeof(o->title), "%s", title);
    snprintf(o->tags, sizeof(o->tags), "%s", tags);
    snprintf(o->msg, sizeof(o->msg), "%s", msg);
    return true;
}

static void end_session(policy_t *p)
{
    bool lowbat = p->lowbat_sent;
    policy_init(p, p->alarm_mm, p->temp_limit_c, p->notify_filling);
    p->lowbat_sent = lowbat;            // low battery is reported once per charge, not per bath
}

bool policy_step(policy_t *p, const policy_in_t *in, policy_out_t *out)
{
    char t[24], m[160];
    memset(out, 0, sizeof(*out));
    temp_str(t, sizeof(t), in->temp_c);

    if (in->battery_pct >= 0 && in->battery_pct < POLICY_LOW_BATT_PCT && !p->lowbat_sent) {
        p->lowbat_sent = true;
        snprintf(m, sizeof(m), "Battery at %d %%. Put brim on a Qi charger soon.", in->battery_pct);
        return emit(out, EV_LOW_BATTERY, 3, "brim battery low", "battery", m);
    }
    if (in->battery_pct >= 60) p->lowbat_sent = false;    // recharged

    if (in->wet) p->last_wet_s = in->now_s;
    if (!p->active) {
        if (!in->wet) return false;
        p->active = true;
        p->last_wet_s = in->now_s;
        // fell in: everything wet at the very first wet sample
        if (in->all_wet && !p->prev_wet) {
            p->submerged_sent = true;
            return emit(out, EV_SUBMERGED, 4, "brim is under water",
                        "warning", "Every sensor is wet at once - brim may have come off the tub wall.");
        }
        if (p->notify_filling) {
            p->filling_sent = true;
            snprintf(m, sizeof(m), "Bath filling, water at %s.", t);
            return emit(out, EV_FILLING, 2, "Bath filling", "bathtub", m);
        }
    }
    p->prev_wet = in->wet;
    if (!in->wet && in->now_s - p->last_wet_s > POLICY_SESSION_END_S) {   // drained
        end_session(p);
        return false;
    }

    // still rising? within range: the fill rate; at/above 60 mm the level is pinned, so use REF
    if (in->now_s - p->ref_snap_t >= 60.0f) {
        p->ref_rising = (in->ref_frac - p->ref_snap) > POLICY_REF_RISE;
        p->ref_snap = in->ref_frac;
        p->ref_snap_t = in->now_s;
    }
    bool saturated = in->level_mm >= 59.5f;
    bool rising = saturated ? p->ref_rising : (in->rate_ok && in->rate_mm_min > POLICY_RISING_MM_MIN);
    if (in->at_alarm || in->level_mm >= p->alarm_mm) {
        if (!p->alarm_active) {
            p->alarm_active = true;
            p->alarm_first_s = p->alarm_last_s = in->now_s;
            snprintf(m, sizeof(m), "Bath at the target level - turn off the tap. Water %s.", t);
            return emit(out, EV_ALARM, 5, "BATH FULL", "rotating_light,bathtub", m);
        }
        if (rising && in->now_s - p->alarm_last_s >= POLICY_REPEAT_S &&
            in->now_s - p->alarm_first_s <= POLICY_REPEAT_MAX_S) {
            p->alarm_last_s = in->now_s;
            snprintf(m, sizeof(m), "Still filling, %.0f mm above the target. Turn off the tap.",
                     in->level_mm - p->alarm_mm < 0 ? 0 : in->level_mm - p->alarm_mm);
            return emit(out, EV_ALARM, 5, "BATH STILL FILLING", "rotating_light,bathtub", m);
        }
    } else if (!p->nearly_sent && in->eta_s > 0 && in->eta_s <= POLICY_NEARLY_S) {
        p->nearly_sent = true;
        int mins = (int)(in->eta_s / 60.0f + 0.5f);
        if (mins < 1) snprintf(m, sizeof(m), "Bath nearly full - under a minute to go. Water %s.", t);
        else snprintf(m, sizeof(m), "Bath nearly full - about %d min to go. Water %s.", mins, t);
        return emit(out, EV_NEARLY_FULL, 4, "Bath nearly full", "bathtub", m);
    }
    if (!isnan(in->temp_c) && in->temp_c > p->temp_limit_c && !p->hot_sent) {
        p->hot_sent = true;
        snprintf(m, sizeof(m), "Water is %s, above your %.0f \xC2\xB0" "C limit.", t, p->temp_limit_c);
        return emit(out, EV_TOO_HOT, 4, "Bath too hot", "thermometer", m);
    }
    return false;
}
