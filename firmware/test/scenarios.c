// Virtual usability experiments: real bath-night situations played against the real firmware logic.
//
// level.c, rate.c, policy.c, fdclevel.c and tilt.c run unchanged. Around them, a copy of main.c's bath loop and
// its sleep rules (2 s samples while awake, wake on the wake pad / timer / tap, in-bath sleeps of 1, 2 or 5 min,
// 60 s dry -> sleep) and a physical bath: tap flow, people getting in, splashing, temperature, brim falling in.
//
//   make -C firmware/test scenarios        (prints one timeline per scenario, then the checks)
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../main/fdclevel.h"
#include "../main/level.h"
#include "../main/policy.h"
#include "../main/rate.h"
#include "../main/tilt.h"

static int fails, checks;
#define CHECK(cond, ...) do { checks++; if (!(cond)) { fails++; printf("    FAIL: "); printf(__VA_ARGS__); printf("\n"); } \
                              else { printf("    ok:   "); printf(__VA_ARGS__); printf("\n"); } } while (0)

// ---------------- the bath ----------------
#define MAXSEG 12
typedef struct { double t0, t1; float v; } seg_t;            // flow (mm/min), waves (amplitude mm), ...
typedef struct {
    const char *name, *who;
    bool fdc;                     // FDC1004 build (default product) or touch build
    int alarm_pad;                // 5 or 6 (FDC), 1..6 touch
    float temp_limit, temp_cool;
    double duration;
    float level0;                 // water at t = 0, mm above the bottom of PAD1 (negative = below the sensors)
    seg_t flow[MAXSEG];           // tap on: mm/min (negative = draining)
    seg_t step[MAXSEG];           // someone gets in (+mm) or out (-mm) at t0
    seg_t waves[MAXSEG];          // splashing: +-amplitude mm
    seg_t temp[MAXSEG];           // water temperature: from t0 on it is v (linear ramps between points)
    double fall_at;               // brim falls into the bath (0 = never)
    double taps[MAXSEG];          // double-taps on the case (s)
    double wifi_down0, wifi_down1;
} scen_t;

static unsigned rng = 12345, g_seed = 12345;
static float frand(void)            // xorshift32: -1..1
{
    rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
    return (rng >> 8) / 8388607.5f - 1.0f;
}
static float g_seiche_T = 1.9f, g_seiche_ph;   // the tub's sloshing period (s) and phase, per run

static float world_level(const scen_t *s, double t)
{
    float L = s->level0;
    for (int i = 0; i < MAXSEG && s->flow[i].t1 > 0; i++) {
        double a = s->flow[i].t0, b = fmin(t, s->flow[i].t1);
        if (b > a) L += s->flow[i].v * (b - a) / 60.0;
    }
    for (int i = 0; i < MAXSEG && s->step[i].v != 0; i++) if (t >= s->step[i].t0) L += s->step[i].v;
    return L;
}
// splashing: the tub's slosh (seiche, ~1.7-2.2 s, amplitude drifting 50..100 %) plus 30 % random chop
static float world_wave(const scen_t *s, double t)
{
    for (int i = 0; i < MAXSEG && s->waves[i].t1 > 0; i++)
        if (t >= s->waves[i].t0 && t < s->waves[i].t1) {
            float env = 0.75f + 0.25f * sinf((float)(t / 23.0));
            return s->waves[i].v * (0.8f * env * sinf((float)(6.2831853 * t / g_seiche_T) + g_seiche_ph) + 0.3f * frand());
        }
    return 0;
}
static float world_temp(const scen_t *s, double t)
{
    float T = s->temp[0].v;
    for (int i = 1; i < MAXSEG && s->temp[i].t0 > 0; i++) {
        if (t >= s->temp[i].t0) { T = s->temp[i].v; continue; }
        double a = s->temp[i - 1].t0;
        return s->temp[i - 1].v + (s->temp[i].v - s->temp[i - 1].v) * (float)((t - a) / (s->temp[i].t0 - a));
    }
    return T;
}
static bool fallen(const scen_t *s, double t) { return s->fall_at > 0 && t >= s->fall_at; }
static bool tapped(const scen_t *s, double a, double b)
{
    for (int i = 0; i < MAXSEG && s->taps[i] > 0; i++) if (s->taps[i] > a && s->taps[i] <= b) return true;
    return false;
}

