#include "sense_touch.h"

#include "board.h"
#include "esp_check.h"
#include "esp_sleep.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "touch";

esp_err_t sense_init(void)
{
    ESP_RETURN_ON_ERROR(touch_pad_init(), TAG, "init");
    for (int i = 0; i < N_SENSE_PADS; i++)
        ESP_RETURN_ON_ERROR(touch_pad_config(SENSE_CH[i]), TAG, "config ch %d", SENSE_CH[i]);
    ESP_RETURN_ON_ERROR(touch_pad_config(GUARD_CH), TAG, "guard");

    // idle electrodes float (high-Z): they then follow the shield instead of loading the
    // measured pad through a water film (see docs/placement-and-electrodes.md, section 3.4)
    ESP_RETURN_ON_ERROR(touch_pad_set_idle_channel_connect(TOUCH_PAD_CONN_HIGHZ), TAG, "idle");

    // driven shield on T14 (L1 side strips + hatched L2 plane). Drive level L2 = up to 120 pF;
    // measure the real shield load on the first boards and adjust.
    touch_pad_waterproof_t wp = {.guard_ring_pad = GUARD_CH, .shield_driver = TOUCH_PAD_SHIELD_DRV_L2};
    ESP_RETURN_ON_ERROR(touch_pad_waterproof_set_config(&wp), TAG, "waterproof");
    ESP_RETURN_ON_ERROR(touch_pad_waterproof_enable(), TAG, "waterproof en");

    touch_pad_denoise_t dn = {.grade = TOUCH_PAD_DENOISE_BIT4, .cap_level = TOUCH_PAD_DENOISE_CAP_L4};
    ESP_RETURN_ON_ERROR(touch_pad_denoise_set_config(&dn), TAG, "denoise");
    ESP_RETURN_ON_ERROR(touch_pad_denoise_enable(), TAG, "denoise en");

    ESP_RETURN_ON_ERROR(touch_pad_set_fsm_mode(TOUCH_FSM_MODE_TIMER), TAG, "fsm");
    ESP_RETURN_ON_ERROR(touch_pad_fsm_start(), TAG, "fsm start");
    vTaskDelay(pdMS_TO_TICKS(50));   // first measurements
    return ESP_OK;
}

esp_err_t sense_read(uint32_t raw[LVL_CH], int n)
{
    uint64_t acc[LVL_CH] = {0};
    for (int s = 0; s < n; s++) {
        for (int i = 0; i < N_SENSE_PADS; i++) {
            uint32_t v = 0;
            ESP_RETURN_ON_ERROR(touch_pad_read_raw_data(SENSE_CH[i], &v), TAG, "read %d", i);
            acc[i] += v;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    for (int i = 0; i < LVL_CH; i++) raw[i] = (uint32_t)(acc[i] / (n ? n : 1));
    return ESP_OK;
}

esp_err_t sense_arm_wake(uint32_t delta_counts)
{
    ESP_RETURN_ON_ERROR(touch_pad_sleep_channel_enable(WAKE_CH, true), TAG, "sleep ch");
    ESP_RETURN_ON_ERROR(touch_pad_sleep_set_threshold(WAKE_CH, delta_counts), TAG, "sleep thr");
    // sample PAD1 every ~200 ms in deep sleep: low current, fast enough for a filling bath
    ESP_RETURN_ON_ERROR(touch_pad_sleep_channel_set_work_time(3000, 500), TAG, "sleep work");
    return esp_sleep_enable_touchpad_wakeup();
}
