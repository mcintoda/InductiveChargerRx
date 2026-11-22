#include "buzzer.h"

#include "board.h"
#include "driver/ledc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define BUZ_HZ 4000                       // near a bonded 20 mm disc's resonance; tune on the bench

static void start(int hz)
{
    ledc_timer_config_t t = {.speed_mode = LEDC_LOW_SPEED_MODE, .duty_resolution = LEDC_TIMER_8_BIT,
                             .timer_num = LEDC_TIMER_1, .freq_hz = hz, .clk_cfg = LEDC_AUTO_CLK};
    ledc_timer_config(&t);
    ledc_channel_config_t a = {.gpio_num = PIN_BUZ_A, .speed_mode = LEDC_LOW_SPEED_MODE, .channel = LEDC_CHANNEL_0,
                               .timer_sel = LEDC_TIMER_1, .duty = 128, .hpoint = 0};
    ledc_channel_config(&a);
    ledc_channel_config_t b = a;
    b.gpio_num = PIN_BUZ_B; b.channel = LEDC_CHANNEL_1; b.flags.output_invert = 1;   // antiphase: 2 x the swing
    ledc_channel_config(&b);
}

static void stop(void)
{
    ledc_stop(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 0);
    ledc_stop(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1, 0);
    gpio_set_direction(PIN_BUZ_A, GPIO_MODE_OUTPUT); gpio_set_level(PIN_BUZ_A, 0);
    gpio_set_direction(PIN_BUZ_B, GPIO_MODE_OUTPUT); gpio_set_level(PIN_BUZ_B, 0);   // no DC across the disc
}

void buzzer_tone(int hz, int ms)
{
    start(hz);
    vTaskDelay(pdMS_TO_TICKS(ms));
    stop();
}

void buzzer_alarm(void)
{
    for (int burst = 0; burst < 3; burst++) {
        for (int i = 0; i < 3; i++) { buzzer_tone(BUZ_HZ, 120); vTaskDelay(pdMS_TO_TICKS(80)); }
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

void buzzer_chirp(void) { buzzer_tone(BUZ_HZ, 60); }
