/* squeeze: two hand-held units that pass squeezes back and forth.
 *
 * Asleep (most of the time): deep sleep, waking every SLEEP_PERIOD_MS for ~60 ms
 * to check (1) is my holder squeezing? and (2) is my partner calling (WAKE)?
 *
 * Awake (a session): 50 Hz loop. Squeeze -> level -> radio. Partner's level ->
 * plates. Turn-taking (turn.c) decides which way squeezes flow. 90 s with no
 * squeeze on either side -> BYE -> sleep.
 *
 * See docs/design.md §7 for the full behaviour and the LED legend.
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
#define LISTEN_MS        45     /* asleep: how long to listen for WAKE on each check */
#define WAKE_PA          300.0f /* asleep: rise that counts as "squeezed me awake" */
#define CALL_MS          (CONFIG_SQZ_SLEEP_PERIOD_MS + 1500)
#define PARTNER_LOST_MS  3000   /* no heartbeat for this long = partner asleep / out of range */
#define REMOTE_STALE_MS  250    /* no LEVEL frame for this long = partner let go (link loss safety) */
#define HELLO_MS         400    /* woken by the partner: one gentle swell */
#define HELLO_LEVEL      0.4f
#define INVITE_MS        60000  /* ...then glow the partner's colour for up to a minute */
#define VBAT_LOW_MV      3500   /* red blink, LOW_BATT flag */
#define VBAT_NO_SERVO_MV 3400   /* plates off, LED only */
#define VBAT_EMPTY_MV    3300   /* sleep 60 s at a time, no radio, until charged */

#if CONFIG_SQZ_ROLE_PARENT
#define COLOR_SELF    CONFIG_SQZ_COLOR_PARENT
#define COLOR_PARTNER CONFIG_SQZ_COLOR_CHILD
#else
#define COLOR_SELF    CONFIG_SQZ_COLOR_CHILD
#define COLOR_PARTNER CONFIG_SQZ_COLOR_PARENT
#endif
#define COLOR_CHARGING 0xFF7000
#define COLOR_LOW      0xFF0000

RTC_DATA_ATTR static float rtc_base_pa;
RTC_DATA_ATTR static bool rtc_have_base;

static uint32_t now_ms(void) { return (uint32_t)(esp_timer_get_time() / 1000); }

static void sleep_now(uint32_t period_ms)
{
    servo_off();
    bmp280_sleep();
    esp_sleep_enable_timer_wakeup((uint64_t)period_ms * 1000ULL);
    esp_deep_sleep_start();
}

/* Asleep and the timer fired: decide whether to wake up. Returns only if awake. */
typedef enum { WOKE_POWER_ON, WOKE_BY_SQUEEZE, WOKE_BY_PARTNER } woke_t;

static woke_t quick_check(bool sensor_ok)
{
    int vbat = power_vbat_mv();
    if (vbat < VBAT_EMPTY_MV && !power_charging() && !power_usb())
        sleep_now(60000);

    float pa;
    if (sensor_ok && bmp280_one_shot(&pa) == ESP_OK) {
        if (rtc_have_base && pa - rtc_base_pa > WAKE_PA) {
            radio_start();
            return WOKE_BY_SQUEEZE;
        }
        /* Follow the slow drift (time constant ~30 s at a 2 s period). */
        rtc_base_pa = rtc_have_base ? rtc_base_pa + (pa - rtc_base_pa) * 0.07f : pa;
        rtc_have_base = true;
    }

    radio_start();
    uint32_t until = now_ms() + LISTEN_MS;
    sq_msg_t m;
    for (int32_t left; (left = (int32_t)(until - now_ms())) > 0;)
        if (radio_recv(&m, left) && m.type == SQ_WAKE)
            return WOKE_BY_PARTNER;
    sleep_now(CONFIG_SQZ_SLEEP_PERIOD_MS);
    return WOKE_POWER_ON; /* not reached */
}

static float breathe(uint32_t t, uint32_t period_ms)
{
    float ph = (float)(t % period_ms) / (float)period_ms;
    return 0.5f - 0.5f * cosf(2.0f * (float)M_PI * ph);
}

