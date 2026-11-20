#include "fdc1004.h"

#include "esp_check.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sensor_bus.h"

static const char *TAG = "fdc1004";
#define FDC_ADDR 0x50
#define REG_MEAS_MSB(n) (0x00 + 2 * (n))
#define REG_MEAS_LSB(n) (0x01 + 2 * (n))
#define REG_CONF_MEAS(n) (0x08 + (n))
#define REG_FDC_CONF 0x0C
#define RATE_100 (1u << 10)
#define CAPDAC_PF 3.125f

static esp_err_t wr16(i2c_master_dev_handle_t d, uint8_t reg, uint16_t v)
{
    uint8_t b[3] = {reg, v >> 8, v & 0xff};
    return i2c_master_transmit(d, b, 3, 50);
}

static esp_err_t rd16(i2c_master_dev_handle_t d, uint8_t reg, uint16_t *v)
{
    uint8_t b[2];
    esp_err_t err = i2c_master_transmit_receive(d, &reg, 1, b, 2, 50);
    *v = (b[0] << 8) | b[1];
    return err;
}

static esp_err_t open_dev(i2c_master_bus_handle_t *bus, i2c_master_dev_handle_t *dev)
{
    ESP_RETURN_ON_ERROR(sensor_bus_acquire(bus), TAG, "bus");
    i2c_device_config_t cfg = {.dev_addr_length = I2C_ADDR_BIT_LEN_7, .device_address = FDC_ADDR, .scl_speed_hz = 400000};
    esp_err_t err = i2c_master_bus_add_device(*bus, &cfg, dev);
    if (err != ESP_OK) sensor_bus_release();
    return err;
}

bool fdc_present(void)
{
    i2c_master_bus_handle_t bus;
    if (sensor_bus_acquire(&bus) != ESP_OK) return false;
    bool ok = i2c_master_probe(bus, FDC_ADDR, 50) == ESP_OK;
    sensor_bus_release();
    return ok;
}

// one single-ended measurement of channel n against the CAPDAC; returns the input-referred pF
static esp_err_t measure(i2c_master_dev_handle_t d, int n, uint8_t capdac, float *pf)
{
    ESP_RETURN_ON_ERROR(wr16(d, REG_CONF_MEAS(n), (uint16_t)((n << 13) | (4u << 10) | ((capdac & 0x1f) << 5))), TAG, "cfg");
    ESP_RETURN_ON_ERROR(wr16(d, REG_FDC_CONF, RATE_100 | (0x80u >> n)), TAG, "trigger");
    uint16_t conf = 0;
    for (int i = 0; i < 10; i++) {                         // ~10 ms per conversion at 100 S/s
        vTaskDelay(pdMS_TO_TICKS(4));
        ESP_RETURN_ON_ERROR(rd16(d, REG_FDC_CONF, &conf), TAG, "poll");
        if (conf & (0x08u >> n)) break;
    }
    if (!(conf & (0x08u >> n))) return ESP_ERR_TIMEOUT;
    uint16_t msb, lsb;
    ESP_RETURN_ON_ERROR(rd16(d, REG_MEAS_MSB(n), &msb), TAG, "msb");
    ESP_RETURN_ON_ERROR(rd16(d, REG_MEAS_LSB(n), &lsb), TAG, "lsb");
    int32_t raw = (int32_t)(((uint32_t)msb << 16) | lsb) >> 8;   // 24-bit two's complement
    *pf = raw / 524288.0f;                                       // 2^19 counts per pF, +-16 pF span
    return ESP_OK;
}

esp_err_t fdc_read_all(fdc_state_t *st, float pf[FDC_CH])
{
    i2c_master_bus_handle_t bus;
    i2c_master_dev_handle_t dev;
    ESP_RETURN_ON_ERROR(open_dev(&bus, &dev), TAG, "open");
    esp_err_t err = ESP_OK;
    for (int n = 0; n < FDC_CH && err == ESP_OK; n++) {
        float v = 0;
        for (int tries = 0; tries < 6; tries++) {          // keep the input within the +-15 pF window
            err = measure(dev, n, st->capdac[n], &v);
            if (err != ESP_OK) break;
            int step = (int)(v / CAPDAC_PF);                // re-centre the CAPDAC on the input
            if ((v > 12.0f || v < -12.0f) && step != 0) {
                int c = st->capdac[n] + step;
                c = c < 0 ? 0 : (c > 31 ? 31 : c);
                if (c == st->capdac[n]) break;               // at the end of the CAPDAC range
                st->capdac[n] = (uint8_t)c;
            } else break;
        }
        pf[n] = v + st->capdac[n] * CAPDAC_PF;
    }
    i2c_master_bus_rm_device(dev);
    sensor_bus_release();
    return err;
}
