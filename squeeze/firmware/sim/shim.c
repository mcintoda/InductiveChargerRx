/* ESP-IDF stand-ins for one unit. Compiled together with the real firmware sources into one object per unit
 * (symbols then prefixed uA_ / uB_, see Makefile); hardware access goes to the simulated world. */
#include <math.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/ledc.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "world.h"

void app_main(void);

static const world_api_t *W;
static int U;
static int64_t boot_us;
static esp_sleep_wakeup_cause_t cause;
static jmp_buf reboot;
static uint64_t sleep_timer_us;
static int wifi_channel = 1;
static bool wifi_started;
static esp_now_recv_cb_t recv_cb;
static struct { uint32_t freq, bits; } timers[4];
static struct { int gpio, timer, invert, configured; uint32_t duty; } chans[6];

/* ---------------- logging, time, sleep ---------------- */
void sim_log(char level, const char *tag, const char *fmt, ...)
{
    char msg[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    W->log(U, level, tag, msg);
}

int64_t esp_timer_get_time(void) { return W->now_us() - boot_us; }   /* restarts at 0 on every boot */
TickType_t xTaskGetTickCount(void) { return (TickType_t)(esp_timer_get_time() / 1000); }
void vTaskDelay(TickType_t t) { W->wait_until(U, W->now_us() + (int64_t)t * 1000); }

void vTaskDelayUntil(TickType_t *prev, TickType_t inc)
{
    *prev += inc;
    int64_t t = boot_us + (int64_t)*prev * 1000;
    if (t > W->now_us())
        W->wait_until(U, t);
    else
        *prev = xTaskGetTickCount();   /* overran: FreeRTOS would not wait either */
}

esp_err_t esp_sleep_enable_timer_wakeup(uint64_t us) { sleep_timer_us = us; return ESP_OK; }
esp_sleep_wakeup_cause_t esp_sleep_get_wakeup_cause(void) { return cause; }

void esp_deep_sleep_start(void)
{
    wifi_started = false;
    W->radio_on(U, false, wifi_channel);
    W->deep_sleep(U, (int64_t)sleep_timer_us);
    longjmp(reboot, 1);
}

esp_err_t esp_light_sleep_start(void)
{
    W->light_sleep(U, true);
    W->wait_until(U, W->now_us() + (int64_t)sleep_timer_us);
    W->light_sleep(U, false);
    return ESP_OK;
}

void sim_unit_run(const world_api_t *w, int unit)
{
    W = w;
    U = unit;
    cause = ESP_SLEEP_WAKEUP_UNDEFINED;
    if (setjmp(reboot)) {
        W->wait_until(U, W->now_us() + (int64_t)sleep_timer_us);
        cause = ESP_SLEEP_WAKEUP_TIMER;
    }
    for (;;) {
        memset(timers, 0, sizeof timers);   /* peripherals reset on a (deep sleep) reboot */
        memset(chans, 0, sizeof chans);
        boot_us = W->now_us();
        W->wait_until(U, boot_us + 30000);   /* ROM + bootloader (skip-validate-in-deep-sleep): ~30 ms */
        boot_us = W->now_us() - 0;           /* esp_timer starts near 0 at app start */
        app_main();
        /* app_main never returns on the chip; if it did, idle */
        for (;;)
            W->wait_until(U, W->now_us() + 1000000);
    }
}

/* ---------------- FreeRTOS queue ---------------- */
typedef struct { uint32_t len, size, head, count; uint8_t *buf; } q_t;

QueueHandle_t xQueueCreate(uint32_t len, uint32_t size)
{
    q_t *q = calloc(1, sizeof *q);
    q->len = len; q->size = size; q->buf = calloc(len, size);
    return q;
}

BaseType_t xQueueSend(QueueHandle_t h, const void *item, TickType_t ticks)
{
    (void)ticks;
    q_t *q = h;
    if (q->count == q->len)
        return pdFALSE;
    memcpy(q->buf + ((q->head + q->count) % q->len) * q->size, item, q->size);
    q->count++;
    return pdTRUE;
}

static void pump_radio(void)
{
    uint8_t buf[256];
    int n;
    static uint8_t src[6] = { 2, 0, 0, 0, 0, 0 };
    while (wifi_started && recv_cb && (n = W->radio_take(U, buf, sizeof buf)) >= 0) {
        esp_now_recv_info_t info = { .src_addr = src, .des_addr = NULL, .rx_ctrl = NULL };
        recv_cb(&info, buf, n);   /* the Wi-Fi task's callback */
    }
}

BaseType_t xQueueReceive(QueueHandle_t h, void *item, TickType_t ticks)
{
    q_t *q = h;
    int64_t deadline = W->now_us() + (int64_t)ticks * 1000;
    for (;;) {
        pump_radio();
        if (q->count) {
            memcpy(item, q->buf + q->head * q->size, q->size);
            q->head = (q->head + 1) % q->len;
            q->count--;
            return pdTRUE;
        }
        if (W->now_us() >= deadline)
            return pdFALSE;
        W->wait_radio(U, deadline);
    }
}

/* ---------------- I2C ---------------- */
struct sim_i2c_bus { int x; };
struct sim_i2c_dev { uint16_t addr; };
static struct sim_i2c_bus the_bus;
static struct sim_i2c_dev the_dev;

esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t *c, i2c_master_bus_handle_t *r) { (void)c; *r = &the_bus; return ESP_OK; }
esp_err_t i2c_master_bus_add_device(i2c_master_bus_handle_t b, const i2c_device_config_t *c, i2c_master_dev_handle_t *r)
{
    (void)b;
    the_dev.addr = c->device_address;
    *r = &the_dev;
    return ESP_OK;
}