// sensor models (same as test_logic.c)
static const float BASE[LVL_CH] = {20000, 19500, 19800, 20200, 19900, 20100, 15000};
static const float FULLF[LVL_CH] = {0.30f, 0.32f, 0.31f, 0.33f, 0.32f, 0.31f, 0.21f};
static float frac_model(float level, float bottom, float h)
{
    float f = (level - (bottom - 1.0f)) / (h + 2.0f);
    return f < 0 ? 0 : (f > 1 ? 1 : f);
}
static bool g_fdc_build;   // FDC build: PAD1, PAD5, PAD6 and REF are on the FDC1004 (their touch links not fitted)
static void touch_raw(float L, uint32_t raw[LVL_CH])
{
    for (int k = 0; k < LVL_PADS; k++) raw[k] = (uint32_t)(BASE[k] + BASE[k] * FULLF[k] * frac_model(L, k * 10.0f, 9.0f));
    raw[LVL_REF] = (uint32_t)(BASE[LVL_REF] + BASE[LVL_REF] * FULLF[LVL_REF] * frac_model(L, 63.0f, 6.0f));
    if (g_fdc_build) raw[0] = (uint32_t)BASE[0], raw[4] = (uint32_t)BASE[4], raw[5] = (uint32_t)BASE[5], raw[LVL_REF] = (uint32_t)BASE[LVL_REF];
}
static void fdc_raw(float L, float pf[FDC_CH])
{
    const float base[FDC_CH] = {25.0f, 24.0f, 24.5f, 20.0f}, full[FDC_CH] = {5.5f, 5.8f, 5.8f, 3.9f};
    const float bottom[FDC_CH] = {0, 40, 50, 63}, h[FDC_CH] = {9, 9, 9, 6};
    for (int i = 0; i < FDC_CH; i++) pf[i] = base[i] + full[i] * frac_model(L, bottom[i], h[i]);
}

// ---------------- the device (main.c's bath loop and sleep rules) ----------------
typedef struct { double t; char title[48]; int prio; bool beep; float above_line; } alert_t;
typedef struct {
    alert_t a[64]; int n;
    int beeps;                    // local alarm bursts
    double asleep_s;
    float max_over;               // highest water above the line while the tap was on
} result_t;

static const double T0 = 1.7e9;   // wall clock, like the device

