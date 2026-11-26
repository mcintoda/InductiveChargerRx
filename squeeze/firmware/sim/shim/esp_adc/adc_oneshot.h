#pragma once
#include "esp_err.h"
typedef struct sim_adc *adc_oneshot_unit_handle_t;
typedef enum { ADC_UNIT_1 = 0 } adc_unit_t;
typedef enum { ADC_CHANNEL_0 = 0, ADC_CHANNEL_1, ADC_CHANNEL_2, ADC_CHANNEL_3, ADC_CHANNEL_4 } adc_channel_t;
typedef enum { ADC_ATTEN_DB_12 = 3 } adc_atten_t;
typedef enum { ADC_BITWIDTH_DEFAULT = 0 } adc_bitwidth_t;
typedef struct { adc_unit_t unit_id; int clk_src; int ulp_mode; } adc_oneshot_unit_init_cfg_t;
typedef struct { adc_atten_t atten; adc_bitwidth_t bitwidth; } adc_oneshot_chan_cfg_t;
esp_err_t adc_oneshot_new_unit(const adc_oneshot_unit_init_cfg_t *cfg, adc_oneshot_unit_handle_t *ret);
esp_err_t adc_oneshot_config_channel(adc_oneshot_unit_handle_t h, adc_channel_t ch, const adc_oneshot_chan_cfg_t *cfg);
esp_err_t adc_oneshot_read(adc_oneshot_unit_handle_t h, adc_channel_t ch, int *raw);
