/* BMP280 driver (register map: Bosch BST-BMP280-DS001 section 4). The squeeze sensor.
 * Normal mode: x4 pressure, x1 temperature, no IIR, 0.5 ms standby -> a new sample every ~14 ms;
 * main.c reads it at 50 Hz. Bring-up check: ~101 kPa at sea level. */
#include "bmp280.h"

#include <stdbool.h>

#include "bmp280_comp.h"
#include "board.h"
#include "driver/i2c_master.h"
#include "esp_check.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define REG_CALIB     0x88 /* 24 bytes */
#define REG_ID        0xD0 /* 0x58 */
#define REG_RESET     0xE0
#define REG_STATUS    0xF3
#define REG_CTRL_MEAS 0xF4
#define REG_CONFIG    0xF5
#define REG_DATA      0xF7 /* press msb lsb xlsb, temp msb lsb xlsb */

#define OSRS        ((1 << 5) | (3 << 2)) /* temp x1, pressure x4 */
#define MODE_SLEEP  0
#define MODE_FORCED 1
#define MODE_NORMAL 3
#define STATUS_MEASURING 0x08

static const char *TAG = "bmp280";
static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_dev;
static bmp280_calib_t s_cal;

static esp_err_t wr(uint8_t reg, uint8_t val)
{
    uint8_t b[2] = { reg, val };
    return i2c_master_transmit(s_dev, b, 2, 20);
}

static esp_err_t rd(uint8_t reg, uint8_t *buf, size_t n)
{
    return i2c_master_transmit_receive(s_dev, &reg, 1, buf, n, 20);
}

static esp_err_t read_pa(float *pa)
{
    uint8_t b[6];
    ESP_RETURN_ON_ERROR(rd(REG_DATA, b, sizeof b), TAG, "data");
    int32_t up = (int32_t)((uint32_t)b[0] << 12 | (uint32_t)b[1] << 4 | b[2] >> 4);
    int32_t ut = (int32_t)((uint32_t)b[3] << 12 | (uint32_t)b[4] << 4 | b[5] >> 4);
    *pa = (float)bmp280_compensate(&s_cal, up, ut, NULL);
    return ESP_OK;
}

esp_err_t bmp280_init(void)
{
    if (!s_bus) {
        i2c_master_bus_config_t bus = {
            .i2c_port = I2C_NUM_0,
            .sda_io_num = PIN_SDA,
            .scl_io_num = PIN_SCL,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .flags.enable_internal_pullup = false, /* 4.7k on the board */
        };
        ESP_RETURN_ON_ERROR(i2c_new_master_bus(&bus, &s_bus), TAG, "bus");
        i2c_device_config_t dev = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = BMP280_ADDR,
            .scl_speed_hz = 400000,
        };
        ESP_RETURN_ON_ERROR(i2c_master_bus_add_device(s_bus, &dev, &s_dev), TAG, "dev");
    }
    uint8_t id = 0;
    ESP_RETURN_ON_ERROR(rd(REG_ID, &id, 1), TAG, "no BMP280 at 0x%02x", BMP280_ADDR);
    if (id != 0x58) {
        ESP_LOGE(TAG, "unexpected chip id 0x%02x", id);
        return ESP_ERR_NOT_FOUND;
    }
    ESP_RETURN_ON_ERROR(wr(REG_RESET, 0xB6), TAG, "reset");
    vTaskDelay(pdMS_TO_TICKS(3));
    uint8_t cal[24];
    ESP_RETURN_ON_ERROR(rd(REG_CALIB, cal, sizeof cal), TAG, "calib");
    bmp280_parse_calib(cal, &s_cal);
    return wr(REG_CONFIG, 0x00); /* t_sb 0.5 ms, filter off (only writable in sleep mode) */
}

esp_err_t bmp280_start_stream(void)
{
    ESP_RETURN_ON_ERROR(wr(REG_CTRL_MEAS, OSRS | MODE_NORMAL), TAG, "normal");
    vTaskDelay(pdMS_TO_TICKS(20));
    return ESP_OK;
}

esp_err_t bmp280_read(float *pa) { return read_pa(pa); }

esp_err_t bmp280_one_shot(float *pa)
{
    ESP_RETURN_ON_ERROR(wr(REG_CTRL_MEAS, OSRS | MODE_FORCED), TAG, "forced");
    for (int i = 0; i < 10; i++) {
        vTaskDelay(pdMS_TO_TICKS(i == 0 ? 14 : 2));
        uint8_t st = 0;
        ESP_RETURN_ON_ERROR(rd(REG_STATUS, &st, 1), TAG, "status");
        if (!(st & STATUS_MEASURING))
            return read_pa(pa);
    }
    return ESP_ERR_TIMEOUT;
}

/* Doze sampling (10 Hz while asleep): x1 pressure, x1 temperature, forced: ~5.5 ms, ~3 uA average.
 * The caller light-sleeps through the conversion, then reads with bmp280_read(). */
esp_err_t bmp280_start_fast(void) { return wr(REG_CTRL_MEAS, (1 << 5) | (1 << 2) | MODE_FORCED); }

esp_err_t bmp280_sleep(void) { return wr(REG_CTRL_MEAS, OSRS | MODE_SLEEP); }