static void run(const scen_t *s, result_t *res)
{
    memset(res, 0, sizeof(*res));
    rng = g_seed ? g_seed : 1;
    g_seiche_T = 1.7f + 0.25f * (frand() + 1); g_seiche_ph = 3.14159f * frand();
    g_fdc_build = s->fdc;
    // calibration from earlier baths
    lvl_cal_t cal; uint32_t raw[LVL_CH];
    touch_raw(-20, raw); lvl_cal_init(&cal, raw);
    for (float L = -5; L <= 62; L += 1) { touch_raw(L, raw); lvl_compute(&cal, raw); }
    fdc_cal_t fdc; float pf[FDC_CH];
    fdc_raw(-20, pf); fdc_cal_init(&fdc, pf);
    policy_t pol; bool pol_ready = false;
    tilt_t tilt = {0};
    const float alarm_mm = lvl_pad_top_mm(s->alarm_pad);
    const int wake_pad = s->fdc ? 2 : 1;

    bool awake = false; double timer_at = -1; bool wake_by_tap = false;
    int armed_pad = wake_pad; float armed_base = 0;          // touch wake: pad and its wet fraction at sleep entry
    // awake-period state (locals of bath_mode)
    rate_t rate; double t_start = 0, t_temp = 0, t_dry = 0, t_steady = 0, next_sample = 0; float temp = NAN;

    for (double t = 0; t < s->duration; t += 0.5) {
        float L = world_level(s, t);
        if (fallen(s, t)) L = 200;                                    // lying on the bottom: everything under water
        if (!awake) {
            res->asleep_s += 0.5;
            bool wake = (timer_at >= 0 && t >= timer_at) ||
                        (armed_pad && frac_model(L + world_wave(s, t), (armed_pad - 1) * 10.0f, 9.0f) - armed_base >= 0.5f);
            wake_by_tap = tapped(s, t - 0.5, t);
            if (wake_by_tap && !(pol_ready && pol.active)) wake_by_tap = false;   // shows the battery, sleeps again
            if (!wake && !wake_by_tap) continue;
            awake = true;
            // bath_mode() entry
            if (!pol_ready) { policy_init(&pol, alarm_mm, s->temp_limit, false); pol_ready = true; }
            policy_set_cool(&pol, s->temp_cool);
            if (!pol.active) { fdc_bath_start(&fdc); tilt.ref_valid = false; }
            rate_init(&rate, 60);
            t_start = t; t_temp = 0; t_dry = 0; t_steady = 0; temp = NAN; next_sample = t;
        }
        if (t < next_sample) continue;
        next_sample = t + 2.0;

        // ---- one pass of the bath loop ----
        // main.c bath_sample(): 4 readings 0.45 s apart, averaged (raw counts are linear in the wetted area)
        uint64_t acc[LVL_CH] = {0}; float pacc[FDC_CH] = {0};
        for (int i = 0; i < 4; i++) {
            float Li = L + world_wave(s, t - 1.35 + 0.45 * i);
            uint32_t r1[LVL_CH]; float p1[FDC_CH];
            touch_raw(Li, r1); fdc_raw(Li, p1);
            for (int k = 0; k < LVL_CH; k++) acc[k] += r1[k];
            for (int k = 0; k < FDC_CH; k++) pacc[k] += p1[k] / 4;
        }
        for (int k = 0; k < LVL_CH; k++) raw[k] = (uint32_t)(acc[k] / 4);
        lvl_result_t r;
        r = lvl_compute(&cal, raw);
        if (s->fdc) {
            memcpy(pf, pacc, sizeof(pf));
            fdc_result_t fr = fdc_level(&fdc, pf);
            r.wet = fr.pad1_wet;
            r.level_mm = fr.in_window ? fr.level_mm : (fr.pad1_wet ? lvl_lower_mm(&r) : 0);
            r.top_full = fr.top_full;
            r.raw_frac[LVL_REF] = fr.ref_frac;
            r.all_wet = fr.ref_wet && fr.top_full == 6;
        }
        if (r.wet && (t - t_temp > 10 || isnan(temp))) { temp = world_temp(s, t); t_temp = t; }
        if (r.wet) rate_add(&rate, (float)(t - t_start), r.level_mm);
        int alarm_pad = s->alarm_pad;
        float g_up[3] = {0.02f, -0.99f, 0.05f}, g_flat[3] = {0.05f, 0.1f, -0.99f};
        const float *g = fallen(s, t) ? g_flat : g_up;
        int upright = tilt.ref_valid ? tilt_angle_deg(g, tilt.ref) <= TILT_LIMIT_DEG : -1;
        policy_in_t in = {.now_s = T0 + t, .wet = r.wet, .all_wet = r.all_wet, .level_mm = r.level_mm,
                          .ref_frac = r.raw_frac[LVL_REF], .at_alarm = r.top_full >= alarm_pad, .temp_c = temp,
                          .battery_pct = 80, .upright = upright};
        in.rate_ok = rate_mm_per_min(&rate, &in.rate_mm_min);
        in.eta_s = rate_eta_s(&rate, r.level_mm, pol.alarm_mm - 1.0f);
        policy_out_t o;
        bool fired = policy_step(&pol, &in, &o);
        if (getenv("SIMDBG") && !strcmp(s->name, getenv("SIMDBG")) && fmod(t, 10) < 2)
            printf("      t %5.0f L %5.1f lvl %5.1f ref %.2f at %d trend %5.1f se %.2f snaps %d sus %d acked %d still %.0f\n", t, L, r.level_mm, r.raw_frac[LVL_REF], in.at_alarm, pol.trend_mm, pol.trend_se, pol.snap_n, policy_sustained_rise(&pol, pol.acked ? pol.acked_s : 0), pol.acked, pol.still_since ? T0 + t - pol.still_since : 0);
        if (fired && getenv("RINGDBG") && o.ev == EV_ALARM) {
            printf("      seed %u t %.0f trend %.1f se %.2f slope %.3f n %d:", g_seed, t, pol.trend_mm, pol.trend_se, pol.trend_slope, pol.ring_n);
            for (int i = 0; i < pol.ring_n; i++) printf(" %.1f@%.0f", pol.ring_v[i], pol.ring_t[i] - T0);
            printf("\n");
        }
        if (fired) {
            alert_t *a = &res->a[res->n < 63 ? res->n++ : 63];
            a->t = t; snprintf(a->title, sizeof(a->title), "%s", o.title); a->prio = o.priority;
            a->above_line = L - alarm_mm;
            bool urgent = o.ev == EV_ALARM || o.ev == EV_SUBMERGED;
            bool sent = !(t >= s->wifi_down0 && t < s->wifi_down1);
            a->beep = (urgent && !pol.acked) || (!sent && (o.ev == EV_NEARLY_FULL || o.ev == EV_TOO_HOT));
            if (a->beep) res->beeps++;
            if (!sent) snprintf(a->title + strlen(a->title), sizeof(a->title) - strlen(a->title), " (not sent)");
        }
        if (tapped(s, t - 2.0, t)) policy_ack(&pol);
        if (r.wet && tilt_update(&tilt, g, T0 + t) && !pol.submerged) {
            alert_t *a = &res->a[res->n < 63 ? res->n++ : 63];
            a->t = t; snprintf(a->title, sizeof(a->title), "brim is tilted"); a->prio = 4; a->beep = false;
            a->above_line = L - alarm_mm;
        }

        // ---- sleep rules ----
        double sleep_for = -1; int pad = wake_pad;
        if (!r.wet) {
            if (t_dry == 0) t_dry = t;
            if (t - t_dry > 60) { lvl_track_dry(&cal, raw, 0.1f); sleep_for = pol.active ? 15 * 60 : 6 * 3600; }
        } else t_dry = 0;
        bool steady = in.rate_ok && fabsf(in.rate_mm_min) < POLICY_RISING_MM_MIN && !pol.alarm_active;
        bool alarm_quiet = pol.alarm_active && !(in.rate_ok && in.rate_mm_min > POLICY_RISING_MM_MIN) && !pol.ref_rising;
        if (sleep_for < 0 && (steady || alarm_quiet)) {
            if (t_steady == 0) t_steady = t;
            // main.c pad_above(): lowest touch pad not yet half wet (FDC build: PAD2..4 only)
            pad = 0;
            for (int k = 1; k <= LVL_PADS && !pad; k++)
                if ((!s->fdc || (k >= 2 && k <= 4)) && r.raw_frac[k - 1] < 0.5f) pad = k;
            bool near = pol.alarm_active || pol.nearly_sent || !pad;
            if (t - t_steady > 180) sleep_for = near ? 60 : 300;
        } else if (sleep_for < 0) t_steady = 0;
        if (sleep_for > 0) {
            awake = false; timer_at = t + sleep_for; armed_pad = pad;
            armed_base = pad ? frac_model(L, (pad - 1) * 10.0f, 9.0f) : 0;
        }
    }
    // water above the line at its highest
    for (double t = 0; t < s->duration; t += 1) { float L = world_level(s, t) - alarm_mm; if (L > res->max_over) res->max_over = L; }
}

