// Host unit tests for the pure firmware logic: level estimation, fill rate, notification policy.
//   make -C firmware/test
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "../main/level.h"
#include "../main/policy.h"
#include "../main/rate.h"

static int fails, checks;
#define CHECK(cond, ...) do { checks++; if (!(cond)) { fails++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

// --- pad model: linear over the pad with ~1 mm fringe each side (matches electrode_sim.py) ---
static const float BASE[LVL_CH] = {20000, 19500, 19800, 20200, 19900, 20100, 15000};
static const float FULL_FRAC[LVL_CH] = {0.30f, 0.32f, 0.31f, 0.33f, 0.32f, 0.31f, 0.21f};   // true wet gains

static float frac_model(float level, float bottom, float h)
{
    float f = (level - (bottom - 1.0f)) / (h + 2.0f);
    return f < 0 ? 0 : (f > 1 ? 1 : f);
}

static void sample(float level, float drift, float film_pad, float film_frac, uint32_t raw[LVL_CH])
{
    for (int k = 0; k < LVL_PADS; k++) {
        float f = frac_model(level, k * 10.0f, 9.0f);
        if (k == (int)film_pad) f = fmaxf(f, film_frac);
        raw[k] = (uint32_t)(BASE[k] * (1 + drift) + BASE[k] * FULL_FRAC[k] * f);
    }
    float fr = frac_model(level, 63.0f, 6.0f);
    raw[LVL_REF] = (uint32_t)(BASE[LVL_REF] * (1 + drift) + BASE[LVL_REF] * FULL_FRAC[LVL_REF] * fr);
}

static void test_level(void)
{
    lvl_cal_t cal;
    uint32_t raw[LVL_CH];
    sample(-10, 0, -1, 0, raw);
    lvl_cal_init(&cal, raw);

    // a first fill teaches each pad's full-wet value; a second fill is then accurate
    for (float L = -5; L <= 62; L += 0.5f) { sample(L, 0, -1, 0, raw); lvl_compute(&cal, raw); }
    float worst = 0;
    for (float L = 5; L <= 58; L += 0.5f) {   // below ~4.5 mm PAD1 is not yet 'wet' (by design)
        sample(L, 0, -1, 0, raw);
        lvl_result_t r = lvl_compute(&cal, raw);
        float err = fabsf(r.level_mm - L);
        if (err > worst) worst = err;
    }
    printf("  level: worst error over 5..58 mm after one learning fill = %.2f mm\n", worst);
    CHECK(worst < 2.0f, "level error %.2f mm", worst);

    // dry: not wet, level 0
    sample(-10, 0, -1, 0, raw);
    lvl_result_t r = lvl_compute(&cal, raw);
    CHECK(!r.wet && r.level_mm == 0, "dry should read not-wet");

    // water film: pad 4 looks 45 % wet while the water is only at mid pad 2 -> must be ignored
    sample(15, 0, 3, 0.45f, raw);
    r = lvl_compute(&cal, raw);
    CHECK(fabsf(r.level_mm - 15) < 1.5f, "film on pad 4 moved the level to %.1f", r.level_mm);
    CHECK(r.frac[3] == 0, "film pad should be chained out");

    // drift: +3 % on everything (warm board), REF still dry -> compensated
    sample(25, 0.03f, -1, 0, raw);
    r = lvl_compute(&cal, raw);
    CHECK(fabsf(r.level_mm - 25) < 1.5f, "3 %% drift gave %.1f mm", r.level_mm);
    sample(-10, 0.03f, -1, 0, raw);
    r = lvl_compute(&cal, raw);
    CHECK(!r.wet, "3 %% drift alone must not read wet");

    // submerged: everything wet
    sample(80, 0, -1, 0, raw);
    r = lvl_compute(&cal, raw);
    CHECK(r.all_wet && r.ref_wet && fabsf(r.level_mm - 60) < 0.01f && r.top_full == 6, "submerged: all %d ref %d (%.2f) level %.1f top %d", r.all_wet, r.ref_wet, r.raw_frac[LVL_REF], r.level_mm, r.top_full);
    CHECK(fabsf(lvl_pad_top_mm(6) - 59) < 0.01f && fabsf(lvl_pad_top_mm(1) - 9) < 0.01f, "pad tops");
}

