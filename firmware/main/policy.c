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
    float cool = p->temp_cool_c;
    policy_init(p, p->alarm_mm, p->temp_limit_c, p->notify_filling);
    p->temp_cool_c = cool;
    p->lowbat_sent = lowbat;            // low battery is reported once per charge, not per bath
}

// One level scale through and above the line: the alarm pad counts as reached when it is full (FDC levels stop
// just short of the pad top), and above the top pad the dry REF pad (63..69 mm) carries on (60..63 mm is unseen).
static float ext_level(const policy_t *p, const policy_in_t *in)
{
    float v = in->level_mm;
    if (in->at_alarm && v < p->alarm_mm) v = p->alarm_mm;
    if (in->ref_frac > 0.02f) v = fmaxf(v, 63.0f + 6.0f * in->ref_frac);     // REF spans 63..69 mm
    return v;
}

// least-squares line through the ring, evaluated now; se = its scatter at the newest end
static void trend(policy_t *p, double now)
{
    int n = p->ring_n;
    double st = 0, sv = 0, stt = 0, stv = 0;
    for (int i = 0; i < n; i++) {
        double t = p->ring_t[i] - now;
        st += t; sv += p->ring_v[i]; stt += t * t; stv += t * p->ring_v[i];
    }
    double den = n * stt - st * st;
    double b = den > 1e-9 ? (n * stv - st * sv) / den : 0, a = (sv - b * st) / n;
    double ss = 0;
    for (int i = 0; i < n; i++) { double e = p->ring_v[i] - (a + b * (p->ring_t[i] - now)); ss += e * e; }
    double sd = n > 2 ? sqrt(ss / (n - 2)) : 0;
    p->trend_mm = (float)a;
    p->trend_se = (float)(sd * sqrt(4.0 / n));      // a line's end point is ~2x as uncertain as its mean
    p->trend_slope = (float)b;
    p->trend_t = now;
}

// Most samples past the line once each is moved forward by the fill rate (0..0.5 mm/s): a steady fill agrees at
// once; a few wave tops among samples below the line don't.
static bool majority_past(const policy_t *p, float line)
{
    float b = p->trend_slope < 0 ? 0 : (p->trend_slope > 0.5f ? 0.5f : p->trend_slope);
    int past = 0;
    for (int i = 0; i < p->ring_n; i++)
        if (p->ring_v[i] + b * (float)(p->trend_t - p->ring_t[i]) >= line) past++;
    return past * 10 >= p->ring_n * 6;
}

static void add_sample(policy_t *p, double now, float v)
{
    int newest = (p->ring_head - 1 + POLICY_RING) % POLICY_RING;
    if (p->ring_n && now - p->ring_t[newest] > 6.0) p->ring_n = p->ring_head = 0;   // woke from a sleep: start over
    p->ring_v[p->ring_head] = v;
    p->ring_t[p->ring_head] = now;
    p->ring_head = (p->ring_head + 1) % POLICY_RING;
    if (p->ring_n < POLICY_RING) p->ring_n++;
    trend(p, now);
    if (p->ring_n >= 3 && (p->snap_n == 0 || now - p->snap_t[p->snap_n - 1] >= 18.0)) {
        if (p->snap_n == POLICY_SNAPS) {
            memmove(p->snap_v, p->snap_v + 1, sizeof(float) * (POLICY_SNAPS - 1));
            memmove(p->snap_t, p->snap_t + 1, sizeof(double) * (POLICY_SNAPS - 1));
            p->snap_n--;
        }
        p->snap_v[p->snap_n] = p->trend_mm;
        p->snap_t[p->snap_n] = now;
        p->snap_n++;
    }
}

