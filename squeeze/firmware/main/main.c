/* squeeze: two hand-held units that pass squeezes back and forth.
 *
 * Doze (most of the time): light sleep. Every 100 ms a fast pressure sample (is my holder squeezing?);
 * every SLEEP_PERIOD_MS (DEEP_PERIOD_MS after RECENT_S) the radio listens for 30 ms (is my partner
 * calling?). A squeeze of 0.1 s or longer wakes it. (A flat battery is the only reason for deep sleep.)
 *
 * Session: 50 Hz loop. Squeeze -> level -> radio. Partner's level -> plates. Turn-taking (turn.c)
 * decides which way squeezes flow; duplex sensing lets a squeeze made during the partner's playback
 * through. A squeeze is sent once confirmed (not a pickup). Squeezes made while the partner wakes are kept and
 * replayed when it answers; the receiver plays at the real pace and skips silence to catch up.
 * 90 s with no squeeze on either side -> BYE -> doze.
 *
 * USB attached at power-on: self-test first (bring-up, docs/design.md section 9).
 * See docs/design.md section 7 for the behaviour and the LED legend, docs/virtual-experiments.md for the
 * simulated bring-up and usability runs that shaped it.
 */
#include <math.h>

#include "bmp280.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "grip.h"
#include "hw.h"
#include "radio.h"
#include "sdkconfig.h"
#include "shaper.h"
#include "turn.h"

static const char *TAG = "squeeze";