void app_main(void)
{
    power_init();
    bool sensor_ok = bmp280_init() == ESP_OK;
    if (!sensor_ok)
        ESP_LOGE(TAG, "pressure sensor missing: this unit can receive but not send");

    woke_t woke = WOKE_POWER_ON;
    if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER)
        woke = quick_check(sensor_ok); /* starts the radio when it returns */
    else
        radio_start();

    servo_init(CONFIG_SQZ_SERVO_REST_DEG);
    led_init();
    if (sensor_ok)
        bmp280_start_stream();

    grip_cfg_t gc = grip_default_cfg();
    grip_t grip;
    grip_init(&grip, &gc);
    if (woke == WOKE_BY_SQUEEZE && rtc_have_base) {
        /* The holder is squeezing right now: start from the resting pressure
         * measured while asleep, not from this squeezed one. */
        grip.init = true;
        grip.baseline = rtc_base_pa;
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

    uint32_t t0 = now_ms();
    uint32_t last_activity = t0, last_hb = 0, last_vbat = 0, partner_seen = 0, remote_ms = 0;
    uint32_t call_start = t0, hello_until = 0, invite_until = 0, trace = 0;
    bool partner_awake = false, calling = woke != WOKE_BY_PARTNER, mask = false;
    uint8_t remote_level = 0;
    int vbat = power_vbat_mv();
    bool on_usb = power_usb(); /* USB-C plugged in: never sleep */
    float pa = rtc_base_pa;

    if (woke == WOKE_BY_PARTNER) {
        radio_send(SQ_AWAKE, 0, 0);
        partner_awake = true;
        partner_seen = t0;
        hello_until = t0 + HELLO_MS;
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
            switch (m.type) {
            case SQ_LEVEL:
                remote_level = m.level;
                remote_ms = now;
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
        bool remote_active = remote_level > 0 && now - remote_ms < REMOTE_STALE_MS;

        /* --- turn-taking --- */
        turn_out_t o = turn_update(&turn, grip.active, remote_active, shaper_busy(&shaper), now);
        if (o.send)
            radio_send(SQ_LEVEL, (uint8_t)lroundf(level * 255.0f), flags);
        if (grip.active && !partner_awake && !calling) {
            calling = true; /* partner asleep: wake it */
            call_start = now;
        }
        if (calling) {
            radio_send(SQ_WAKE, 0, flags);
            if (now - call_start > CALL_MS)
                calling = false;
        }
        if (now - last_hb >= 1000) {
            last_hb = now;
            radio_send(SQ_HEARTBEAT, 0, flags);
        }

        /* --- plates --- */
        float target = (o.play && remote_active) ? remote_level / 255.0f : 0.0f; /* stale = let go */
        bool hello = (int32_t)(hello_until - now) > 0;
        if (hello)
            target = fmaxf(target, HELLO_LEVEL);
        if (vbat < VBAT_NO_SERVO_MV)
            target = 0.0f;
        float angle = shaper_update(&shaper, target, DT);
        servo_set(angle, !shaper_busy(&shaper), now);
        /* Our own plates moving raise our own pressure: not the holder squeezing. */
        mask = o.mask || hello || shaper_busy(&shaper);

        /* --- LED (legend: docs/design.md §7) --- */
        if (o.play && remote_active)
            led_rgb(COLOR_PARTNER, 0.15f + 0.85f * remote_level / 255.0f);
        else if (o.send && grip.active)
            led_rgb(COLOR_SELF, 0.10f + 0.60f * level);
        else if (calling)
            led_rgb(COLOR_SELF, 0.4f * breathe(now, 500));
        else if ((int32_t)(invite_until - now) > 0)
            led_rgb(COLOR_PARTNER, 0.6f * breathe(now, 2500));
        else if (low && (now % 2000) < 120)
            led_rgb(COLOR_LOW, 0.5f);
        else if (charging)
            led_rgb(COLOR_CHARGING, 0.05f);
        else if (partner_awake)
            led_rgb(COLOR_PARTNER, 0.04f);
        else
            led_rgb(0, 0);

#if CONFIG_SQZ_TRACE
        if (now - trace >= 200) {
            trace = now;
            ESP_LOGI(TAG, "p=%.0f base=%.0f range=%.0f lvl=%.2f | turn=%d remote=%u ang=%.0f | %s vbat=%d",
                     pa, grip.baseline, grip.range, level, turn.st, remote_level, angle,
                     partner_awake ? "partner" : "alone", vbat);
        }
#else
        (void)trace;
#endif

        /* --- sleep --- */
        bool idle = now - last_activity > CONFIG_SQZ_SESSION_IDLE_S * 1000u;
        if (!on_usb && idle && turn.st == TURN_IDLE && !shaper_busy(&shaper)) {
            ESP_LOGI(TAG, "idle: sleeping");
            for (int i = 0; i < 3; i++) {
                radio_send(SQ_BYE, 0, flags);
                vTaskDelay(pdMS_TO_TICKS(5));
            }
            led_rgb(0, 0);
            if (grip.init) {
                rtc_base_pa = grip.baseline;
                rtc_have_base = true;
            }
            sleep_now(CONFIG_SQZ_SLEEP_PERIOD_MS);
        }

        vTaskDelayUntil(&wake_tick, pdMS_TO_TICKS(TICK_MS));
    }
}