esp_err_t i2c_master_transmit(i2c_master_dev_handle_t d, const uint8_t *w, size_t n, int to)
{
    (void)to;
    if (!W->i2c_present(U, (uint8_t)d->addr))
        return ESP_FAIL;   /* NACK */
    if (n >= 2)
        W->i2c_write(U, w[0], w[1]);
    return ESP_OK;
}

esp_err_t i2c_master_transmit_receive(i2c_master_dev_handle_t d, const uint8_t *w, size_t wn, uint8_t *r, size_t rn, int to)
{
    (void)to; (void)wn;
    if (!W->i2c_present(U, (uint8_t)d->addr))
        return ESP_FAIL;
    W->i2c_read(U, w[0], r, rn);
    return ESP_OK;
}

/* ---------------- GPIO, LEDC, ADC ---------------- */
esp_err_t gpio_config(const gpio_config_t *c) { (void)c; return ESP_OK; }
esp_err_t gpio_set_level(int g, uint32_t l) { W->gpio_set(U, g, (int)l); return ESP_OK; }
int gpio_get_level(int g) { return W->gpio_get(U, g); }


esp_err_t ledc_timer_config(const ledc_timer_config_t *c)
{
    timers[c->timer_num].freq = c->freq_hz;
    timers[c->timer_num].bits = (uint32_t)c->duty_resolution;
    return ESP_OK;
}

esp_err_t ledc_channel_config(const ledc_channel_config_t *c)
{
    chans[c->channel].gpio = c->gpio_num; chans[c->channel].timer = c->timer_sel;
    chans[c->channel].invert = c->flags.output_invert; chans[c->channel].duty = c->duty;
    chans[c->channel].configured = 1;
    ledc_update_duty(LEDC_LOW_SPEED_MODE, c->channel);
    return ESP_OK;
}

esp_err_t ledc_set_duty(ledc_mode_t m, ledc_channel_t ch, uint32_t duty)
{
    (void)m;
    if (!chans[ch].configured)
        return ESP_ERR_INVALID_STATE;   /* as the IDF: "LEDC is not initialized" */
    chans[ch].duty = duty;
    return ESP_OK;
}

esp_err_t ledc_update_duty(ledc_mode_t m, ledc_channel_t ch)
{
    (void)m;
    if (!chans[ch].configured)
        return ESP_ERR_INVALID_STATE;
    double frac = chans[ch].duty / (double)(1u << timers[chans[ch].timer].bits);
    if (chans[ch].invert)
        frac = 1.0 - frac;
    W->pwm(U, chans[ch].gpio, frac, timers[chans[ch].timer].freq);
    return ESP_OK;
}

