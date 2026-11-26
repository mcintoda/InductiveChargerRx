/* squeeze: two hand-held units that pass squeezes back and forth.
 *
 * Doze (most of the time): light sleep. Every 100 ms a fast pressure sample (is my holder squeezing?);
 * every SLEEP_PERIOD_MS the radio listens for 45 ms (is my partner calling?). A squeeze of 0.1 s or
 * longer wakes it. (A flat battery is the only reason for deep sleep.)
 *
 * Session: 50 Hz loop. Squeeze -> level -> radio. Partner's level -> plates. Turn-taking (turn.c)
 * decides which way squeezes flow. Squeezes made while the partner is still waking up are kept and
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
#define LISTEN_MS        45     /* asleep: how long to listen for WAKE each SLEEP_PERIOD_MS */
#define WAKE_PA          150.0f /* asleep: rise that counts as "squeezed me awake" (= grip on_pa: a 6-year-old's gentle squeeze) */
#define CALL_MS          (CONFIG_SQZ_SLEEP_PERIOD_MS + 1500)
#define PARTNER_LOST_MS  3000   /* no heartbeat for this long = partner asleep / out of range */
#define REMOTE_STALE_MS  250    /* no LEVEL frame for this long = partner let go (link loss safety) */
#define INVITE_MS        60000  /* woken by the partner: glow its colour for up to a minute */
#define UNREACHED_MS     1200   /* a call nobody answered: blink own colour */
#define CATCHUP_FRAMES   4      /* replay: frames sent per tick while catching up */
#define KEEP_GAP_TICKS   30     /* replay: pauses longer than 0.6 s are shortened to 0.6 s */
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
    uint32_t next_listen = now_ms() + CONFIG_SQZ_SLEEP_PERIOD_MS, next_vbat = now_ms();
    for (;;) {
        light_sleep_ms(DOZE_SAMPLE_MS - DOZE_CONV_MS);
        if (sensor_ok && bmp280_start_fast() == ESP_OK) {
            light_sleep_ms(DOZE_CONV_MS);
            float pa;
            if (bmp280_read(&pa) == ESP_OK) {
                if (have_rest && pa - rest_pa > WAKE_PA)
                    return WOKE_BY_SQUEEZE;
                /* follow drift (~2 s time constant), but not a rise in progress: a slow squeeze must not
                 * drag the reference up with it */
                if (!have_rest)
                    rest_pa = pa;
                else if (pa - rest_pa < WAKE_PA / 3)
                    rest_pa += (pa - rest_pa) * 0.05f;
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
            next_listen = now + CONFIG_SQZ_SLEEP_PERIOD_MS;
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
typedef struct { uint8_t v[256]; uint8_t head; uint16_t n; } fifo_t;
static void fifo_push(fifo_t *f, uint8_t x)
{
    if (f->n == 256) { f->head++; f->n--; }   /* full: drop the oldest */
    f->v[(uint8_t)(f->head + f->n)] = x;
    f->n++;
}
static uint8_t fifo_pop(fifo_t *f) { uint8_t x = f->v[f->head++]; f->n--; return x; }
static uint8_t fifo_peek(const fifo_t *f, int i) { return f->v[(uint8_t)(f->head + i)]; }

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
        .on_level = 0.03f,
        .cam_a_mm = 8, /* hardware/mech/squeeze_unit.py CAM_A / CAM_B */
        .cam_b_mm = 5,
    };
    shaper_t shaper;
    shaper_init(&shaper, &sc);
    turn_t turn;
    turn_init(&turn, 150);
    static fifo_t outq, playq;
    outq.n = playq.n = 0;

    uint32_t t0 = now_ms();
    uint32_t last_activity = t0, last_hb = 0, last_vbat = 0, partner_seen = 0, last_frame = 0;
    uint32_t call_start = t0, invite_until = 0, unreached_until = 0, trace = 0;
    bool partner_awake = false, partner_low = false, calling = woke != WOKE_BY_PARTNER, mask = false;
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
        float level = sensor_ok ? grip_update(&grip, pa, DT, mask) : 0.0f;
        if (grip.active) {
            last_activity = now;
            invite_until = 0;
        }

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
        if (playq.n)
            remote_level = fifo_pop(&playq);
        else if (now - last_frame > REMOTE_STALE_MS)
            remote_level = 0;
        bool remote_active = remote_level > 0 && (playq.n > 0 || now - last_frame < REMOTE_STALE_MS);

        /* --- turn-taking --- */
        turn_out_t o = turn_update(&turn, grip.active, remote_active, shaper_busy(&shaper), now);
        if (o.send)
            fifo_push(&outq, (uint8_t)lroundf(level * 255.0f));
        if (partner_awake)   /* live, or catching up on what was squeezed while the partner woke */
            for (int k = 0; k < CATCHUP_FRAMES && outq.n; k++)
                radio_send(SQ_LEVEL, fifo_pop(&outq), flags);
        if (grip.active && !partner_awake && !calling) {
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
        /* Our own plates moving raise our own pressure: not the holder squeezing. */
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
