// brim bath monitor - main state machine.
//
//   SETUP    no Wi-Fi stored: access point "brim-setup-XXXX", form at http://192.168.4.1
//   CHARGER  on a Qi pad: settings + OTA page for 10 min, dry-baseline recalibration;
//            3 placements within 20 s = factory reset
//   BATH     deep sleep until PAD1 gets wet (touch wake); then track the fill every 2 s,
//            notify via ntfy, sleep again once the level is steady or the bath is drained
//
// On the device itself (rev C): RGB status LED, piezo sounder for local alarms (works without Wi-Fi),
// double-tap on the case = acknowledge the alarm, LIS2DW12 wakes on motion (tap / pick up -> battery colour)
// and flags a tilted / fallen device during a bath.
//
// Level sensing (settings page, docs/sensing-options.md):
//   fdc      FDC1004 on PAD1 / PAD5 / PAD6 / REF (alarm region 40..60 mm only) (default)
//   touch    ESP32-S3 touch, ratiometric live reference (automatic fallback when no FDC1004 answers)
//   compare  both run; every sample is logged as a CMP line on the USB console; alarms from touch
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <sys/time.h>

#include "accel.h"
#include "board.h"
#include "buzzer.h"
#include "driver/usb_serial_jtag.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
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
#include "status.h"
#include "tilt.h"
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
static RTC_DATA_ATTR bool s_acc_probed, s_acc_fitted;
static RTC_DATA_ATTR tilt_t s_tilt;
static bool s_rail_held;                       // sensor rail kept on while awake (FDC fitted)

static settings_t s_set;

static double now_s(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);   // RTC timer keeps running through deep sleep
    return tv.tv_sec + tv.tv_usec / 1e6;
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
    status_quiet(true);                               // and the LED current must not move the shared rail
    esp_err_t err = fdc_read_all(&s_fdc_st, pf);
    status_quiet(false);
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

// ---------------- check-in: brim says it's alive, the ntfy server says when it isn't ----------------
#define CHECKIN_S (48 * 3600.0)      // re-arm the watchdog every 2 days...
#define WATCHDOG_DELAY "70h"         // ...which fires after ~3 days of silence (ntfy.sh's limit is 3 days)
#define STATUS_S (7 * 24 * 3600.0)   // and a silent "brim OK" once a week
#define RETRY_S (6 * 3600.0)
static RTC_DATA_ATTR double s_next_checkin, s_next_status;
static RTC_DATA_ATTR bool s_empty_sent;
#define BATT_EMPTY_MV 3450           // RT9080 needs ~3.5 V for 3.3 V at Wi-Fi peaks; the cell's PCM cuts at ~2.5-3 V

static void checkin(bool online)
{
    double now = now_s();
    if (!online && !net_wifi_connect(&s_set, 15000)) {
        s_next_checkin = now + RETRY_S;
        net_wifi_stop();
        return;
    }
    int code = net_watchdog(&s_set, WATCHDOG_DELAY);
    // 2xx: armed. 4xx: this server can't schedule (old or self-hosted ntfy): don't keep retrying every 6 h
    s_next_checkin = now + ((code >= 200 && code < 300) || (code >= 400 && code < 500) ? CHECKIN_S : RETRY_S);
    int mv0 = power_battery_mv(), pct0 = mv0 > 0 ? power_battery_pct(mv0) : -1;
    if (!power_on_charger() && pct0 >= 0 && pct0 < POLICY_LOW_BATT_PCT && !s_policy.lowbat_sent) {
        char m[96];
        snprintf(m, sizeof(m), "Battery at %d %%. Put brim on a Qi charger soon.", pct0);
        if (net_ntfy(&s_set, "brim battery low", m, 3, "battery") == ESP_OK) s_policy.lowbat_sent = true;
    }
    if (now >= s_next_status) {
        int mv = power_battery_mv();
        char m[160];
        if (power_on_charger()) snprintf(m, sizeof(m), "On the charger. brim checks in every 2 days, and you'll get an "
                                         "alert if it goes quiet for 3.");
        else snprintf(m, sizeof(m), "Battery %d %%. brim checks in every 2 days, and you'll get an alert if it goes "
                      "quiet for 3.", mv > 0 ? power_battery_pct(mv) : 0);
        if (net_ntfy(&s_set, "brim OK", m, 1, "white_check_mark") == ESP_OK) s_next_status = now + STATUS_S;
    }
    if (!online) net_wifi_stop();
}