#define TICK_MS          20
#define DT               (TICK_MS / 1000.0f)
#define DOZE_SAMPLE_MS   100    /* asleep: pressure sample period */
#define DOZE_CONV_MS     7      /* BMP280 forced x1 conversion, slept through */
#define LISTEN_MS        30     /* asleep: how long to listen for WAKE (sent every 20 ms) each listen period */
#define WAKE_PA_MIN      100.0f /* asleep: smallest rise that wakes (a 6-year-old's gentle squeeze is ~150+) */
#define WAKE_SIGMAS      8.0f   /* ...or 8 x the measured sensor noise, whichever is larger */
#define CALL_MS          (CONFIG_SQZ_DEEP_PERIOD_MS + 1500)   /* longer than the partner's slowest listen period */
#define FIFO_N           512    /* replay outbox / playback queue: 10 s at 50 Hz */
#define CONFIRM_LEVEL    0.5f   /* a squeeze this strong (0.5 s average) is sent at once; weaker ones when released */
#define STRONG_LEVEL     0.6f   /* ...or this strong for STRONG_TICKS in a row (a pickup + tremor is not) */
#define STRONG_TICKS     2
#define GENTLE_MAX_S     1.5f   /* a gentle squeeze counts if released within this; longer = picked up */
#define MIN_SENT_LEVEL   0.25f  /* a squeeze is sent at least this strong */
#define GENTLE_MIN_S     0.12f  /* ...and if it lasted this long (shorter: a tremor blip) */
#define PARTNER_LOST_MS  3000   /* no heartbeat for this long = partner asleep / out of range */
#define REMOTE_STALE_MS  250    /* no LEVEL frame for this long = partner let go (link loss safety) */
#define INVITE_MS        60000  /* woken by the partner: glow its colour for up to a minute */
#define UNREACHED_MS     1200   /* a call nobody answered: blink own colour */
#define CATCHUP_FRAMES   4      /* replay: frames sent per tick while catching up */
#define KEEP_GAP_TICKS   30     /* replay: pauses longer than 0.6 s are shortened to 0.6 s */
#define MIN_GAP_TICKS    6      /* playback: a pause between two squeezes lasts at least 120 ms, so the
                                 * plates open far enough to be felt as two (fast children's patterns) */
#define VBAT_LOW_MV      3500   /* red blink, LOW_BATT flag */
#define VBAT_NO_SERVO_MV 3400   /* plates off, LED only */
#define VBAT_EMPTY_MV    3300   /* deep sleep 60 s at a time, no radio, until charged */

#if CONFIG_SQZ_ROLE_PARENT
#define COLOR_SELF    CONFIG_SQZ_COLOR_PARENT
#define COLOR_PARTNER CONFIG_SQZ_COLOR_CHILD
#else
#define COLOR_SELF    CONFIG_SQZ_COLOR_CHILD
#define COLOR_PARTNER CONFIG_SQZ_COLOR_PARENT
#endif
#define COLOR_CHARGING 0x00FF30
#define COLOR_LOW      0xFF0000

typedef enum { WOKE_POWER_ON, WOKE_BY_SQUEEZE, WOKE_BY_PARTNER } woke_t;

static float rest_pa;     /* resting pressure, tracked while dozing */
static bool have_rest;
static float noise_var = 15.0f * 15.0f;   /* doze samples: variance around rest_pa (Pa^2) */

static uint32_t now_ms(void) { return (uint32_t)(esp_timer_get_time() / 1000); }

static void light_sleep_ms(uint32_t ms)
{
    esp_sleep_enable_timer_wakeup((uint64_t)ms * 1000ULL);
    esp_light_sleep_start();
}

static bool battery_empty(void)
{
    return power_vbat_mv() < VBAT_EMPTY_MV && !power_charging() && !power_usb();
}

static void empty_battery_sleep(void)
{
    servo_off();
    led_rgb(0, 0);
    radio_pause();
    bmp280_sleep();
    esp_sleep_enable_timer_wakeup(60ULL * 1000 * 1000);
    esp_deep_sleep_start();
}

/* Asleep. Returns why it woke. */
static woke_t doze(bool sensor_ok)
{
    radio_pause();
    servo_off();
    led_rgb(0, 0);
    if (sensor_ok)
        bmp280_sleep();
    uint32_t start = now_ms(), next_listen = start + CONFIG_SQZ_SLEEP_PERIOD_MS, next_vbat = start;
    for (;;) {
        light_sleep_ms(DOZE_SAMPLE_MS - DOZE_CONV_MS);
        if (sensor_ok && bmp280_start_fast() == ESP_OK) {
            light_sleep_ms(DOZE_CONV_MS);
            float pa;
            if (bmp280_read(&pa) == ESP_OK) {
                float wake_pa = fmaxf(WAKE_PA_MIN, WAKE_SIGMAS * sqrtf(noise_var));
                if (have_rest && pa - rest_pa > wake_pa)
                    return WOKE_BY_SQUEEZE;
                /* follow drift (~2 s time constant) and learn the noise, but not during a rise in progress:
                 * a slow squeeze must not drag the reference up with it */
                if (!have_rest) {
                    rest_pa = pa;
                } else if (pa - rest_pa < wake_pa / 3) {
                    float e = pa - rest_pa;
                    noise_var += (e * e - noise_var) * 0.01f;    /* ~10 s */
                    rest_pa += e * 0.05f;
                }
                have_rest = true;
            }
        }
        uint32_t now = now_ms();
        if ((int32_t)(now - next_vbat) >= 0) {
            next_vbat = now + 60000;
            if (battery_empty())
                empty_battery_sleep();
        }
        if ((int32_t)(now - next_listen) >= 0) {
            /* fast for a while after a session (another round is likely), then slower to save the battery */
            next_listen = now + (now - start < CONFIG_SQZ_RECENT_S * 1000u ? CONFIG_SQZ_SLEEP_PERIOD_MS
                                                                            : CONFIG_SQZ_DEEP_PERIOD_MS);
            radio_resume();
            uint32_t until = now_ms() + LISTEN_MS;
            sq_msg_t m;
            for (int32_t left; (left = (int32_t)(until - now_ms())) > 0;)
                if (radio_recv(&m, left) && m.type == SQ_WAKE)
                    return WOKE_BY_PARTNER;
            radio_pause();
        }
    }
}

static float breathe(uint32_t t, uint32_t period_ms)
{
    float ph = (float)(t % period_ms) / (float)period_ms;
    return 0.5f - 0.5f * cosf(2.0f * (float)M_PI * ph);
}

/* ---------------- level FIFOs: replay outbox (sender) and playback queue (receiver) ---------------- */
typedef struct { uint8_t v[FIFO_N]; uint16_t head, n; } fifo_t;
static void fifo_push(fifo_t *f, uint8_t x)
{
    if (f->n == FIFO_N) { f->head = (f->head + 1) % FIFO_N; f->n--; }   /* full: drop the oldest */
    f->v[(f->head + f->n) % FIFO_N] = x;
    f->n++;
}
static uint8_t fifo_pop(fifo_t *f) { uint8_t x = f->v[f->head]; f->head = (f->head + 1) % FIFO_N; f->n--; return x; }
static uint8_t fifo_peek(const fifo_t *f, int i) { return f->v[(f->head + i) % FIFO_N]; }

static void session(woke_t woke, bool sensor_ok)
{
    radio_resume();
    if (sensor_ok)
        bmp280_start_stream();

    grip_cfg_t gc = grip_default_cfg();
    grip_t grip;
    grip_init(&grip, &gc);
    if (woke == WOKE_BY_SQUEEZE && have_rest) {
        /* The holder is squeezing right now: start from the resting pressure measured while dozing
         * (at most ~100 ms old), not from this squeezed one. */
        grip.init = true;
        grip.baseline = rest_pa;
    }

    shaper_cfg_t sc = {
        .rest_deg = CONFIG_SQZ_SERVO_REST_DEG,
        .full_deg = CONFIG_SQZ_SERVO_REST_DEG + CONFIG_SQZ_SWELL_DEG,
        .slew_dps = 600, /* SG90: ~0.1 s per 60 deg */
        .max_hold_s = 4,
        .hold_level = 0.4f,
        .on_level = 0.03f,
        .cam_a_mm = 8, /* hardware/mech/squeeze_unit.py CAM_A / CAM_B */
        .cam_b_mm = 5,
    };
    shaper_t shaper;
    shaper_init(&shaper, &sc);
    turn_t turn;
    turn_init(&turn, 150);
    static fifo_t outq, playq, staged;
    outq.n = playq.n = staged.n = 0;
    bool confirmed = false;          /* the current squeeze is real (strong enough, or released in time) */
    bool turn_sent = false;
    int zero_run = 0;                /* playback: consecutive silent ticks played */
    bool had_level = false;          /* something real was sent this turn: its tail follows */
    float k_own = 400.0f;            /* Pa per mm of own-plate lift in this hand (learned while playing) */

    uint32_t t0 = now_ms();
    uint32_t last_activity = t0, last_hb = 0, last_vbat = 0, partner_seen = 0, last_frame = 0;
    uint32_t call_start = t0, invite_until = 0, unreached_until = 0, trace = 0;
    bool partner_awake = false, partner_low = false, calling = woke == WOKE_POWER_ON, mask = false;
    uint8_t remote_level = 0;
    int vbat = power_vbat_mv();
    bool on_usb = power_usb(); /* USB-C plugged in: never doze */
    float pa = rest_pa;

    if (woke == WOKE_BY_PARTNER) {
        radio_send(SQ_AWAKE, 0, 0);
        partner_awake = true;
        partner_seen = t0;
        invite_until = t0 + INVITE_MS;
    }
    ESP_LOGI(TAG, "awake (%s), battery %d mV", woke == WOKE_POWER_ON ? "power on" :
             woke == WOKE_BY_SQUEEZE ? "squeezed" : "partner called", vbat);

    TickType_t wake_tick = xTaskGetTickCount();
    for (;;) {
        uint32_t now = now_ms();

        if (now - last_vbat >= 1000) {
            last_vbat = now;
            vbat = power_vbat_mv();
            on_usb = power_usb();
        }
        bool charging = power_charging();
        bool low = vbat < VBAT_LOW_MV;
        uint8_t flags = (charging ? SQ_FLAG_CHARGING : 0) | (low ? SQ_FLAG_LOW_BATT : 0);

        /* --- this holder --- */
        if (sensor_ok)
            bmp280_read(&pa);
        float level = 0.0f;
        bool was_active = grip.active;
        static int strong_ticks;
#if CONFIG_SQZ_DUPLEX
        /* Own plates pushing into the hand raise the pressure too: subtract the learned share plus a margin, and
         * keep the baseline still. What is left over is the holder squeezing (also during the partner's turn). */
        float lift = shaper_lift_mm(&shaper);
        bool own = shaper_busy(&shaper);
        grip.freeze = own;
        float comp = own ? k_own * lift * 1.1f + 60.0f : 0.0f;
        if (sensor_ok)
            level = grip_update(&grip, pa - comp, DT, false);
        if (own && lift > 1.0f && !grip.active) {
            float ko = (pa - grip.baseline) / lift;
            /* the holder can only add pressure: learn down fast, up slowly (a squeeze during playback is not
             * taken for the plates) */
            ko = fminf(fmaxf(ko, 0.0f), 1500.0f);
            k_own += (ko - k_own) * (ko < k_own ? 0.1f : 0.005f);
        }
        (void)mask;
#else
        if (sensor_ok)
            level = grip_update(&grip, pa, DT, mask);
#endif
        if (grip.active) {
            last_activity = now;
            invite_until = 0;
        }
        strong_ticks = (grip.active && level >= STRONG_LEVEL) ? strong_ticks + 1 : 0;   /* 40 ms that strong: not tremor */
        /* a weak rise that turned out to be a grip (picked up) is dropped; a real one is confirmed */
        if (grip.rezeroed) {
            staged.n = 0;
            confirmed = false;
        } else if (grip.active && !confirmed && (strong_ticks >= STRONG_TICKS || grip.level_avg >= CONFIRM_LEVEL)) {
            confirmed = true;
        } else if (was_active && !grip.active && !confirmed && staged.n &&
                   grip.active_s >= GENTLE_MIN_S && grip.active_s <= GENTLE_MAX_S) {
            confirmed = true;   /* a gentle squeeze, released quickly: send it now, whoever has the turn */
            while (staged.n)
                fifo_push(&outq, fifo_pop(&staged));
            fifo_push(&outq, 0);
            turn_sent = true;
        } else if (was_active && !grip.active && !confirmed) {
            staged.n = 0;       /* a weak, long rise and fall: picked up and put down */
        }
        if (!grip.active && !was_active)
            confirmed = false;

        /* --- the partner --- */
        sq_msg_t m;
        while (radio_recv(&m, 0)) {
            partner_awake = true;
            partner_seen = now;
            partner_low = m.flags & SQ_FLAG_LOW_BATT;
            switch (m.type) {
            case SQ_LEVEL:
                fifo_push(&playq, m.level);
                last_frame = now;
                if (m.level)
                    last_activity = now;
                break;
            case SQ_WAKE:
                radio_send(SQ_AWAKE, 0, flags);
                break;
            case SQ_BYE:
                partner_awake = false;
                break;
            default: /* AWAKE, HEARTBEAT */
                break;
            }
        }
        if (now - partner_seen > PARTNER_LOST_MS)
            partner_awake = false;
        if (partner_awake)
            calling = false;
        /* While this holder has the turn, the partner's frames wait (played when it ends: nothing is lost). */
        bool hold_playback = turn.st == TURN_TALK;
        /* playback at the real pace. After a replay, catch up by shortening only the long pauses: gaps up to
         * KEEP_GAP_TICKS stay intact, because the rhythm is the game. */
        {
            int run = 0;
            while (run < playq.n && fifo_peek(&playq, run) == 0)
                run++;
            while (run > KEEP_GAP_TICKS && playq.n > run) {
                fifo_pop(&playq);
                run--;
            }
        }
        if (hold_playback)
            remote_level = 0;
        else if (playq.n && fifo_peek(&playq, 0) && zero_run > 0 && zero_run < MIN_GAP_TICKS && had_level)
            remote_level = 0;   /* stretch a short pause; the queue catches up in the next long one */
        else if (playq.n)
            remote_level = fifo_pop(&playq);
        else if (now - last_frame > REMOTE_STALE_MS)
            remote_level = 0;
        if (remote_level) {
            zero_run = 0;
            had_level = true;
        } else if (zero_run < 1000) {
            zero_run++;
        }
        bool remote_active = !hold_playback && remote_level > 0 && (playq.n > 0 || now - last_frame < REMOTE_STALE_MS);

        /* --- turn-taking --- */
        turn_out_t o = turn_update(&turn, grip.active, remote_active, shaper_busy(&shaper), now);
        /* send: our turn, or a squeeze that started during the partner's (duplex). Unconfirmed frames wait. */
        if (o.send || (o.play && grip.active)) {
            /* every squeeze arrives strong enough to feel (a gentle one, or one squeezed against the plates) */
            uint8_t v = (uint8_t)lroundf((grip.active ? fmaxf(level, MIN_SENT_LEVEL) : 0.0f) * 255.0f);
            if (confirmed) {
                while (staged.n)
                    fifo_push(&outq, fifo_pop(&staged));
                fifo_push(&outq, v);
                turn_sent = true;
            } else if (grip.active) {
                fifo_push(&staged, v);
            } else if (turn_sent) {
                fifo_push(&outq, v);   /* the tail after a real squeeze (not after a discarded grip) */
            }
        }
        if (turn.st == TURN_IDLE)
            turn_sent = false;
        if (partner_awake)   /* live, or catching up on what was squeezed while the partner woke */
            for (int k = 0; k < CATCHUP_FRAMES && outq.n; k++)
                radio_send(SQ_LEVEL, fifo_pop(&outq), flags);
        if (outq.n && !partner_awake && !calling) {   /* a confirmed squeeze waits: wake the partner */
            calling = true; /* partner asleep: wake it (the squeeze waits in the outbox) */
            call_start = now;
        }
        if (calling) {
            radio_send(SQ_WAKE, 0, flags);
            if (now - call_start > CALL_MS) {
                calling = false;
                if (!partner_awake) {
                    unreached_until = now + UNREACHED_MS;   /* tell the holder: nobody answered */
                    outq.n = 0;
                }
            }
        }
        if (now - last_hb >= 1000) {
            last_hb = now;
            radio_send(SQ_HEARTBEAT, 0, flags);
        }

        /* --- plates --- */
        float target = (o.play && remote_active) ? remote_level / 255.0f : 0.0f; /* stale = let go */
        if (vbat < VBAT_NO_SERVO_MV)
            target = 0.0f;
        float angle = shaper_update(&shaper, target, DT);
        servo_set(angle, !shaper_busy(&shaper), now);
        /* Our own plates moving raise our own pressure: not the holder squeezing (when not compensating). */
        mask = o.mask || shaper_busy(&shaper);

        /* --- LED (legend: docs/design.md section 7) --- */
        if (o.play && remote_active)
            led_rgb(COLOR_PARTNER, 0.25f + 0.75f * remote_level / 255.0f);
        else if (o.send && grip.active)
            led_rgb(COLOR_SELF, 0.20f + 0.60f * level);
        else if ((int32_t)(unreached_until - now) > 0)
            led_rgb(COLOR_SELF, ((now / 150) & 1) ? 0.6f : 0.0f);
        else if (calling)
            led_rgb(COLOR_SELF, 0.15f + 0.45f * breathe(now, 500));
        else if ((int32_t)(invite_until - now) > 0)
            led_rgb(COLOR_PARTNER, 0.15f + 0.55f * breathe(now, 2500));
        else if (low && (now % 2000) < 150)
            led_rgb(COLOR_LOW, 0.5f);
        else if (charging)
            led_rgb(COLOR_CHARGING, 0.15f);
        else if (partner_awake && partner_low && (now % 4000) < 150)
            led_rgb(COLOR_LOW, 0.3f);                       /* the other unit needs charging */
        else if (partner_awake)
            led_rgb(COLOR_PARTNER, 0.12f);
        else
            led_rgb(0, 0);

#if CONFIG_SQZ_TRACE
        if (now - trace >= 200) {
            trace = now;
            ESP_LOGI(TAG, "p=%.0f base=%.0f range=%.0f lvl=%.2f | turn=%d remote=%u q=%u ang=%.0f | %s vbat=%d",
                     pa, grip.baseline, grip.range, level, turn.st, remote_level, playq.n, angle,
                     partner_awake ? "partner" : "alone", vbat);
        }
#else
        (void)trace;
#endif

        /* --- doze --- */
        bool idle = now - last_activity > CONFIG_SQZ_SESSION_IDLE_S * 1000u;
        if (!on_usb && idle && turn.st == TURN_IDLE && !shaper_busy(&shaper)) {
            ESP_LOGI(TAG, "idle: dozing");
            for (int i = 0; i < 3; i++) {
                radio_send(SQ_BYE, 0, flags);
                vTaskDelay(pdMS_TO_TICKS(5));
            }
            led_rgb(0, 0);
            if (grip.init) {
                rest_pa = grip.baseline;
                have_rest = true;
            }
            return;
        }
        if (vbat < VBAT_EMPTY_MV && !charging && !on_usb)
            empty_battery_sleep();

        vTaskDelayUntil(&wake_tick, pdMS_TO_TICKS(TICK_MS));
    }
}

/* USB attached at power-on: a bench self-test, logged on the USB console (docs/design.md section 9). */
static void selftest(bool sensor_ok)
{
    static const char *T = "selftest";
    int fails = 0;
    ESP_LOGI(T, "USB attached at power-on: self-test");
    int vb = power_vbat_mv();
    bool ok = vb > 3300 && vb < 4300;
    fails += !ok;
    ESP_LOGI(T, "battery %d mV: %s", vb, ok ? "PASS" : "FAIL (expected 3.3-4.3 V: battery fitted and charged?)");
    ESP_LOGI(T, "charger CHG: %s", power_charging() ? "charging (on a Qi pad)" : "not charging");
    if (sensor_ok) {
        float pa = 0;
        ok = bmp280_one_shot(&pa) == ESP_OK && pa > 70000 && pa < 110000;
        fails += !ok;
        ESP_LOGI(T, "pressure sensor: %.0f Pa: %s", pa, ok ? "PASS" : "FAIL (expected 70-110 kPa)");
    } else {
        fails++;
        ESP_LOGE(T, "pressure sensor: FAIL (no BMP280 at 0x76: check U4 soldering)");
    }
    static const uint32_t col[3] = { 0xFF0000, 0x00FF00, 0x0000FF };
    static const char *cn[3] = { "red", "green", "blue" };
    for (int i = 0; i < 3; i++) {
        ESP_LOGI(T, "LED %s for 0.4 s: look", cn[i]);
        led_rgb(col[i], 1.0f);
        vTaskDelay(pdMS_TO_TICKS(400));
    }
    led_rgb(0, 0);
    ESP_LOGI(T, "servo: rest -> full swell -> rest (watch the plates move 3 mm and back; no buzzing at the ends)");
    for (int i = 0; i <= 40; i++) {
        float f = i <= 20 ? i / 20.0f : (40 - i) / 20.0f;
        servo_set(CONFIG_SQZ_SERVO_REST_DEG + CONFIG_SQZ_SWELL_DEG * f, false, now_ms());
        vTaskDelay(pdMS_TO_TICKS(30));
    }
    for (int i = 0; i < 40; i++) {   /* hold rest, then the 5 V supply switches off */
        servo_set(CONFIG_SQZ_SERVO_REST_DEG, true, now_ms());
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    ESP_LOGI(T, "%s (%d failure%s). Next: the partner link, see docs/design.md section 9",
             fails ? "SELF-TEST FAILED" : "SELF-TEST PASSED", fails, fails == 1 ? "" : "s");
}

void app_main(void)
{
    power_init();
    bool sensor_ok = bmp280_init() == ESP_OK;
    if (!sensor_ok)
        ESP_LOGE(TAG, "pressure sensor missing: this unit can receive but not send");
    servo_init(CONFIG_SQZ_SERVO_REST_DEG);
    led_init();

    woke_t woke = WOKE_POWER_ON;
    if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER) {   /* only after a flat-battery deep sleep */
        if (battery_empty())
            empty_battery_sleep();
        woke = doze(sensor_ok);
    } else if (power_usb()) {
        selftest(sensor_ok);
    }
    radio_start();
    for (;;) {
        session(woke, sensor_ok);
        woke = doze(sensor_ok);
    }
}
