/* BMP390 driver. Register map and compensation from the Bosch BMP390 datasheet
 * (BST-BMP390-DS002), section 8.4/8.5 floating-point formulas.
 * Bring-up check: bmp390_one_shot() reads ~101 kPa at sea level (docs/design.md §9). */
#include "bmp390.h"

#include "board.h"
#include "driver/i2c_master.h"
#include "esp_check.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define REG_CHIP_ID  0x00
#define REG_ERR      0x02
#define REG_STATUS   0x03
#define REG_DATA     0x04 /* press xlsb..msb, temp xlsb..msb */
#define REG_PWR_CTRL 0x1B
#define REG_OSR      0x1C
#define REG_ODR      0x1D
#define REG_CONFIG   0x1F
#define REG_CALIB    0x31 /* 21 bytes */
#define REG_CMD      0x7E

#define PWR_PRESS_TEMP 0x03
#define MODE_FORCED    0x10
#define MODE_NORMAL    0x30
#define STATUS_DRDY_P  0x20

static const char *TAG = "bmp390";
static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_dev;

static struct {
    double t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11;
} c;

static esp_err_t wr(uint8_t reg, uint8_t val)
{
    uint8_t b[2] = { reg, val };
    return i2c_master_transmit(s_dev, b, 2, 20);
}

static esp_err_t rd(uint8_t reg, uint8_t *buf, size_t n)
{
    return i2c_master_transmit_receive(s_dev, &reg, 1, buf, n, 20);
}

static double pow2(int e) { return e >= 0 ? (double)(1ULL << e) : 1.0 / (double)(1ULL << -e); }

static esp_err_t load_calibration(void)
{
    uint8_t b[21];
    ESP_RETURN_ON_ERROR(rd(REG_CALIB, b, sizeof b), TAG, "calib");
#define U16(i) ((uint16_t)(b[i] | b[(i) + 1] << 8))
#define S16(i) ((int16_t)U16(i))
#define S8(i)  ((int8_t)b[i])
    c.t1 = U16(0) / pow2(-8);
    c.t2 = U16(2) / pow2(30);
    c.t3 = S8(4) / pow2(48);
    c.p1 = (S16(5) - 16384) / pow2(20);
    c.p2 = (S16(7) - 16384) / pow2(29);
    c.p3 = S8(9) / pow2(32);
    c.p4 = S8(10) / pow2(37);
    c.p5 = U16(11) / pow2(-3);
    c.p6 = U16(13) / pow2(6);
    c.p7 = S8(15) / pow2(8);
    c.p8 = S8(16) / pow2(15);
    c.p9 = S16(17) / pow2(48);
    c.p10 = S8(19) / pow2(48);
    c.p11 = S8(20) / (pow2(32) * pow2(33)); /* 2^65 */
#undef U16
#undef S16
#undef S8
    return ESP_OK;
}

static float compensate(uint32_t up, uint32_t ut)
{
    double pd1 = (double)ut - c.t1;
    double t = pd1 * c.t2 + pd1 * pd1 * c.t3;

    double o1 = c.p5 + c.p6 * t + c.p7 * t * t + c.p8 * t * t * t;
    double o2 = (double)up * (c.p1 + c.p2 * t + c.p3 * t * t + c.p4 * t * t * t);
    double u2 = (double)up * (double)up;
    double o3 = u2 * (c.p9 + c.p10 * t) + u2 * (double)up * c.p11;
    return (float)(o1 + o2 + o3);
}

static esp_err_t read_raw(float *pa)
{
    uint8_t b[6];
    ESP_RETURN_ON_ERROR(rd(REG_DATA, b, sizeof b), TAG, "data");
    uint32_t up = (uint32_t)b[0] | (uint32_t)b[1] << 8 | (uint32_t)b[2] << 16;
    uint32_t ut = (uint32_t)b[3] | (uint32_t)b[4] << 8 | (uint32_t)b[5] << 16;
    *pa = compensate(up, ut);
    return ESP_OK;
}

esp_err_t bmp390_init(void)
{
    if (!s_bus) {
        i2c_master_bus_config_t bus = {
            .i2c_port = I2C_NUM_0,
            .sda_io_num = PIN_SDA,
            .scl_io_num = PIN_SCL,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .flags.enable_internal_pullup = true, /* the carrier also has 4.7k */
        };
        ESP_RETURN_ON_ERROR(i2c_new_master_bus(&bus, &s_bus), TAG, "bus");
        i2c_device_config_t dev = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = BMP390_ADDR,
            .scl_speed_hz = 400000,
        };
        ESP_RETURN_ON_ERROR(i2c_master_bus_add_device(s_bus, &dev, &s_dev), TAG, "dev");
    }
    uint8_t id = 0;
    ESP_RETURN_ON_ERROR(rd(REG_CHIP_ID, &id, 1), TAG, "no BMP390 at 0x%02x", BMP390_ADDR);
    if (id != 0x60 && id != 0x50) { /* BMP390, BMP388 */
        ESP_LOGE(TAG, "unexpected chip id 0x%02x", id);
        return ESP_ERR_NOT_FOUND;
    }
    ESP_RETURN_ON_ERROR(wr(REG_CMD, 0xB6), TAG, "reset");
    vTaskDelay(pdMS_TO_TICKS(3));
    ESP_RETURN_ON_ERROR(load_calibration(), TAG, "calib");
    /* x4 pressure, x1 temperature: 10.9 ms per conversion, fits 50 Hz. No IIR:
     * grip.c does its own filtering and needs the latency low. */
    ESP_RETURN_ON_ERROR(wr(REG_OSR, 0x02), TAG, "osr");
    ESP_RETURN_ON_ERROR(wr(REG_ODR, 0x02), TAG, "odr"); /* 200 Hz / 2^2 = 50 Hz */
    ESP_RETURN_ON_ERROR(wr(REG_CONFIG, 0x00), TAG, "iir");
    return ESP_OK;
}

esp_err_t bmp390_start_stream(void)
{
    ESP_RETURN_ON_ERROR(wr(REG_PWR_CTRL, PWR_PRESS_TEMP | MODE_NORMAL), TAG, "normal");
    vTaskDelay(pdMS_TO_TICKS(25));
    uint8_t err = 0;
    rd(REG_ERR, &err, 1);
    if (err)
        ESP_LOGW(TAG, "ERR_REG 0x%02x (conf_err = ODR too fast for the oversampling)", err);
    return ESP_OK;
}

esp_err_t bmp390_read(float *pa) { return read_raw(pa); }

esp_err_t bmp390_one_shot(float *pa)
{
    ESP_RETURN_ON_ERROR(wr(REG_PWR_CTRL, PWR_PRESS_TEMP | MODE_FORCED), TAG, "forced");
    for (int i = 0; i < 10; i++) {
        vTaskDelay(pdMS_TO_TICKS(i == 0 ? 11 : 2));
        uint8_t st = 0;
        ESP_RETURN_ON_ERROR(rd(REG_STATUS, &st, 1), TAG, "status");
        if (st & STATUS_DRDY_P)
            return read_raw(pa);
    }
    return ESP_ERR_TIMEOUT;
}

esp_err_t bmp390_sleep(void) { return wr(REG_PWR_CTRL, PWR_PRESS_TEMP); /* mode 00 = sleep */ }
