/* Host tests for the pure modules: make -C test */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "grip.h"
#include "proto.h"
#include "shaper.h"
#include "turn.h"

static int fails;
#define CHECK(c)                                                       \
    do {                                                               \
        if (!(c)) {                                                    \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c);        \
            fails++;                                                   \
        }                                                              \
    } while (0)
#define NEAR(a, b, tol) CHECK(fabsf((float)(a) - (float)(b)) <= (tol))

static const float DT = 0.02f; /* 50 Hz */
static const float P0 = 101325.0f;

/* Run n samples at pressure p; return the last level. */
static float run(grip_t *g, float p, int n, bool masked)
{
    float l = 0;
    for (int i = 0; i < n; i++)
        l = grip_update(g, p, DT, masked);
    return l;
}

static void test_grip(void)
{
    grip_cfg_t c = grip_default_cfg();
    grip_t g;
    grip_init(&g, &c);

    CHECK(run(&g, P0, 100, false) == 0.0f);
    NEAR(g.baseline, P0, 0.1f);

    /* A small noise-level bump is not a squeeze. */
    CHECK(run(&g, P0 + 60, 5, false) == 0.0f);
    CHECK(!g.active);
    run(&g, P0, 200, false);

    /* A 2 kPa squeeze: active, level rises to 1 as it becomes full scale. */
    float l = run(&g, P0 + 2000, 10, false);
    CHECK(g.active);
    NEAR(l, 1.0f, 1e-4f);
    NEAR(g.range, 2000, 1);
    /* Half that, soon after: about half scale. */
    l = run(&g, P0 + 1000, 5, false);
    CHECK(l > 0.4f && l < 0.55f);
    /* Release ends it. */
    l = run(&g, P0, 2, false);
    CHECK(l == 0.0f && !g.active);

    /* Full scale relaxes toward min_range with a 30 s time constant, so a later soft squeeze
     * by a smaller hand gets bigger. */
    run(&g, P0, 50 * 300, false); /* 10 time constants */
    NEAR(g.range, c.min_range_pa, 5);
    l = run(&g, P0 + 800, 5, false);
    NEAR(l, 1.0f, 1e-3f);
    run(&g, P0, 50, false);

    /* Slow warming (+300 Pa over 60 s) never becomes a squeeze. */
    bool ever = false;
    for (int i = 0; i < 50 * 60; i++) {
        grip_update(&g, P0 + 300.0f * i / (50 * 60), DT, false);
        ever |= g.active;
    }
    CHECK(!ever);
    NEAR(g.baseline, P0 + 300, 30);

    /* A step that stays (e.g. clamped in a drawer) re-zeroes after max_squeeze_s. */
    float pb = g.baseline;
    run(&g, pb + 1500, (int)(c.max_squeeze_s / DT) + 5, false);
    CHECK(!g.active);
    NEAR(g.baseline, pb + 1500, 1);

    /* Masked: no output and the baseline is frozen even under big changes. */
    pb = g.baseline;
    CHECK(run(&g, pb + 3000, 100, true) == 0.0f);
    NEAR(g.baseline, pb, 0.01f);
    /* Unmasked with the hand still squeezing: that counts immediately. */
    CHECK(run(&g, pb + 3000, 1, false) > 0.0f);
}

static shaper_cfg_t shaper_cfg(void)
{
    return (shaper_cfg_t){ .rest_deg = 45, .full_deg = 135, .slew_dps = 600, .max_hold_s = 4,
                           .on_level = 0.03f, .cam_a_mm = 8, .cam_b_mm = 5 };
}

static void test_shaper(void)
{
    /* Cam inverse: endpoints, monotonic, and the forward lift matches. */
    NEAR(shaper_cam_inverse(0, 8, 5), 0, 1e-6f);
    NEAR(shaper_cam_inverse(1, 8, 5), 1, 1e-5f);
    float prev = -1;
    for (int i = 0; i <= 100; i++) {
        float x = i / 100.0f, f = shaper_cam_inverse(x, 8, 5);
        CHECK(f > prev);
        prev = f;
        float t = f * (float)M_PI_2;
        float h = sqrtf(25 * cosf(t) * cosf(t) + 64 * sinf(t) * sinf(t));
        NEAR((h - 5) / 3, x, 1e-4f);
    }
    NEAR(shaper_cam_inverse(0.3f, 0, 0), 0.3f, 1e-6f); /* off */

    shaper_cfg_t c = shaper_cfg();
    shaper_t s;
    shaper_init(&s, &c);
    CHECK(!shaper_busy(&s));

    /* Slew: one 20 ms tick moves at most 12 deg. */
    float a = shaper_update(&s, 1.0f, DT);
    NEAR(a, 57, 0.01f);
    CHECK(shaper_busy(&s));
    for (int i = 0; i < 20; i++)
        a = shaper_update(&s, 1.0f, DT);
    NEAR(a, 135, 0.01f);

    /* Hold limit: relaxes after 4 s although the partner still squeezes... */
    for (int i = 0; i < (int)(4.0f / DT) + 20; i++)
        a = shaper_update(&s, 1.0f, DT);
    NEAR(a, 45, 0.01f);
    /* ...and works again after a release. */
    shaper_update(&s, 0.0f, DT);
    for (int i = 0; i < 20; i++)
        a = shaper_update(&s, 1.0f, DT);
    NEAR(a, 135, 0.01f);

    /* Below on_level is rest. */
    for (int i = 0; i < 20; i++)
        a = shaper_update(&s, 0.02f, DT);
    NEAR(a, 45, 0.01f);
    CHECK(!shaper_busy(&s));

    /* A gentler unit (child's) and a reversed servo both stay in range. */
    c.full_deg = 45 - 65;
    shaper_init(&s, &c);
    for (int i = 0; i < 30; i++)
        a = shaper_update(&s, 1.0f, DT);
    NEAR(a, -20, 0.01f);
}

