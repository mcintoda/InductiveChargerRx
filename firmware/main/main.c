// brim bath monitor - main state machine.
//
//   SETUP    no Wi-Fi stored: access point "brim-setup-XXXX", form at http://192.168.4.1
//   CHARGER  on a Qi pad: settings + OTA page for 10 min, dry-baseline recalibration;
//            3 placements within 20 s = factory reset
//   BATH     deep sleep until PAD1 gets wet (touch wake); then track the fill every 2 s,
//            notify via ntfy, sleep again once the level is steady or the bath is drained
#include <math.h>
#include <string.h>
#include <sys/time.h>

#include "board.h"
#include "esp_log.h"
#include "esp_pm.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "level.h"
#include "net.h"
#include "nvs_flash.h"
#include "policy.h"
#include "power.h"
#include "rate.h"
#include "sense_touch.h"
#include "settings.h"
#include "tmp117.h"

static const char *TAG = "brim";

// survives deep sleep
static RTC_DATA_ATTR lvl_cal_t s_cal;
static RTC_DATA_ATTR policy_t s_policy;
static RTC_DATA_ATTR bool s_policy_ready;
static RTC_DATA_ATTR double s_placed_at[3];   // last three charger placements (for factory reset)

static settings_t s_set;

static double now_s(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);   // RTC timer keeps running through deep sleep
    return tv.tv_sec + tv.tv_usec / 1e6;
}

static void blink(int n, int ms)
{
    for (int i = 0; i < n; i++) {
        power_led(true); vTaskDelay(pdMS_TO_TICKS(ms));
        power_led(false); vTaskDelay(pdMS_TO_TICKS(ms));
    }
}

static void sleep_now(bool pad1_wet, uint64_t timer_s)
{
    net_wifi_stop();
    power_led(false);
    if (!pad1_wet) sense_arm_wake(lvl_wake_threshold(&s_cal));       // wake when the bath reaches PAD1
    if (!power_on_charger()) esp_sleep_enable_ext1_wakeup(1ULL << PIN_QI_DET_N, ESP_EXT1_WAKEUP_ANY_LOW);
    if (timer_s) esp_sleep_enable_timer_wakeup(timer_s * 1000000ULL);
    ESP_LOGI(TAG, "deep sleep (pad1 %s, timer %llus)", pad1_wet ? "wet" : "dry", timer_s);
    esp_deep_sleep_start();
}

static void notify(const policy_out_t *o)
{
    if (!net_wifi_connect(&s_set, 10000)) { ESP_LOGW(TAG, "no Wi-Fi: '%s' not sent", o->title); return; }
    for (int i = 0; i < 3 && net_ntfy(&s_set, o->title, o->msg, o->priority, o->tags) != ESP_OK; i++)
        vTaskDelay(pdMS_TO_TICKS(2000));
}

// ---------------- charger ----------------
static bool factory_reset_gesture(void)
{
    s_placed_at[0] = s_placed_at[1];
    s_placed_at[1] = s_placed_at[2];
    s_placed_at[2] = now_s();
    return s_placed_at[0] > 0 && s_placed_at[2] - s_placed_at[0] < 20.0;
}