static void show(const scen_t *s, const result_t *r)
{
    printf("\n== %s\n   %s\n   (%s build, alarm at pad %d = %.0f mm, hot > %.0f C)\n", s->name, s->who,
           s->fdc ? "FDC1004" : "touch", s->alarm_pad, lvl_pad_top_mm(s->alarm_pad), s->temp_limit);
    for (int i = 0; i < r->n; i++)
        printf("   %3d:%02d  %-34s prio %d%s   water %+.0f mm vs line\n", (int)(r->a[i].t / 60), (int)fmod(r->a[i].t, 60),
               r->a[i].title, r->a[i].prio, r->a[i].beep ? " +BEEP" : "      ", r->a[i].above_line);
    if (!r->n) printf("   (no alerts)\n");
    printf("   asleep %.0f %% of the time, water peaked %+.0f mm vs line\n", 100 * r->asleep_s / s->duration, r->max_over);
}

static int count(const result_t *r, const char *title)
{
    int n = 0;
    for (int i = 0; i < r->n; i++) if (!strncmp(r->a[i].title, title, strlen(title))) n++;
    return n;
}
static const alert_t *first(const result_t *r, const char *title)
{
    for (int i = 0; i < r->n; i++) if (!strncmp(r->a[i].title, title, strlen(title))) return &r->a[i];
    return NULL;
}
static double first_t(const result_t *r, const char *title) { const alert_t *a = first(r, title); return a ? a->t : -1; }