struct sim_adc { int x; };
struct sim_cali { int x; };
static struct sim_adc the_adc;
static struct sim_cali the_cali;
esp_err_t adc_oneshot_new_unit(const adc_oneshot_unit_init_cfg_t *c, adc_oneshot_unit_handle_t *r) { (void)c; *r = &the_adc; return ESP_OK; }
esp_err_t adc_oneshot_config_channel(adc_oneshot_unit_handle_t h, adc_channel_t ch, const adc_oneshot_chan_cfg_t *c) { (void)h; (void)ch; (void)c; return ESP_OK; }
esp_err_t adc_oneshot_read(adc_oneshot_unit_handle_t h, adc_channel_t ch, int *raw)
{
    (void)h;
    int mv = W->adc_mv(U, ch);
    *raw = mv > 2500 ? 4095 : mv * 4095 / 2500;   /* 12 dB attenuation: ~2.5 V full scale */
    return ESP_OK;
}
esp_err_t adc_cali_create_scheme_curve_fitting(const adc_cali_curve_fitting_config_t *c, adc_cali_handle_t *r) { (void)c; *r = &the_cali; return ESP_OK; }
esp_err_t adc_cali_raw_to_voltage(adc_cali_handle_t h, int raw, int *mv) { (void)h; *mv = raw * 2500 / 4095; return ESP_OK; }

/* ---------------- Wi-Fi / ESP-NOW ---------------- */
esp_err_t nvs_flash_init(void) { return ESP_OK; }
esp_err_t nvs_flash_erase(void) { return ESP_OK; }
esp_err_t esp_netif_init(void) { return ESP_OK; }
esp_err_t esp_event_loop_create_default(void) { return ESP_OK; }
esp_err_t esp_read_mac(uint8_t *mac, esp_mac_type_t t) { (void)t; uint8_t m[6] = { 0x24, 0x58, 0x7c, 0, 0, (uint8_t)U }; memcpy(mac, m, 6); return ESP_OK; }
esp_err_t esp_wifi_init(const wifi_init_config_t *c) { (void)c; return ESP_OK; }
esp_err_t esp_wifi_set_storage(wifi_storage_t s) { (void)s; return ESP_OK; }
esp_err_t esp_wifi_set_mode(wifi_mode_t m) { (void)m; return ESP_OK; }
esp_err_t esp_wifi_set_protocol(wifi_interface_t i, uint8_t b) { (void)i; (void)b; return ESP_OK; }
esp_err_t esp_wifi_start(void)
{
    W->wait_until(U, W->now_us() + 35000);   /* RF init with stored calibration: ~35 ms */
    wifi_started = true;
    W->radio_on(U, true, wifi_channel);
    return ESP_OK;
}
esp_err_t esp_wifi_stop(void)
{
    wifi_started = false;
    W->radio_on(U, false, wifi_channel);
    return ESP_OK;
}
esp_err_t esp_wifi_set_channel(uint8_t p, wifi_second_chan_t s) { (void)s; wifi_channel = p; W->radio_on(U, wifi_started, p); return ESP_OK; }
esp_err_t esp_wifi_set_ps(wifi_ps_type_t t) { (void)t; return ESP_OK; }
esp_err_t esp_now_init(void) { return wifi_started ? ESP_OK : ESP_ERR_INVALID_STATE; }
esp_err_t esp_now_deinit(void) { return ESP_OK; }
esp_err_t esp_now_register_recv_cb(esp_now_recv_cb_t cb) { recv_cb = cb; return ESP_OK; }
esp_err_t esp_now_add_peer(const esp_now_peer_info_t *p) { (void)p; return ESP_OK; }
esp_err_t esp_now_send(const uint8_t *a, const uint8_t *d, size_t n)
{
    (void)a;
    if (!wifi_started)
        return ESP_ERR_INVALID_STATE;
    W->radio_send(U, d, (int)n);
    return ESP_OK;
}