static void charger_mode(void)
{
    if (factory_reset_gesture()) {
        ESP_LOGW(TAG, "factory reset");
        blink(10, 80);
        settings_erase();
        memset(s_placed_at, 0, sizeof(s_placed_at));
        esp_restart();
    }
    // out of the water: refresh the dry baseline
    uint32_t raw[LVL_CH];
    sense_read(raw, 8);
    if (!s_cal.valid) lvl_cal_init(&s_cal, raw);
    else lvl_track_dry(&s_cal, raw, 0.5f);

    net_status_t st = {.battery_pct = -1, .temp_c = NAN};
    bool online = net_wifi_connect(&s_set, 15000);
    if (online) net_web_start(&s_set, &st);
    double t0 = now_s();
    while (now_s() - t0 < 10 * 60 && power_on_charger()) {
        int mv = power_battery_mv();
        st.battery_pct = mv > 0 ? power_battery_pct(mv) : -1;
        st.charging = power_charging();
        power_led(st.charging);                       // LED on while charging
        if (net_ota_done()) { vTaskDelay(pdMS_TO_TICKS(1500)); esp_restart(); }
        if (net_web_saved()) { vTaskDelay(pdMS_TO_TICKS(1500)); esp_restart(); }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    net_web_stop();
    // still on the pad: check again in 10 min (no ext1 wake while QI_DET_N is low)
    sleep_now(false, power_on_charger() ? 10 * 60 : 0);
}

// ---------------- bath ----------------
static void bath_mode(void)
{
    if (!s_policy_ready) {
        policy_init(&s_policy, lvl_pad_top_mm(s_set.alarm_pad), s_set.temp_limit_c, s_set.notify_filling);
        s_policy_ready = true;
    }
    s_policy.alarm_mm = lvl_pad_top_mm(s_set.alarm_pad);

    rate_t rate;
    rate_init(&rate, 60);
    uint32_t raw[LVL_CH];
    float temp = NAN;
    int batt = -1;
    double t_start = now_s(), t_temp = 0, t_batt = 0, t_dry = 0, t_steady = 0;
    esp_pm_config_t pm = {.max_freq_mhz = 80, .min_freq_mhz = 40, .light_sleep_enable = true};
    esp_pm_configure(&pm);

    for (;;) {
        double t = now_s();
        if (power_on_charger()) esp_restart();            // taken out and put on the charger
        sense_read(raw, 4);
        lvl_result_t r = lvl_compute(&s_cal, raw);
        if (r.wet && (t - t_temp > 10 || isnan(temp))) {  // the TMP117 tab is underwater before PAD1
            float c;
            if (tmp117_read(&c) == ESP_OK) temp = c;
            t_temp = t;
        }
        if (t - t_batt > 60 || batt < 0) {
            int mv = power_battery_mv();
            batt = mv > 0 ? power_battery_pct(mv) : -1;
            t_batt = t;
        }
        if (r.wet) rate_add(&rate, (float)(t - t_start), r.level_mm);

        policy_in_t in = {.now_s = (float)(t - 1.7e9), .wet = r.wet, .all_wet = r.all_wet, .level_mm = r.level_mm,
                          .ref_frac = r.raw_frac[LVL_REF], .at_alarm = r.top_full >= s_set.alarm_pad,
                          .temp_c = temp, .battery_pct = batt};
        in.rate_ok = rate_mm_per_min(&rate, &in.rate_mm_min);
        in.eta_s = rate_eta_s(&rate, r.level_mm, s_policy.alarm_mm - 1.0f);
        policy_out_t out;
        if (policy_step(&s_policy, &in, &out)) notify(&out);
        ESP_LOGI(TAG, "level %.1f mm (top pad %d) rate %.2f mm/min temp %.2f C batt %d %%", r.level_mm, r.top_full,
                 in.rate_ok ? in.rate_mm_min : NAN, temp, batt);

        if (!r.wet) {
            if (t_dry == 0) t_dry = t;
            if (t - t_dry > 60) {                         // drained or a splash: back to sleep
                lvl_track_dry(&s_cal, raw, 0.1f);
                sleep_now(false, s_policy.active ? 15 * 60 : 6 * 3600);
            }
        } else t_dry = 0;

        bool steady = in.rate_ok && fabsf(in.rate_mm_min) < POLICY_RISING_MM_MIN && !s_policy.alarm_active;
        bool alarm_quiet = s_policy.alarm_active && !(in.rate_ok && in.rate_mm_min > POLICY_RISING_MM_MIN) &&
                           !s_policy.ref_rising;
        if (steady || alarm_quiet) {
            if (t_steady == 0) t_steady = t;
            if (t - t_steady > 180) sleep_now(true, 5 * 60);   // someone is in the bath: check every 5 min
        } else t_steady = 0;

        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    settings_load(&s_set);
    power_init();
    net_init();
    sense_init();
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    ESP_LOGI(TAG, "wake cause %d, on charger %d, provisioned %d", cause, power_on_charger(), settings_provisioned(&s_set));

    if (!s_cal.valid) {                                   // first power-up: assume dry
        uint32_t raw[LVL_CH];
        sense_read(raw, 8);
        lvl_cal_init(&s_cal, raw);
    }
    if (!settings_provisioned(&s_set)) {
        blink(3, 300);
        if (net_provision(&s_set, 15 * 60 * 1000)) esp_restart();
        sleep_now(false, 0);
    }
    if (power_on_charger()) charger_mode();
    bath_mode();
}
