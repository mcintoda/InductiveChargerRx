#include "accel.h"

#include "board.h"
#include "esp_log.h"
#include "sensor_bus.h"

static const char *TAG = "accel";

enum {
    WHO_AM_I = 0x0F, CTRL1 = 0x20, CTRL2 = 0x21, CTRL3 = 0x22, CTRL4_INT1 = 0x23, CTRL6 = 0x25, OUT_X_L = 0x28,
    TAP_THS_X = 0x30, TAP_THS_Y = 0x31, TAP_THS_Z = 0x32, INT_DUR = 0x33, WAKE_UP_THS = 0x34, WAKE_UP_DUR = 0x35,
    FREE_FALL = 0x36, ALL_INT_SRC = 0x3B, CTRL7 = 0x3F,
};

static esp_err_t w(uint8_t reg, uint8_t v) { return sensor_reg_write(LIS2DW12_ADDR, reg, v); }

bool accel_present(void)
{
    uint8_t id = 0;
    return sensor_reg_read(LIS2DW12_ADDR, WHO_AM_I, &id, 1) == ESP_OK && id == 0x44;
}

static esp_err_t common(void)
{
    esp_err_t err = w(CTRL2, 0x0C);                    // BDU, auto-increment
    // INT1 push-pull, active LOW (H_LACTIVE) so it shares the ext1 ANY_LOW wake with QI_DET_N; latched (LIR)
    if (err == ESP_OK) err = w(CTRL3, 0x18);
    if (err == ESP_OK) err = w(CTRL6, 0x00);           // +-2 g, ODR/2 bandwidth
    if (err == ESP_OK) err = w(CTRL7, 0x20);           // INTERRUPTS_ENABLE
    return err;
}

esp_err_t accel_arm_wake(void)
{
    esp_err_t err = common();
    if (err == ESP_OK) err = w(CTRL1, 0x20);           // ODR 12.5 Hz, low-power mode 1
    if (err == ESP_OK) err = w(WAKE_UP_THS, 0x06);     // 6 x 31.25 mg = 0.19 g, no tap
    if (err == ESP_OK) err = w(WAKE_UP_DUR, 0x00);
    if (err == ESP_OK) err = w(CTRL4_INT1, 0x20);      // INT1_WU
    accel_events();                                    // clear anything pending so INT1 is high before sleep
    if (err != ESP_OK) ESP_LOGW(TAG, "arm wake: %s", esp_err_to_name(err));
    return err;
}

esp_err_t accel_awake(void)
{
    esp_err_t err = common();
    if (err == ESP_OK) err = w(CTRL1, 0x70);           // ODR 400 Hz, low-power mode 1 (taps need >= 400 Hz)
    if (err == ESP_OK) err = w(TAP_THS_X, 0x09);       // 9 x 62.5 mg = 0.56 g, 6D threshold 80 deg
    if (err == ESP_OK) err = w(TAP_THS_Y, 0x09);       // tap priority XYZ
    if (err == ESP_OK) err = w(TAP_THS_Z, 0xE9);       // taps on all axes, Z threshold 0.56 g
    if (err == ESP_OK) err = w(INT_DUR, 0x7A);         // latency 7 x 32 / ODR = 0.56 s, quiet 2, shock 2
    if (err == ESP_OK) err = w(WAKE_UP_THS, 0x86);     // double tap enabled, wake threshold 0.19 g
    if (err == ESP_OK) err = w(CTRL4_INT1, 0x08);      // INT1_TAP (double tap) on the pin as well
    accel_events();
    if (err != ESP_OK) ESP_LOGW(TAG, "awake config: %s", esp_err_to_name(err));
    return err;
}

uint8_t accel_events(void)
{
    uint8_t src = 0;
    if (sensor_reg_read(LIS2DW12_ADDR, ALL_INT_SRC, &src, 1) != ESP_OK) return 0;
    return src & 0x3F;
}

esp_err_t accel_gravity(float g[3])
{
    uint8_t b[6];
    esp_err_t err = sensor_reg_read(LIS2DW12_ADDR, OUT_X_L, b, 6);
    if (err != ESP_OK) return err;
    for (int i = 0; i < 3; i++) {
        int16_t v = (int16_t)(b[2 * i] | (b[2 * i + 1] << 8));
        g[i] = (v >> 4) * 0.000976f;                   // low-power mode 1: 12-bit, 0.976 mg/LSB at +-2 g
    }
    return ESP_OK;
}
