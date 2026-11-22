// Switched sensor rail (GPIO12 -> TMP117, FDC1004, I2C pull-ups) and the shared I2C bus.
// Reference counted: the rail stays on while anyone holds it.
#pragma once
#include "driver/i2c_master.h"
#include "esp_err.h"

esp_err_t sensor_bus_acquire(i2c_master_bus_handle_t *bus);
void sensor_bus_release(void);

// One-shot register access on the shared bus (acquires and releases the rail around the transfer).
// rx may be NULL for a write-only transfer.
esp_err_t sensor_xfer(uint8_t addr, const uint8_t *tx, size_t ntx, uint8_t *rx, size_t nrx);
esp_err_t sensor_reg_write(uint8_t addr, uint8_t reg, uint8_t val);
esp_err_t sensor_reg_read(uint8_t addr, uint8_t reg, uint8_t *buf, size_t n);