static void test_turn(void)
{
    turn_t t;
    turn_init(&t, 150);
    uint32_t now = 1000;
    turn_out_t o = turn_update(&t, false, false, false, now);
    CHECK(!o.send && !o.play && !o.mask);

    /* Local squeeze: TALK, ignoring the partner. */
    o = turn_update(&t, true, false, false, now += 20);
    CHECK(o.send && !o.play);
    o = turn_update(&t, true, true, false, now += 20);
    CHECK(o.send && !o.play);
    /* Let go: keeps sending (zeros) for the 150 ms tail, then IDLE. */
    o = turn_update(&t, false, false, false, now += 20);
    CHECK(o.send);
    o = turn_update(&t, false, false, false, now += 140);
    CHECK(o.send);
    o = turn_update(&t, false, false, false, now += 20);
    CHECK(!o.send && t.st == TURN_IDLE);

    /* Partner squeezes: LISTEN, mask the local pressure. */
    o = turn_update(&t, false, true, false, now += 20);
    CHECK(o.play && o.mask && !o.send);
    /* Local "squeeze" while listening is the plates pushing: stays LISTEN. */
    o = turn_update(&t, true, true, true, now += 20);
    CHECK(o.play && !o.send);
    /* Partner lets go but the plates are still returning: still LISTEN. */
    o = turn_update(&t, false, false, true, now += 200);
    CHECK(o.play);
    /* Plates at rest: tail, then IDLE. */
    o = turn_update(&t, false, false, false, now += 20);
    CHECK(o.play);
    o = turn_update(&t, false, false, false, now += 160);
    CHECK(t.st == TURN_IDLE && !o.mask);

    /* Tie: local wins. */
    o = turn_update(&t, true, true, false, now += 20);
    CHECK(o.send && !o.play);

    /* Clock wrap. */
    turn_init(&t, 150);
    now = 0xFFFFFFF0u;
    turn_update(&t, true, false, false, now);
    turn_update(&t, false, false, false, now += 10);
    o = turn_update(&t, false, false, false, now += 100);
    CHECK(o.send);
    o = turn_update(&t, false, false, false, now += 60);
    CHECK(!o.send);
}

static void test_proto(void)
{
    uint32_t id = sq_pair_id("our-secret");
    CHECK(id == sq_pair_id("our-secret"));
    CHECK(id != sq_pair_id("our-secreT"));
    CHECK(sq_pair_id("") == 2166136261u);
    CHECK(sq_pair_id("a") == 0xe40c292cu); /* FNV-1a reference value */

    uint8_t b[SQ_PKT_LEN];
    sq_msg_t m = { .type = SQ_LEVEL, .seq = 0xBEEF, .level = 200, .flags = SQ_FLAG_CHARGING }, r;
    CHECK(sq_pack(b, id, &m) == SQ_PKT_LEN);
    CHECK(sq_unpack(b, sizeof b, id, &r));
    CHECK(r.type == SQ_LEVEL && r.seq == 0xBEEF && r.level == 200 && r.flags == SQ_FLAG_CHARGING);

    CHECK(!sq_unpack(b, sizeof b, id + 1, &r)); /* another pair */
    CHECK(!sq_unpack(b, sizeof b - 1, id, &r)); /* short */
    uint8_t x[SQ_PKT_LEN];
    memcpy(x, b, sizeof b);
    x[0] = 'X';
    CHECK(!sq_unpack(x, sizeof x, id, &r));
    memcpy(x, b, sizeof b);
    x[2] = 2;
    CHECK(!sq_unpack(x, sizeof x, id, &r)); /* future version */
    memcpy(x, b, sizeof b);
    x[3] = 0;
    CHECK(!sq_unpack(x, sizeof x, id, &r));
    x[3] = 6;
    CHECK(!sq_unpack(x, sizeof x, id, &r));

    CHECK(sq_seq_accept(11, 10));
    CHECK(!sq_seq_accept(10, 10)); /* duplicate */
    CHECK(!sq_seq_accept(9, 10));  /* late */
    CHECK(sq_seq_accept(2, 0xFFFE)); /* wrap */
    CHECK(sq_seq_accept(5, 5000));   /* partner restarted */
}

int main(void)
{
    test_grip();
    test_shaper();
    test_turn();
    test_proto();
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("all tests passed\n");
    return 0;
}