static void sleep_now(bool pad1_wet, uint64_t timer_s)
{
    // deep sleep turns the USB port off: stay awake while a computer is attached so esptool can
    // reset the chip into the bootloader by itself (no IO0 / EN buttons needed)
    if (usb_serial_jtag_is_connected()) {
        ESP_LOGI(TAG, "USB host attached: staying awake");
        while (usb_serial_jtag_is_connected()) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    net_wifi_stop();
    status_led(LED_OFF);
    hold_rail(false);
    if (!pad1_wet) sense_arm_wake(wake_pad(), lvl_wake_threshold(&s_cal, wake_pad()));   // wake when the bath arrives
    // ext1, any low: put on a Qi pad (QI_DET_N) or moved / tapped (LIS2DW12 INT1, active low)
    uint64_t ext1 = 0;
    if (!power_on_charger()) ext1 |= 1ULL << PIN_QI_DET_N;
    if (s_acc_fitted && accel_arm_wake() == ESP_OK) ext1 |= 1ULL << PIN_ACC_INT;
    if (ext1) esp_sleep_enable_ext1_wakeup(ext1, ESP_EXT1_WAKEUP_ANY_LOW);
    if (s_next_checkin > 0) {                        // never sleep through a check-in
        double dt = s_next_checkin - now_s();
        uint64_t c = dt < 60 ? 60 : (uint64_t)dt;
        if (!timer_s || c < timer_s) timer_s = c;
    }
    if (timer_s) esp_sleep_enable_timer_wakeup(timer_s * 1000000ULL);
    ESP_LOGI(TAG, "deep sleep (pad1 %s, timer %llus)", pad1_wet ? "wet" : "dry", timer_s);
    esp_deep_sleep_start();
}

static bool send(const policy_out_t *o)
{
    if (!net_wifi_connect(&s_set, 10000)) { ESP_LOGW(TAG, "no Wi-Fi: '%s' not sent", o->title); return false; }
    bool ok = false;
    for (int i = 0; i < 3 && !ok; i++) {
        ok = net_ntfy(&s_set, o->title, o->msg, o->priority, o->tags) == ESP_OK;
        if (!ok) vTaskDelay(pdMS_TO_TICKS(2000));
    }
    net_wifi_stop();          // the radio is the biggest load: off between alerts (reconnecting takes ~2 s)
    return ok;
}

// phone notification plus the local signal on the device: the sounder covers "bath full" even when the
// phone is in another room or the Wi-Fi is down
static void notify(const policy_out_t *o)
{
    bool urgent = o->ev == EV_ALARM || o->ev == EV_SUBMERGED;
    if (urgent && !s_policy.acked) { status_led(LED_ALARM); buzzer_alarm(); }
    bool sent = send(o);
    if (!sent && (o->ev == EV_NEARLY_FULL || o->ev == EV_TOO_HOT)) buzzer_alarm();
}

static void notify_text(const char *title, const char *msg, int prio, const char *tags)
{
    policy_out_t o = {.ev = EV_NONE, .priority = prio};
    snprintf(o.title, sizeof(o.title), "%s", title);
    snprintf(o.msg, sizeof(o.msg), "%s", msg);
    snprintf(o.tags, sizeof(o.tags), "%s", tags);
    if (settings_provisioned(&s_set)) send(&o);
}


// ---------------- charger ----------------
static bool factory_reset_gesture(void)
{
    s_placed_at[0] = s_placed_at[1];
    s_placed_at[1] = s_placed_at[2];
    s_placed_at[2] = now_s();
    return s_placed_at[0] > 0 && s_placed_at[2] - s_placed_at[0] < 20.0;
}

// 3 placements in 20 s can also be a pad that keeps dropping the connection: with the accelerometer fitted, ask
// for a double-tap within 10 s (fast red flashing) before erasing anything
static bool confirm_reset(void)
{
    if (!s_acc_fitted) return true;
    accel_awake();
    accel_events();
    for (int i = 0; i < 25; i++) {                        // ~10 s
        status_flash(255, 0, 0, 1, 200);
        if (accel_events() & ACC_EV_DOUBLE_TAP) return true;
    }
    ESP_LOGI(TAG, "factory reset not confirmed");
    memset(s_placed_at, 0, sizeof(s_placed_at));
    return false;
}

static void charger_mode(bool placed)
{
    if (placed && factory_reset_gesture() && confirm_reset()) {
        ESP_LOGW(TAG, "factory reset");
        // cancel the pending "hasn't checked in" alert so the old topic doesn't get it in 3 days
        if (s_set.topic[0] && net_wifi_connect(&s_set, 8000)) net_watchdog(&s_set, NULL);
        net_wifi_stop();
        s_next_checkin = s_next_status = 0;
        status_flash(255, 0, 0, 10, 80);
        settings_erase();
        memset(s_placed_at, 0, sizeof(s_placed_at));
        esp_restart();
    }
    calibrate_dry(0.5f);

    net_status_t st = {.battery_pct = -1, .temp_c = NAN};
    bool online = net_wifi_connect(&s_set, 15000);
    if (online) {
        net_web_start(&s_set, &st);
        char url[40], msg[96];
        snprintf(url, sizeof(url), "http://%s/", net_ip());
        snprintf(msg, sizeof(msg), "Tap for settings (open for 10 min): %s", url);
        if (placed) net_ntfy_click(&s_set, "brim is charging", msg, 1, "battery", url);   // priority 1: silent
        checkin(true);
    }
    // changes need physical presence: a double-tap on the device (no accelerometer: the first 2 min on the pad)
    if (s_acc_fitted) { accel_awake(); accel_events(); }
    else net_unlock(120);
    double t0 = now_s();
    while (now_s() - t0 < 10 * 60 && power_on_charger()) {
        if (s_acc_fitted && (accel_events() & ACC_EV_DOUBLE_TAP)) {
            net_unlock(120);
            status_flash(0, 255, 0, 2, 150);
        }
        int mv = power_battery_mv();
        st.battery_pct = mv > 0 ? power_battery_pct(mv) : -1;
        st.charging = power_charging();
        status_led(st.charging ? LED_CHARGING : LED_CHARGED);
        if (net_ota_done()) { vTaskDelay(pdMS_TO_TICKS(1500)); esp_restart(); }
        if (net_web_saved()) { vTaskDelay(pdMS_TO_TICKS(1500)); esp_restart(); }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    net_web_stop();
    net_wifi_stop();
    // stay with it while it charges (the pad powers it): keep the charging light on and notice the lift-off.
    // Light sleep between checks; Wi-Fi only for a due check-in
    esp_pm_config_t pm = {.max_freq_mhz = 80, .min_freq_mhz = 40, .light_sleep_enable = true};
    esp_pm_configure(&pm);
    while (power_on_charger()) {
        status_led(power_charging() ? LED_CHARGING : LED_CHARGED);
        if (now_s() >= s_next_checkin) checkin(false);
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
    sleep_now(false, 0);
}

// ---------------- bath ----------------
static void bath_mode(void)
{
    if (!s_policy_ready) {
        policy_init(&s_policy, lvl_pad_top_mm(s_set.alarm_pad), s_set.temp_limit_c, s_set.notify_filling);
        s_policy_ready = true;
    }
    s_policy.alarm_mm = lvl_pad_top_mm(s_set.alarm_pad);
    s_policy.temp_limit_c = s_set.temp_limit_c;          // settings may have changed on the charger
    policy_set_cool(&s_policy, s_set.temp_cool_c);

    int mode = s_set.sense_mode;
    if (mode != SENSE_TOUCH && !(s_fdc_fitted && s_fdc.valid)) {
        ESP_LOGW(TAG, "FDC1004 not fitted: using touch sensing");
        mode = SENSE_TOUCH;
    }
    int alarm_pad = s_set.alarm_pad;
    if (mode == SENSE_FDC && alarm_pad < 5) {            // the FDC only sees PAD5 / PAD6 (the settings page offers only those)
        ESP_LOGW(TAG, "FDC mode: alarm pad %d not covered, using pad 5", alarm_pad);
        alarm_pad = 5;
        s_policy.alarm_mm = lvl_pad_top_mm(alarm_pad);
    }
    if (!s_policy.active) {                           // a new bath
        fdc_bath_start(&s_fdc);                       // forget the last reference-liquid value
        s_tilt.ref_valid = false;                     // learn "upright" again from this mounting
    }
    hold_rail(true);
    if (s_acc_fitted) accel_awake();

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

        policy_in_t in = {.now_s = t, .wet = r.wet, .all_wet = r.all_wet, .level_mm = r.level_mm,
                          .ref_frac = r.raw_frac[LVL_REF], .at_alarm = r.top_full >= alarm_pad,
                          .temp_c = temp, .battery_pct = batt};
        in.rate_ok = rate_mm_per_min(&rate, &in.rate_mm_min);
        in.eta_s = rate_eta_s(&rate, r.level_mm, s_policy.alarm_mm - 1.0f);
        policy_out_t out;
        if (policy_step(&s_policy, &in, &out)) notify(&out);
        // the device itself: double tap = "I know", tilt / fall check, LED
        if (s_acc_fitted) {
            uint8_t ev = accel_events();
            if ((ev & ACC_EV_DOUBLE_TAP) && s_policy.active) {
                policy_ack(&s_policy);
                status_flash(0, 255, 0, 2, 150);
                buzzer_chirp();
                ESP_LOGI(TAG, "alarm acknowledged on the device");
            }
            float g[3];
            if (r.wet && accel_gravity(g) == ESP_OK && tilt_update(&s_tilt, g, t))
                notify_text("brim is tilted", "brim is no longer upright - it may have slipped out of its bracket. "
                            "Level readings are unreliable until it is back in place.", 4, "warning,bathtub");
        }
        led_state_t led = LED_MONITOR;
        if (s_policy.alarm_active) led = s_policy.acked ? LED_OK : LED_ALARM;
        else if (!isnan(temp) && temp > s_policy.temp_limit_c) led = LED_HOT;
        else if (tilt_is_tilted(&s_tilt)) led = LED_ATTENTION;
        else if (s_policy.nearly_sent) led = LED_NEARLY;
        status_led(led);
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
            // at or near the line (someone may top up): check every minute
            bool near = s_policy.alarm_active || s_policy.nearly_sent || r.level_mm >= s_policy.alarm_mm - 15.0f;
            if (t - t_steady > 180)
                sleep_now(true, near ? 60 : (mode == SENSE_FDC && !fdc_window) ? 2 * 60 : 5 * 60);
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
    // rollback is enabled: an image that got this far (settings, power, radio, sensors up) is good, keep it
    esp_ota_mark_app_valid_cancel_rollback();
    ESP_LOGI(TAG, "wake cause %d, on charger %d, provisioned %d", cause, power_on_charger(), settings_provisioned(&s_set));

    if (!s_fdc_probed) {                                  // which board variant is this?
        s_fdc_fitted = fdc_present();
        s_fdc_probed = true;
        ESP_LOGI(TAG, "FDC1004 %s, wake pad %d", s_fdc_fitted ? "fitted" : "not fitted", wake_pad());
    }
    if (!s_acc_probed) {
        s_acc_fitted = accel_present();
        s_acc_probed = true;
        ESP_LOGI(TAG, "LIS2DW12 %s", s_acc_fitted ? "fitted" : "not answering");
    }
    if (!s_cal.valid) calibrate_dry(1);                   // first power-up: assume dry
    net_set_fdc_fitted(s_fdc_fitted);
    // first boot after setup (or new Wi-Fi details): prove they work before relying on them
    if (s_set.ssid[0] && s_set.topic[0] && !s_set.wifi_ok) {
        status_led(LED_SETUP);
        if (net_wifi_connect(&s_set, 20000)) {
            s_set.wifi_ok = true;
            settings_save(&s_set);
            net_ntfy(&s_set, "brim is connected",
                     "Alerts will arrive here. Put brim in its bracket with the arrows at your full line.", 3, "bathtub");
            s_next_status = now_s() + STATUS_S;          // the first "brim OK" comes a week from now
            checkin(true);
            net_wifi_stop();
            status_flash(0, 255, 0, 2, 300);
        } else {
            net_wifi_stop();
            ESP_LOGW(TAG, "can't join '%s': back to setup", s_set.ssid);
        }
    }
    if (!settings_provisioned(&s_set) || !s_set.wifi_ok) {
        status_led(LED_SETUP);
        if (net_provision(&s_set, 15 * 60 * 1000)) esp_restart();
        sleep_now(false, 0);
    }
    // moved or tapped while asleep: show the battery, then straight back to sleep unless a bath is running
    if (cause == ESP_SLEEP_WAKEUP_EXT1 && s_acc_fitted && (esp_sleep_get_ext1_wakeup_status() & (1ULL << PIN_ACC_INT))) {
        accel_events();
        int mv = power_battery_mv();
        status_battery(mv > 0 ? power_battery_pct(mv) : 0);
        if (!power_on_charger() && !s_policy.active) sleep_now(false, 6 * 3600);
    }
    // empty: say so once, then sleep until it is put on a charger (protects the cell, no brown-out loops)
    if (!power_on_charger()) {
        int mv = power_battery_mv();
        if (mv > 0 && mv < BATT_EMPTY_MV) {
            if (!s_empty_sent) {
                notify_text("brim battery empty", "brim has stopped watching baths. Put it on a Qi charger.", 4,
                            "battery,warning");
                s_empty_sent = true;
            }
            esp_sleep_enable_ext1_wakeup(1ULL << PIN_QI_DET_N, ESP_EXT1_WAKEUP_ANY_LOW);
            ESP_LOGW(TAG, "battery empty (%d mV): sleeping until charged", mv);
            esp_deep_sleep_start();
        }
    } else s_empty_sent = false;
    // due, or never armed since power-up (RTC memory was cleared): check in now
    if (!power_on_charger() && !s_policy.active && (s_next_checkin == 0 || now_s() >= s_next_checkin)) checkin(false);
    // a real placement (woken by the pad, or powered up / restarted on it), not a timer wake while it sat there
    if (power_on_charger()) charger_mode(cause != ESP_SLEEP_WAKEUP_TIMER);
    bath_mode();
}
