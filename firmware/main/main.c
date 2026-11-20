// brim bath monitor - main state machine.
//
//   SETUP    no Wi-Fi stored: access point "brim-setup-XXXX", form at http://192.168.4.1
//   CHARGER  on a Qi pad: settings + OTA page for 10 min, dry-baseline recalibration;
//            3 placements within 20 s = factory reset
//   BATH     deep sleep until PAD1 gets wet (touch wake); then track the fill every 2 s,
//            notify via ntfy, sleep again once the level is steady or the bath is drained
//
// Level sensing (settings page, docs/sensing-options.md):
//   fdc      FDC1004 on PAD1 / PAD5 / PAD6 / REF (alarm region 40..60 mm only) (default)
//   touch    ESP32-S3 touch, ratiometric live reference (automatic fallback when no FDC1004 answers)
//   compare  both run; every sample is logged as a CMP line on the USB console; alarms from touch
#include <math.h>
#include <string.h>
#include <sys/time.h>

#include "board.h"
#include "esp_log.h"
#include "fdc1004.h"
#include "fdclevel.h"
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
#include "sensor_bus.h"
#include "sense_touch.h"
#include "settings.h"
#include "tmp117.h"

static const char *TAG = "brim";

// survives deep sleep
static RTC_DATA_ATTR lvl_cal_t s_cal;
static RTC_DATA_ATTR policy_t s_policy;
static RTC_DATA_ATTR bool s_policy_ready;
static RTC_DATA_ATTR double s_placed_at[3];   // last three charger placements (for factory reset)
static RTC_DATA_ATTR fdc_cal_t s_fdc;
static RTC_DATA_ATTR fdc_state_t s_fdc_st;      // CAPDAC per channel
static RTC_DATA_ATTR bool s_fdc_probed, s_fdc_fitted;
static bool s_rail_held;                       // sensor rail kept on while awake (FDC fitted)

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

// PAD1 cannot wake the chip when the FDC1004 links are fitted: with the rail off its ESD diodes clamp the pad
static int wake_pad(void) { return s_fdc_fitted ? 2 : 1; }

// with the FDC1004 fitted the sensor rail must stay on while the touch peripheral measures (see wake_pad)
static void hold_rail(bool on)
{
    i2c_master_bus_handle_t bus;
    if (on && !s_rail_held && s_fdc_fitted) s_rail_held = sensor_bus_acquire(&bus) == ESP_OK;
    else if (!on && s_rail_held) { sensor_bus_release(); s_rail_held = false; }
}

static bool fdc_sample(float pf[FDC_CH])
{
    sense_pause();                                    // the touch FSM must not drive the pads meanwhile
    esp_err_t err = fdc_read_all(&s_fdc_st, pf);
    sense_resume();
    if (err != ESP_OK) ESP_LOGW(TAG, "FDC1004 read failed: %s", esp_err_to_name(err));
    return err == ESP_OK;
}

// out of the water: refresh the dry baselines (alpha 1 = replace)
static void calibrate_dry(float alpha)
{
    hold_rail(true);
    uint32_t raw[LVL_CH];
    sense_read(raw, 8);
    if (!s_cal.valid || alpha >= 1) lvl_cal_init(&s_cal, raw);
    else lvl_track_dry(&s_cal, raw, alpha);
    float pf[FDC_CH];
    if (s_fdc_fitted && fdc_sample(pf)) {
        if (!s_fdc.valid || alpha >= 1) fdc_cal_init(&s_fdc, pf);
        else for (int i = 0; i < FDC_CH; i++) s_fdc.base[i] += alpha * (pf[i] - s_fdc.base[i]);
    }
}