// ---------------- the experiments ----------------
#define M *60.0
int main(void)
{
    result_t r;
    printf("brim virtual usability experiments (firmware logic, simulated bath)\n");

    // 1. The normal bath at real tap rates: how early is "nearly full", how far past the line is "BATH FULL"?
    printf("\n######## 1. Nearly-full warning at real fill rates (tap off 30 s after BATH FULL)\n");
    float rates[] = {5, 10, 15, 20, 25};
    for (int b = 0; b < 2; b++)
        for (int i = 0; i < 5; i++) {
            scen_t s = {.name = "fill", .who = "", .fdc = b == 0, .alarm_pad = 6, .temp_limit = 38, .duration = 40 M,
                        .level0 = -60, .temp = {{0, 0, 37.5f}}};
            float v = rates[i];
            double t_line = (59 - s.level0) / v * 60;            // when the water reaches the alarm line
            s.flow[0] = (seg_t){0, t_line + 30, v};
            run(&s, &r);
            double tn = first_t(&r, "Bath nearly full"), tf = first_t(&r, "BATH FULL");
            const alert_t *af = first(&r, "BATH FULL");
            printf("   %-7s %2.0f mm/min: nearly-full %s%5.0f s before BATH FULL; BATH FULL at %+.1f mm; %d alerts\n",
                   s.fdc ? "FDC" : "touch", v, tn < 0 ? "MISSING " : "", tn < 0 ? 0 : tf - tn, af ? af->above_line : NAN, r.n);
            char lab[64]; snprintf(lab, sizeof(lab), "%s %.0f mm/min: nearly-full >= 60 s ahead", s.fdc ? "FDC" : "touch", v);
            CHECK(tn > 0 && tf - tn >= 60, "%s", lab);
            CHECK(af && af->above_line < 2, "%s %.0f mm/min: BATH FULL within 2 mm of the line", s.fdc ? "FDC" : "touch", v);
        }

    // 2. Pause and resume: parent stops the tap to test the water, fetches the kids, turns it back on
    {
        scen_t s = {.name = "Pause the tap 6 min, then resume at 20 mm/min",
                    .who = "Parent stops the fill at a third of the window to check the temperature, comes back later.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 30 M, .level0 = -60,
                    .flow = {{0, 4.25 M, 20}, {10.25 M, 13 M, 20}}, .temp = {{0, 0, 37.5f}}};
        for (int b = 0; b < 2; b++) {
            s.fdc = b == 0;
            run(&s, &r); show(&s, &r);
            const alert_t *af = first(&r, "BATH FULL");
            CHECK(af && af->above_line < 5, "%s: BATH FULL within 5 mm of the line after a pause (got %+.0f)",
                  s.fdc ? "FDC" : "touch", af ? af->above_line : 99);
            double tn = -1;
            for (int i = 0; i < r.n; i++) if (!strcmp(r.a[i].title, "Bath nearly full") && r.a[i].t > 10 M) tn = r.a[i].t;
            CHECK(tn > 0 && first_t(&r, "BATH FULL") - tn >= 40, "%s: a fresh nearly-full after the pause, %.0f s ahead",
                  s.fdc ? "FDC" : "touch", tn > 0 ? first_t(&r, "BATH FULL") - tn : -1);
        }
    }

    // 3. Kids climb in after the bath was filled to the line
    {
        scen_t s = {.name = "Filled to the line, tap off, then two toddlers climb in (+12 mm each) and splash",
                    .who = "Parent fills, double-taps the alarm, then puts the kids in 3 and 4 min later.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 30 M, .level0 = -60,
                    .flow = {{0, 6.25 M, 20}}, .step = {{9 M, 0, 12}, {10 M, 0, 12}},
                    .waves = {{9 M, 25 M, 6}}, .temp = {{0, 0, 37.5f}}, .taps = {6.3 M}};
        run(&s, &r); show(&s, &r);
        CHECK(count(&r, "BATH FILLING AGAIN") == 0, "kids getting in is not a 'filling again' alarm");
        CHECK(count(&r, "BATH") <= 1, "one bath-full alarm for one fill (got %d)", count(&r, "BATH"));
    }

    // 4. Splashing below the line: a wave must not be a "BATH FULL"
    {
        scen_t s = {.name = "Water 8 mm under the line, kids splashing (+-12 mm waves) for 10 min",
                    .who = "Parent filled a little short of the line; the kids play hard.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 25 M, .level0 = -60,
                    .flow = {{0, 5.55 M, 20}}, .step = {{7 M, 0, 0.01f}}, .waves = {{7 M, 17 M, 12}},
                    .temp = {{0, 0, 37.5f}}};
        for (int b = 0; b < 2; b++) {
            s.fdc = b == 0;
            run(&s, &r); show(&s, &r);
            CHECK(count(&r, "BATH") == 0, "%s: no BATH FULL from splashing below the line (got %d)", s.fdc ? "FDC" : "touch",
                  count(&r, "BATH"));
        }
    }

    // 5. A toddler plays with brim (double-tap) while the bath is still filling
    {
        scen_t s = {.name = "Toddler taps brim twice during the fill, before the line is reached",
                    .who = "Kid is already sitting in the filling tub and bangs on the case.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 20 M, .level0 = -60,
                    .flow = {{0, 13 M, 10}}, .waves = {{1 M, 20 M, 4}}, .temp = {{0, 0, 37.5f}}, .taps = {5 M}};
        run(&s, &r); show(&s, &r);
        const alert_t *af = first(&r, "BATH FULL");
        CHECK(af && af->beep, "BATH FULL still beeps on the device after an earlier stray double-tap");
        CHECK(count(&r, "BATH STILL FILLING") >= 1, "repeats still come while the tap stays on");
    }

    // 6. Hot, then mixed down, then a kid turns the hot tap on
    {
        scen_t s = {.name = "Filled hot (41 C), cooled with cold water, later the hot tap goes back on (42 C)",
                    .who = "Common way to run a bath; then an older sibling 'helps' with the hot tap.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 30 M, .level0 = -60,
                    .flow = {{0, 4.5 M, 20}, {15 M, 16 M, 8}},
                    .temp = {{0, 0, 41}, {4 M, 0, 41}, {6 M, 0, 36.5f}, {15 M, 0, 36.5f}, {16 M, 0, 42}}};
        run(&s, &r); show(&s, &r);
        CHECK(count(&r, "Bath too hot") == 2, "too-hot warns again when the water heats up a second time (got %d)",
              count(&r, "Bath too hot"));
        double th = -1;
        for (int i = 0; i < r.n; i++) if (!strcmp(r.a[i].title, "Bath too hot") && r.a[i].t > 15 M) th = r.a[i].t;
        CHECK(th > 0 && th - 15 M <= 90, "second too-hot within 90 s of the hot tap (%.0f s)", th < 0 ? -1 : th - 15 M);
    }

    // 7. brim falls in during the bath
    {
        scen_t s = {.name = "brim knocked off the wall into the water 2 min after the kids got in",
                    .who = "Toddler pulls it out of the bracket.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 20 M, .level0 = -60,
                    .flow = {{0, 5 M, 20}}, .step = {{7 M, 0, 10}}, .waves = {{7 M, 20 M, 5}},
                    .temp = {{0, 0, 37.5f}}, .fall_at = 9 M};
        run(&s, &r); show(&s, &r);
        CHECK(count(&r, "brim is under water") == 1, "'brim is under water' sent when it falls in mid-bath");
        CHECK(count(&r, "BATH") == 0, "no misleading BATH FULL when brim falls in (got %d)", count(&r, "BATH"));
        CHECK(count(&r, "brim is tilted") == 0, "one alert for one fall (no extra 'tilted')");
    }

    // 8. Two baths in a row: drain, refill for the second child
    {
        scen_t s = {.name = "Bath 1 drained, bath 2 run 5 min later",
                    .who = "Siblings bathed one after the other.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 50 M, .level0 = -60,
                    .flow = {{0, 6 M, 20}, {20 M, 26 M, -20}, {31 M, 37 M, 20}}, .temp = {{0, 0, 37.5f}}, .taps = {6.2 M}};
        for (int b = 0; b < 2; b++) {
            s.fdc = b == 0;
            run(&s, &r); show(&s, &r);
            CHECK(count(&r, "BATH FULL") == 2, "%s: second bath gets its own BATH FULL (got %d)", s.fdc ? "FDC" : "touch",
                  count(&r, "BATH FULL"));
            CHECK(count(&r, "Bath nearly full") == 2, "%s: and its own nearly-full (got %d)", s.fdc ? "FDC" : "touch",
                  count(&r, "Bath nearly full"));
        }
    }

    // 9. Wi-Fi down while the bath fills
    {
        scen_t s = {.name = "Router rebooting during the fill",
                    .who = "Nothing reaches the phone: the device itself must speak up.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 20 M, .level0 = -60,
                    .flow = {{0, 8.5 M, 15}}, .temp = {{0, 0, 37.5f}}, .wifi_down0 = 0, .wifi_down1 = 30 M};
        run(&s, &r); show(&s, &r);
        const alert_t *an = first(&r, "Bath nearly full"), *af = first(&r, "BATH FULL");
        CHECK(an && an->beep, "nearly-full beeps locally when it can't be sent");
        CHECK(af && af->beep, "BATH FULL beeps locally");
    }

    // 10. A dribbling tap after the alarm was silenced
    {
        scen_t s = {.name = "Alarm silenced, tap not fully closed (2 mm/min dribble)",
                    .who = "Parent double-taps and walks off; the tap keeps dribbling.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 40 M, .level0 = -60,
                    .flow = {{0, 6.0 M, 20}, {6.0 M, 40 M, 2}}, .temp = {{0, 0, 37.5f}}, .taps = {6.2 M}};
        run(&s, &r); show(&s, &r);
        const alert_t *ag = first(&r, "BATH FILLING AGAIN");
        CHECK(ag && ag->above_line < 15, "a silenced alarm comes back before the water is 15 mm over the line (%s)",
              ag ? "sent" : "never");
    }

    // 11. Kids climb in while the alarm is still sounding (tap off, nobody double-tapped)
    {
        scen_t s = {.name = "Tap off at the alarm, not silenced; kids climb in 2 min later and splash",
                    .who = "Parent turns the tap off but ignores the phone; repeats must stop, kids must not restart them.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 25 M, .level0 = -60,
                    .flow = {{0, 6.0 M, 20}}, .step = {{8 M, 0, 15}}, .waves = {{8 M, 25 M, 6}}, .temp = {{0, 0, 37.5f}}};
        run(&s, &r); show(&s, &r);
        CHECK(count(&r, "BATH STILL FILLING") == 0 && count(&r, "BATH FILLING AGAIN") == 0,
              "no repeats once the tap is off, kids or not (got %d)", count(&r, "BATH") - 1);
    }
    // 12. An adult bath: filled to the line, then a grown-up gets in (+70 mm)
    {
        scen_t s = {.name = "Adult bath: filled to the line, grown-up gets in (+70 mm), soaks 20 min",
                    .who = "brim is upright in its bracket: all sensors under water is not 'brim fell in'.",
                    .fdc = true, .alarm_pad = 6, .temp_limit = 42, .duration = 35 M, .level0 = -60,
                    .flow = {{0, 6.0 M, 20}}, .step = {{9 M, 0, 70}}, .waves = {{9 M, 30 M, 3}}, .temp = {{0, 0, 39}}};
        run(&s, &r); show(&s, &r);
        CHECK(count(&r, "brim is under water") == 0, "an adult getting in is not 'under water'");
        CHECK(count(&r, "BATH") == 1, "one alarm for one fill (got %d)", count(&r, "BATH"));
    }
    // 13. Very fast tap
    {
        scen_t s = {.name = "fast", .who = "", .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 20 M,
                    .level0 = -90, .flow = {{0, 5.0 M, 30}}, .temp = {{0, 0, 37.5f}}};
        for (int b = 0; b < 2; b++) {
            s.fdc = b == 0;
            run(&s, &r);
            double tn = first_t(&r, "Bath nearly full"), tf = first_t(&r, "BATH FULL");
            const alert_t *af = first(&r, "BATH FULL");
            printf("\n   %s 30 mm/min: nearly-full %.0f s ahead, BATH FULL at %+.1f mm\n", s.fdc ? "FDC" : "touch",
                   tn < 0 ? -1 : tf - tn, af ? af->above_line : NAN);
            CHECK(tn > 0 && tf - tn >= 45 && af && af->above_line < 3, "%s: 30 mm/min tap: warning >= 45 s, alarm within 3 mm",
                  s.fdc ? "FDC" : "touch");
        }
    }
    // 14. Robustness: splashing, many random seeds
    printf("\n######## 14. Splashing, 30 random seeds each\n");
    {
        int false_full = 0, false_again = 0, false_under = 0, runs = 0;
        for (g_seed = 1; g_seed <= 30; g_seed++) {
            // (a) 8 mm under the line, +-12 mm waves, both builds
            for (int b = 0; b < 2; b++) {
                scen_t s = {.name = "a", .fdc = b == 0, .alarm_pad = 6, .temp_limit = 38, .duration = 25 M, .level0 = -60,
                            .flow = {{0, 5.55 M, 20}}, .waves = {{7 M, 17 M, 12}}, .temp = {{0, 0, 37.5f}}};
                run(&s, &r); runs++;
                false_full += count(&r, "BATH") > 0;
                if (count(&r, "BATH") > 0) printf("   seed %u %s: BATH FULL at %.0f s, water %+.1f\n", g_seed, s.fdc ? "FDC" : "touch", first_t(&r, "BATH"), first(&r, "BATH")->above_line);
            }
            // (b) at the line, silenced, kids in (+20 mm) splashing +-10 mm for 20 min
            scen_t s = {.name = "b", .fdc = true, .alarm_pad = 6, .temp_limit = 38, .duration = 30 M, .level0 = -60,
                        .flow = {{0, 6.0 M, 20}}, .step = {{8 M, 0, 20}}, .waves = {{8 M, 28 M, 10}},
                        .temp = {{0, 0, 37.5f}}, .taps = {6.3 M}};
            run(&s, &r); runs++;
            false_again += count(&r, "BATH") > 1;
            false_under += count(&r, "brim is under water") > 0;
        }
        g_seed = 12345;
        printf("   %d runs: false BATH FULL below the line %d/60, false re-alarm after silencing %d/30, false 'under water' %d/30\n",
               runs, false_full, false_again, false_under);
        CHECK(false_full == 0, "no false BATH FULL from splashing (%d/60)", false_full);
        CHECK(false_again == 0, "no false re-alarm from kids + splashing (%d/30)", false_again);
        CHECK(false_under == 0, "no false 'under water' (%d/30)", false_under);
    }

    printf("\n%d/%d checks passed\n", checks - fails, checks);
    return fails ? 1 : 0;
}
