// LIS2DW12 accelerometer: always powered from +3V3 (~1 uA in its sleep mode), INT1 -> GPIO21 (active low).
// The I2C pull-ups live on the switched rail, so every call briefly powers the rail.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

#define ACC_EV_DOUBLE_TAP 0x08            // ALL_INT_SRC bits
#define ACC_EV_SINGLE_TAP 0x04
#define ACC_EV_WAKE       0x02
#define ACC_EV_FREE_FALL  0x01

bool accel_present(void);
// deep sleep: 12.5 Hz low-power, wake-up (motion > ~0.19 g) on INT1, latched. ~1 uA.
esp_err_t accel_arm_wake(void);
// awake: 400 Hz, double-tap detection (polled with accel_events), gravity readable.
esp_err_t accel_awake(void);
uint8_t accel_events(void);               // reads and clears the latched sources (ACC_EV_*)
esp_err_t accel_gravity(float g[3]);      // in g
