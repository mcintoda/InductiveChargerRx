#include "sensor_bus.h"

#include "board.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static i2c_master_bus_handle_t s_bus;
static int s_refs;

esp_err_t sensor_bus_acquire(i2c_master_bus_handle_t *bus)
{
    if (s_refs++ == 0) {
        gpio_set_direction(PIN_SENSE_PWR, GPIO_MODE_OUTPUT);
        gpio_set_level(PIN_SENSE_PWR, 1);
        vTaskDelay(pdMS_TO_TICKS(3));                     // TMP117 1.5 ms, FDC1004 power-up
        i2c_master_bus_config_t cfg = {
            .i2c_port = I2C_NUM_0, .sda_io_num = PIN_SDA, .scl_io_num = PIN_SCL,
            .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7,
            .flags.enable_internal_pullup = false,        // 10k pull-ups on the switched rail
        };
        esp_err_t err = i2c_new_master_bus(&cfg, &s_bus);
        if (err != ESP_OK) { s_refs = 0; gpio_set_level(PIN_SENSE_PWR, 0); return err; }
    }
    *bus = s_bus;
    return ESP_OK;
}

void sensor_bus_release(void)
{
    if (s_refs == 0 || --s_refs > 0) return;
    i2c_del_master_bus(s_bus);
    s_bus = NULL;
    gpio_set_level(PIN_SENSE_PWR, 0);
    // float the bus pins so the unpowered sensors are not back-fed
    gpio_reset_pin(PIN_SDA);
    gpio_reset_pin(PIN_SCL);
    gpio_set_direction(PIN_SDA, GPIO_MODE_DISABLE);
    gpio_set_direction(PIN_SCL, GPIO_MODE_DISABLE);
    gpio_pullup_dis(PIN_SDA);
    gpio_pullup_dis(PIN_SCL);
}
