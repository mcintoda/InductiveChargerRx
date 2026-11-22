#include "shtc3.h"

#include "board.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sensor_bus.h"

static uint8_t crc8(const uint8_t *d, int n)
{
    uint8_t c = 0xFF;
    for (int i = 0; i < n; i++) {
        c ^= d[i];
        for (int b = 0; b < 8; b++) c = (c & 0x80) ? (uint8_t)((c << 1) ^ 0x31) : (uint8_t)(c << 1);
    }
    return c;
}

esp_err_t shtc3_read(float *temp_c, float *rh)
{
    i2c_master_bus_handle_t bus;
    esp_err_t err = sensor_bus_acquire(&bus);          // hold the rail across wake / measure / sleep
    if (err != ESP_OK) return err;
    const uint8_t wake[2] = {0x35, 0x17}, meas[2] = {0x78, 0x66}, sleep[2] = {0xB0, 0x98};
    uint8_t b[6];
    err = sensor_xfer(SHTC3_ADDR, wake, 2, NULL, 0);
    vTaskDelay(pdMS_TO_TICKS(1));                      // tPU after wake-up: 240 us
    if (err == ESP_OK) err = sensor_xfer(SHTC3_ADDR, meas, 2, NULL, 0);   // T first, no clock stretching
    vTaskDelay(pdMS_TO_TICKS(15));                     // normal mode: 12.1 ms max
    if (err == ESP_OK) err = sensor_xfer(SHTC3_ADDR, NULL, 0, b, 6);
    sensor_xfer(SHTC3_ADDR, sleep, 2, NULL, 0);
    sensor_bus_release();
    if (err != ESP_OK) return err;
    if (crc8(b, 2) != b[2] || crc8(b + 3, 2) != b[5]) return ESP_ERR_INVALID_CRC;
    *temp_c = -45.0f + 175.0f * ((b[0] << 8) | b[1]) / 65536.0f;
    *rh = 100.0f * ((b[3] << 8) | b[4]) / 65536.0f;
    return ESP_OK;
}