static void test_rate(void)
{
    rate_t r;
    rate_init(&r, 60);
    float v;
    CHECK(!rate_mm_per_min(&r, &v), "no rate with no samples");
    for (int i = 0; i <= 30; i++) rate_add(&r, i * 2.0f, 10 + i * 2.0f * (2.0f / 60.0f));   // 2 mm/min
    CHECK(rate_mm_per_min(&r, &v) && fabsf(v - 2.0f) < 0.05f, "rate %.2f", v);
    float eta = rate_eta_s(&r, 12, 16);
    CHECK(fabsf(eta - 120) < 5, "eta %.0f s", eta);
}

static int run_bath(policy_t *p, int alarm_pad, float fill_mm_min, float stop_at_mm, float temp, int *n_alarm, int *n_nearly,
                    int *n_hot, float *t_alarm)
{
    lvl_cal_t cal; uint32_t raw[LVL_CH]; rate_t rt;
    sample(-10, 0, -1, 0, raw); lvl_cal_init(&cal, raw);
    for (float L = -5; L <= 62; L += 1) { sample(L, 0, -1, 0, raw); lvl_compute(&cal, raw); }   // learning
    rate_init(&rt, 60);
    int n = 0; *n_alarm = *n_nearly = *n_hot = 0; *t_alarm = -1;
    float level = -3;
    for (float t = 0; t < 3600; t += 2) {
        if (level < stop_at_mm) level += fill_mm_min * 2 / 60.0f;
        sample(level, 0, -1, 0, raw);
        lvl_result_t r = lvl_compute(&cal, raw);
        if (r.wet) rate_add(&rt, t, r.level_mm);
        policy_in_t in = {.now_s = t, .wet = r.wet, .all_wet = r.all_wet, .level_mm = r.level_mm,
                          .at_alarm = r.top_full >= alarm_pad, .ref_frac = r.raw_frac[LVL_REF],
                          .temp_c = temp, .battery_pct = 80};
        in.rate_ok = rate_mm_per_min(&rt, &in.rate_mm_min);
        in.eta_s = rate_eta_s(&rt, r.level_mm, p->alarm_mm - 1.0f);
        policy_out_t o;
        if (policy_step(p, &in, &o)) {
            n++;
            if (o.ev == EV_ALARM) { (*n_alarm)++; if (*t_alarm < 0) *t_alarm = t; }
            if (o.ev == EV_NEARLY_FULL) (*n_nearly)++;
            if (o.ev == EV_TOO_HOT) (*n_hot)++;
        }
    }
    return n;
}

static void test_policy(void)
{
    policy_t p; int na, nn, nh; float ta;
    // normal bath: 2 mm/min, tap turned off 5 mm above the target -> one alarm + a few repeats, one "nearly"
    policy_init(&p, lvl_pad_top_mm(6), 42, false);
    run_bath(&p, 6, 2.0f, 64, 38.5f, &na, &nn, &nh, &ta);
    printf("  policy: alarms %d, nearly-full %d, too-hot %d, first alarm at %.0f s\n", na, nn, nh, ta);
    CHECK(na >= 2 && na <= 4, "alarm count %d (first + repeats while still rising)", na);
    CHECK(nn == 1, "nearly-full sent %d times", nn);
    CHECK(nh == 0, "too-hot sent at 38.5 C");
    // forgotten tap at 3 mm/min that never stops: repeats are capped at 15 min
    policy_init(&p, lvl_pad_top_mm(6), 42, false);
    run_bath(&p, 6, 3.0f, 1000, 43.0f, &na, &nn, &nh, &ta);
    CHECK(na <= 17, "alarm repeats not capped: %d", na);
    CHECK(nh == 1, "too-hot sent %d times", nh);
    // alarm at pad 3 fires earlier
    policy_init(&p, lvl_pad_top_mm(3), 42, false);
    float ta3; run_bath(&p, 3, 2.0f, 40, 38, &na, &nn, &nh, &ta3);
    CHECK(ta3 > 0 && ta3 < ta, "pad-3 alarm %.0f s should come before pad-6 alarm %.0f s", ta3, ta);
    // low battery once
    policy_init(&p, 59, 42, false);
    policy_in_t in = {.now_s = 0, .temp_c = NAN, .battery_pct = 15}; policy_out_t o;
    CHECK(policy_step(&p, &in, &o) && o.ev == EV_LOW_BATTERY, "low battery");
    in.now_s = 10;
    CHECK(!policy_step(&p, &in, &o), "low battery repeated");
}

int main(void)
{
    printf("level\n"); test_level();
    printf("rate\n"); test_rate();
    printf("policy\n"); test_policy();
    printf("%d/%d checks passed\n", checks - fails, checks);
    return fails ? 1 : 0;
}
