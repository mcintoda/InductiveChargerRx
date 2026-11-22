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

esp_err_t sensor_xfer(uint8_t addr, const uint8_t *tx, size_t ntx, uint8_t *rx, size_t nrx)
{
    i2c_master_bus_handle_t bus;
    esp_err_t err = sensor_bus_acquire(&bus);
    if (err != ESP_OK) return err;
    i2c_master_dev_handle_t dev = NULL;
    i2c_device_config_t cfg = {.dev_addr_length = I2C_ADDR_BIT_LEN_7, .device_address = addr, .scl_speed_hz = 100000};
    err = i2c_master_bus_add_device(bus, &cfg, &dev);
    if (err == ESP_OK) {
        if (rx && ntx) err = i2c_master_transmit_receive(dev, tx, ntx, rx, nrx, 50);
        else if (rx) err = i2c_master_receive(dev, rx, nrx, 50);
        else err = i2c_master_transmit(dev, tx, ntx, 50);
    }
    if (dev) i2c_master_bus_rm_device(dev);
    sensor_bus_release();
    return err;
}

esp_err_t sensor_reg_write(uint8_t addr, uint8_t reg, uint8_t val)
{
    uint8_t b[2] = {reg, val};
    return sensor_xfer(addr, b, 2, NULL, 0);
}

esp_err_t sensor_reg_read(uint8_t addr, uint8_t reg, uint8_t *buf, size_t n)
{
    return sensor_xfer(addr, &reg, 1, buf, n);
}
