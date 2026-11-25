#include "hw.h"

#include <math.h>

#include "board.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

static const char *TAG = "hw";

/* ---------------- servo: LEDC timer 0, 50 Hz, 14 bit ---------------- */
#define SERVO_CH   LEDC_CHANNEL_0
#define SERVO_BITS 14
#define SERVO_OFF_DELAY_MS 500

static bool s_servo_init;
static bool s_servo_on;
static uint32_t s_rest_since;
static float s_rest_deg;

static uint32_t deg_to_duty(float deg)
{
    if (deg < 0) deg = 0;
    if (deg > 180) deg = 180;
#if CONFIG_SQZ_SERVO_REVERSE
    deg = 180 - deg;
#endif
    float us = CONFIG_SQZ_SERVO_MIN_US + (CONFIG_SQZ_SERVO_MAX_US - CONFIG_SQZ_SERVO_MIN_US) * deg / 180.0f;
    return (uint32_t)lroundf(us * (float)(1u << SERVO_BITS) / 20000.0f);
}

static void servo_duty(uint32_t duty)
{
    ledc_set_duty(LEDC_LOW_SPEED_MODE, SERVO_CH, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, SERVO_CH);
}

void servo_init(float rest_deg)
{
    s_rest_deg = rest_deg;
    gpio_config_t en = { .pin_bit_mask = 1ULL << PIN_SERVO_EN, .mode = GPIO_MODE_OUTPUT };
    gpio_config(&en);
    gpio_set_level(PIN_SERVO_EN, 0);
    ledc_timer_config_t t = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = SERVO_BITS,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 50,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&t);
    ledc_channel_config_t ch = {
        .gpio_num = PIN_SERVO_PWM,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = SERVO_CH,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0, /* no pulses = the servo does nothing */
    };
    ledc_channel_config(&ch);
    s_servo_init = true;
}

void servo_set(float deg, bool at_rest, uint32_t now_ms)
{
    if (!at_rest) {
        if (!s_servo_on) {
            /* Pulses at rest first, then power: an SG90 jumps to whatever it is
             * told the moment it gets power. */
            servo_duty(deg_to_duty(s_rest_deg));
            gpio_set_level(PIN_SERVO_EN, 1);
            s_servo_on = true;
        }
        servo_duty(deg_to_duty(deg));
        s_rest_since = now_ms;
        return;
    }
    if (s_servo_on) {
        servo_duty(deg_to_duty(deg));
        if ((uint32_t)(now_ms - s_rest_since) > SERVO_OFF_DELAY_MS)
            servo_off();
    }
}

void servo_off(void)
{
    if (!s_servo_init)
        return; /* quick wake: never powered; SERVO_EN is held low by its pull-down */
    gpio_set_level(PIN_SERVO_EN, 0);
    servo_duty(0);
    s_servo_on = false;
}

/* ---------------- LED: LEDC timer 1, 5 kHz, 10 bit, common cathode ---------------- */
static const int LED_PINS[3] = { PIN_LED_R, PIN_LED_G, PIN_LED_B };

void led_init(void)
{
    ledc_timer_config_t t = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = LEDC_TIMER_1,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&t);
    for (int i = 0; i < 3; i++) {
        ledc_channel_config_t ch = {
            .gpio_num = LED_PINS[i],
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .channel = LEDC_CHANNEL_1 + i,
            .timer_sel = LEDC_TIMER_1,
            .duty = 0,
        };
        ledc_channel_config(&ch);
    }
}

void led_rgb(uint32_t rgb, float brightness)
{
    if (brightness < 0) brightness = 0;
    if (brightness > 1) brightness = 1;
    for (int i = 0; i < 3; i++) {
        float v = ((rgb >> (16 - 8 * i)) & 0xFF) / 255.0f * brightness;
        uint32_t duty = (uint32_t)lroundf(v * v * 1023.0f); /* rough perceptual curve */
        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1 + i, duty);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1 + i);
    }
}

/* ---------------- power ---------------- */
static adc_oneshot_unit_handle_t s_adc;
static adc_cali_handle_t s_cali;

void power_init(void)
{
    gpio_config_t chg = { .pin_bit_mask = 1ULL << PIN_CHG_N, .mode = GPIO_MODE_INPUT,
                          .pull_up_en = GPIO_PULLUP_ENABLE };
    gpio_config(&chg);

    adc_oneshot_unit_init_cfg_t u = { .unit_id = ADC_UNIT_1 };
    if (adc_oneshot_new_unit(&u, &s_adc) != ESP_OK)
        return;
    adc_oneshot_chan_cfg_t ch = { .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT };
    adc_oneshot_config_channel(s_adc, ADC_CHANNEL_3, &ch); /* GPIO3 */
    adc_cali_curve_fitting_config_t cc = { .unit_id = ADC_UNIT_1, .chan = ADC_CHANNEL_3,
                                           .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT };
    if (adc_cali_create_scheme_curve_fitting(&cc, &s_cali) != ESP_OK) {
        ESP_LOGW(TAG, "no ADC calibration; battery voltage is approximate");
        s_cali = NULL;
    }
}

int power_vbat_mv(void)
{
    if (!s_adc)
        return 0;
    int sum = 0;
    for (int i = 0; i < 8; i++) {
        int raw = 0, mv = 0;
        adc_oneshot_read(s_adc, ADC_CHANNEL_3, &raw);
        if (s_cali)
            adc_cali_raw_to_voltage(s_cali, raw, &mv);
        else
            mv = raw * 2500 / 4095;
        sum += mv;
    }
    int vbat = sum / 8 * 2; /* 1M/1M divider */
    return vbat < 2000 ? 0 : vbat;
}

bool power_charging(void) { return gpio_get_level(PIN_CHG_N) == 0; }