static void sleep_now(bool pad1_wet, uint64_t timer_s)
{
    net_wifi_stop();
    power_led(false);
    hold_rail(false);
    if (!pad1_wet) sense_arm_wake(wake_pad(), lvl_wake_threshold(&s_cal, wake_pad()));   // wake when the bath arrives
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
    calibrate_dry(0.5f);

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

    int mode = s_set.sense_mode;
    if (mode != SENSE_TOUCH && !(s_fdc_fitted && s_fdc.valid)) {
        ESP_LOGW(TAG, "FDC1004 not fitted: using touch sensing");
        mode = SENSE_TOUCH;
    }
    int alarm_pad = s_set.alarm_pad;
    if (mode == SENSE_FDC && alarm_pad < 5) {            // the FDC only sees PAD5 / PAD6 in the alarm region
        ESP_LOGW(TAG, "FDC mode: alarm pad %d not covered, using pad 5", alarm_pad);
        alarm_pad = 5;
        s_policy.alarm_mm = lvl_pad_top_mm(alarm_pad);
    }
    if (!s_policy.active) fdc_bath_start(&s_fdc);        // a new bath: forget the last reference-liquid value
    hold_rail(true);

    rate_t rate;
    rate_init(&rate, 60);
    uint32_t raw[LVL_CH];
    float temp = NAN;
    int batt = -1;
    bool fdc_window = false;
    double t_start = now_s(), t_temp = 0, t_batt = 0, t_dry = 0, t_steady = 0;
    esp_pm_config_t pm = {.max_freq_mhz = 80, .min_freq_mhz = 40, .light_sleep_enable = true};
    esp_pm_configure(&pm);

    for (;;) {
        double t = now_s();
        if (power_on_charger()) esp_restart();            // taken out and put on the charger
        sense_read(raw, 4);
        lvl_cal_t other = s_cal;                          // the other touch method, without learning (compare only)
        lvl_result_t r = lvl_compute(&s_cal, raw);
        float pf[FDC_CH] = {0};
        fdc_result_t fr = {0};
        bool fdc_ok = mode != SENSE_TOUCH && fdc_sample(pf);
        if (fdc_ok) fr = fdc_level(&s_fdc, pf);
        if (mode == SENSE_COMPARE) {
            other.ratiometric = !s_cal.ratiometric;
            lvl_result_t o = lvl_compute(&other, raw);
            float learned = s_cal.ratiometric ? o.level_mm : r.level_mm, ratio = s_cal.ratiometric ? r.level_mm : o.level_mm;
            // CMP,t,learned_mm,ratio_mm,fdc_mm(-1 = below window),top_touch,top_fdc,drift,raw1..raw7,pf1..pf4
            ESP_LOGI("CMP", "%.1f,%.1f,%.1f,%.1f,%d,%d,%.4f,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%.3f,%.3f,%.3f,%.3f", t - t_start,
                     learned, ratio, fdc_ok && fr.in_window ? fr.level_mm : -1.0f, r.top_full, fr.top_full, r.drift,
                     (unsigned long)raw[0], (unsigned long)raw[1], (unsigned long)raw[2], (unsigned long)raw[3],
                     (unsigned long)raw[4], (unsigned long)raw[5], (unsigned long)raw[6], pf[0], pf[1], pf[2], pf[3]);
        }
        if (mode == SENSE_FDC) {                          // drive the policy from the FDC
            if (!fdc_ok) { vTaskDelay(pdMS_TO_TICKS(2000)); continue; }
            fdc_window = fr.in_window;
            r.wet = fr.pad1_wet;
            // below the alarm window the FDC only knows that PAD1 is covered
            r.level_mm = fr.in_window ? fr.level_mm : (fr.pad1_wet ? LVL_PAD_H_MM : 0);
            r.top_full = fr.top_full;
            r.raw_frac[LVL_REF] = fr.ref_frac;
            r.all_wet = fr.ref_wet && fr.top_full == 6;
        }
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
                          .ref_frac = r.raw_frac[LVL_REF], .at_alarm = r.top_full >= alarm_pad,
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
                calibrate_dry(0.1f);
                sleep_now(false, s_policy.active ? 15 * 60 : 6 * 3600);
            }
        } else t_dry = 0;

        bool steady = in.rate_ok && fabsf(in.rate_mm_min) < POLICY_RISING_MM_MIN && !s_policy.alarm_active;
        bool alarm_quiet = s_policy.alarm_active && !(in.rate_ok && in.rate_mm_min > POLICY_RISING_MM_MIN) &&
                           !s_policy.ref_rising;
        if (steady || alarm_quiet) {
            if (t_steady == 0) t_steady = t;
            // someone is in the bath: check every 5 min. In FDC mode below 40 mm the level is not seen
            // moving, so check every 2 min (20 mm at a fast 10 mm/min fill: still short of the alarm)
            if (t - t_steady > 180) sleep_now(true, (mode == SENSE_FDC && !fdc_window) ? 2 * 60 : 5 * 60);
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

    if (!s_fdc_probed) {                                  // which board variant is this?
        s_fdc_fitted = fdc_present();
        s_fdc_probed = true;
        ESP_LOGI(TAG, "FDC1004 %s, wake pad %d", s_fdc_fitted ? "fitted" : "not fitted", wake_pad());
    }
    if (!s_cal.valid) calibrate_dry(1);                   // first power-up: assume dry
    if (!settings_provisioned(&s_set)) {
        blink(3, 300);
        if (net_provision(&s_set, 15 * 60 * 1000)) esp_restart();
        sleep_now(false, 0);
    }
    if (power_on_charger()) charger_mode();
    bath_mode();
}