bool policy_sustained_rise(const policy_t *p, double since_s)
{
    // the newest run of snapshots with no gap over 30 s (a sleep breaks the run), none older than since_s
    int k = 1;
    while (k < p->snap_n && p->snap_t[p->snap_n - k] - p->snap_t[p->snap_n - k - 1] <= 30.0 &&
           p->snap_t[p->snap_n - k - 1] >= since_s)
        k++;
    if (k < 3) return false;
    int i0 = p->snap_n - k;
    float total = p->snap_v[p->snap_n - 1] - p->snap_v[i0];
    double span = p->snap_t[p->snap_n - 1] - p->snap_t[i0];
    // at least 2 mm, and well clear of the splashing (3x the trend line's own scatter)
    if (total < fmaxf(2.0f, 3.0f * p->trend_se) || total / (span / 60.0) < 0.8) return false;
    // a tap raises the water in every interval; people climbing in raise it in one or two
    float step = total / (k - 1), biggest = 0;
    int rising = 0;
    for (int i = i0 + 1; i < p->snap_n; i++) {
        float d = p->snap_v[i] - p->snap_v[i - 1];
        if (d > biggest) biggest = d;
        if (d > 0.3f * step) rising++;
    }
    // and still going: the last interval rose too (a tap turned off a minute ago is not "rising")
    bool ongoing = p->snap_v[p->snap_n - 1] - p->snap_v[p->snap_n - 2] > 0.3f * step;
    return ongoing && biggest <= 0.7f * total && rising >= 0.6f * (k - 1);
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

    // a dry spell this long (seen across sleeps too) means the bath was drained: the next water is a new bath
    if (!in->wet) {
        if (p->dry_since == 0) p->dry_since = in->now_s;
        if (p->active && in->now_s - p->dry_since > POLICY_SESSION_END_S) end_session(p);
        return false;
    }
    if (p->active && p->dry_since > 0 && in->now_s - p->dry_since > POLICY_SESSION_END_S) end_session(p);
    p->dry_since = 0;

    float prev = p->trend_mm;
    double prev_t = p->trend_t;
    bool was_active = p->active;
    float v = ext_level(p, in);
    add_sample(p, in->now_s, v);

    // fell in: everything under at once and no longer upright (no accelerometer: a jump since the last sample)
    bool jumped = in->now_s - prev_t <= 10.0 && v - prev >= POLICY_FALL_FROM_MM;
    if (in->all_wet && !p->submerged &&
        (in->upright == 0 || (in->upright < 0 && (jumped || !was_active)))) {
        p->submerged = p->active = true;
        return emit(out, EV_SUBMERGED, 4, "brim is under water", "warning",
                    "Every sensor went under at once - brim may have fallen off the tub wall. Bath alarms are paused "
                    "until it is back in its bracket.");
    }
    if (p->submerged) {
        if (in->all_wet) return false;
        p->submerged = false;                                  // back out of the water
        p->ring_n = p->ring_head = p->snap_n = 0;
    }
    if (!p->active) {
        p->active = true;
        if (p->notify_filling) {
            snprintf(m, sizeof(m), "Bath filling, water at %s.", t);
            return emit(out, EV_FILLING, 2, "Bath filling", "bathtub", m);
        }
    }

    // REF pad trend (main.c's sleep rules use it above the 60 mm range)
    if (in->now_s - p->ref_snap_t >= 60.0) {
        p->ref_rising = (in->ref_frac - p->ref_snap) > POLICY_REF_RISE;
        p->ref_snap = in->ref_frac;
        p->ref_snap_t = in->now_s;
    }
    bool steady_rise = policy_sustained_rise(p, p->acked ? p->acked_s : 0);
    // at the line: the trend line is past it by more than its own scatter (waves), and so are most samples
    bool at_line = p->ring_n >= 5 && p->trend_mm - 2.0f * p->trend_se >= p->alarm_mm - 1.0f &&
                   majority_past(p, p->alarm_mm - 1.5f);
    if (p->alarm_active || at_line) {
        if (!p->alarm_active) {
            p->alarm_active = true;
            p->alarm_first_s = p->alarm_last_s = in->now_s;
            p->still_since = 0;
            snprintf(m, sizeof(m), "Bath at the target level - turn off the tap. Water %s.", t);
            return emit(out, EV_ALARM, 5, "BATH FULL", "rotating_light,bathtub", m);
        }
        float over = p->trend_mm - p->alarm_mm < 0 ? 0 : p->trend_mm - p->alarm_mm;
        if (!steady_rise) {
            if (p->still_since == 0) p->still_since = in->now_s;
        } else if (p->acked || (p->still_since > 0 && in->now_s - p->still_since >= POLICY_REFILL_STILL_S)) {
            // silenced but the tap is still running, or a top-up after the water had stopped: a new alarm
            p->still_since = 0;
            p->acked = false;
            p->alarm_first_s = p->alarm_last_s = in->now_s;
            snprintf(m, sizeof(m), "The water is rising again, %.0f mm above your line. Turn off the tap.", over);
            return emit(out, EV_ALARM, 5, "BATH FILLING AGAIN", "rotating_light,bathtub", m);
        } else {
            p->still_since = 0;
            if (in->now_s - p->alarm_last_s >= POLICY_REPEAT_S && in->now_s - p->alarm_first_s <= POLICY_REPEAT_MAX_S) {
                p->alarm_last_s = in->now_s;
                snprintf(m, sizeof(m), "Still filling, %.0f mm above the target. Turn off the tap.", over);
                return emit(out, EV_ALARM, 5, "BATH STILL FILLING", "rotating_light,bathtub", m);
            }
        }
    } else {
        // the fill paused (parent testing the water, fetching the kids): warn again when it resumes
        bool paused = in->rate_ok && in->rate_mm_min < POLICY_RISING_MM_MIN;
        if (!paused) p->paused_since = 0;
        else if (p->paused_since == 0) p->paused_since = in->now_s;
        else if (p->nearly_sent && in->now_s - p->paused_since >= POLICY_PAUSE_REARM_S) p->nearly_sent = false;
        if (!p->nearly_sent && in->eta_s > 0 && in->eta_s <= POLICY_NEARLY_S) {
            p->nearly_sent = true;
            int mins = (int)(in->eta_s / 60.0f + 0.5f);
            if (mins < 1) snprintf(m, sizeof(m), "Bath nearly full - under a minute to go. Water %s.", t);
            else snprintf(m, sizeof(m), "Bath nearly full - about %d min to go. Water %s.", mins, t);
            return emit(out, EV_NEARLY_FULL, 4, "Bath nearly full", "bathtub", m);
        }
    }
    if (!isnan(in->temp_c)) {
        if (p->hot_sent && in->temp_c < p->temp_limit_c - POLICY_HOT_REARM_C) p->hot_sent = false;   // cooled: re-arm
        if (in->temp_c > p->temp_limit_c && !p->hot_sent) {
            p->hot_sent = true;
            snprintf(m, sizeof(m), "Water is %s, above your %.0f \xC2\xB0" "C limit.", t, p->temp_limit_c);
            return emit(out, EV_TOO_HOT, 4, "Bath too hot", "thermometer", m);
        }
    }
    // "too cool": only once the bath has been warm (0.5 C above the level), so a slow-warming fill doesn't trigger it
    if (p->temp_cool_c > 0 && !isnan(in->temp_c)) {
        if (in->temp_c >= p->temp_cool_c + 0.5f) p->was_warm = true;
        else if (p->was_warm && in->temp_c < p->temp_cool_c && !p->cool_sent) {
            p->cool_sent = true;
            snprintf(m, sizeof(m), "Water has cooled to %s, below your %.0f \xC2\xB0" "C level.", t, p->temp_cool_c);
            return emit(out, EV_TOO_COOL, 3, "Bath cooling down", "thermometer", m);
        }
    }
    return false;
}

void policy_set_cool(policy_t *p, float temp_cool_c) { p->temp_cool_c = temp_cool_c; }

bool policy_ack(policy_t *p)
{
    if (!p->alarm_active || p->acked) return false;
    p->acked = true;
    p->acked_s = p->trend_t;
    return true;
}
