#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
typedef struct sim_i2c_bus *i2c_master_bus_handle_t;
typedef struct sim_i2c_dev *i2c_master_dev_handle_t;
typedef enum { I2C_NUM_0 = 0 } i2c_port_num_t;
typedef enum { I2C_CLK_SRC_DEFAULT = 0 } i2c_clock_source_t;
typedef enum { I2C_ADDR_BIT_LEN_7 = 0 } i2c_addr_bit_len_t;
typedef struct {
    i2c_port_num_t i2c_port; int sda_io_num; int scl_io_num; i2c_clock_source_t clk_source;
    uint8_t glitch_ignore_cnt; int intr_priority; size_t trans_queue_depth;
    struct { uint32_t enable_internal_pullup : 1; } flags;
} i2c_master_bus_config_t;
typedef struct { i2c_addr_bit_len_t dev_addr_length; uint16_t device_address; uint32_t scl_speed_hz; } i2c_device_config_t;
esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t *cfg, i2c_master_bus_handle_t *ret);
esp_err_t i2c_master_bus_add_device(i2c_master_bus_handle_t bus, const i2c_device_config_t *cfg,
                                    i2c_master_dev_handle_t *ret);
esp_err_t i2c_master_transmit(i2c_master_dev_handle_t dev, const uint8_t *w, size_t wlen, int timeout_ms);
esp_err_t i2c_master_transmit_receive(i2c_master_dev_handle_t dev, const uint8_t *w, size_t wlen, uint8_t *r,
                                      size_t rlen, int timeout_ms);
