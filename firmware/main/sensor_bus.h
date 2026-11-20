// Switched sensor rail (GPIO12 -> TMP117, FDC1004, I2C pull-ups) and the shared I2C bus.
// Reference counted: the rail stays on while anyone holds it.
#pragma once
#include "driver/i2c_master.h"
#include "esp_err.h"

esp_err_t sensor_bus_acquire(i2c_master_bus_handle_t *bus);
void sensor_bus_release(void);
