#include "tmp117.h"

#include "board.h"
#include "driver/i2c_master.h"
#include "esp_check.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "tmp117";

#define REG_TEMP 0x00
#define REG_CONFIG 0x01
// CONFIG: MOD = 11 (one-shot), CONV = 000, AVG = 01 (8 averages, ~125 ms)
#define CONFIG_ONESHOT_AVG8 ((3u << 10) | (1u << 5))

static void power(bool on)
{
    gpio_set_direction(PIN_SENSE_PWR, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_SENSE_PWR, on);
    if (!on) {   // leave the bus pins floating so the unpowered sensor is not back-fed
        gpio_reset_pin(PIN_SDA);
        gpio_reset_pin(PIN_SCL);
        gpio_set_direction(PIN_SDA, GPIO_MODE_DISABLE);
        gpio_set_direction(PIN_SCL, GPIO_MODE_DISABLE);
    }
}

esp_err_t tmp117_read(float *temp_c)
{
    power(true);
    vTaskDelay(pdMS_TO_TICKS(3));   // power-up time 1.5 ms

    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0, .sda_io_num = PIN_SDA, .scl_io_num = PIN_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = false,   // 10k pull-ups on the switched sensor rail
    };
    i2c_master_bus_handle_t bus = NULL;
    i2c_master_dev_handle_t dev = NULL;
    esp_err_t err = i2c_new_master_bus(&bus_cfg, &bus);
    if (err == ESP_OK) {
        i2c_device_config_t dev_cfg = {.dev_addr_length = I2C_ADDR_BIT_LEN_7, .device_address = TMP117_ADDR,
                                       .scl_speed_hz = 100000};
        err = i2c_master_bus_add_device(bus, &dev_cfg, &dev);
    }
    if (err == ESP_OK) {
        uint8_t cfg[3] = {REG_CONFIG, CONFIG_ONESHOT_AVG8 >> 8, CONFIG_ONESHOT_AVG8 & 0xff};
        err = i2c_master_transmit(dev, cfg, sizeof(cfg), 50);
    }
    if (err == ESP_OK) {
        vTaskDelay(pdMS_TO_TICKS(140));
        uint8_t reg = REG_TEMP, buf[2];
        err = i2c_master_transmit_receive(dev, &reg, 1, buf, 2, 50);
        if (err == ESP_OK) *temp_c = (int16_t)((buf[0] << 8) | buf[1]) * 0.0078125f;
    }
    if (dev) i2c_master_bus_rm_device(dev);
    if (bus) i2c_del_master_bus(bus);
    power(false);
    ESP_RETURN_ON_ERROR(err, TAG, "read failed");
    return ESP_OK;
}
