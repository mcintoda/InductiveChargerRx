#pragma once
#include <stdint.h>
#include "esp_err.h"
typedef struct { int magic; } wifi_init_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() { .magic = 1 }
typedef enum { WIFI_STORAGE_FLASH = 0, WIFI_STORAGE_RAM } wifi_storage_t;
typedef enum { WIFI_MODE_NULL = 0, WIFI_MODE_STA } wifi_mode_t;
typedef enum { WIFI_IF_STA = 0 } wifi_interface_t;
typedef enum { WIFI_SECOND_CHAN_NONE = 0 } wifi_second_chan_t;
typedef enum { WIFI_PS_NONE = 0 } wifi_ps_type_t;
#define WIFI_PROTOCOL_11B 1
#define WIFI_PROTOCOL_11G 2
#define WIFI_PROTOCOL_11N 4
#define WIFI_PROTOCOL_LR 8
esp_err_t esp_wifi_init(const wifi_init_config_t *cfg);
esp_err_t esp_wifi_set_storage(wifi_storage_t s);
esp_err_t esp_wifi_set_mode(wifi_mode_t m);
esp_err_t esp_wifi_set_protocol(wifi_interface_t ifx, uint8_t bitmap);
esp_err_t esp_wifi_start(void);
esp_err_t esp_wifi_stop(void);
esp_err_t esp_wifi_set_channel(uint8_t primary, wifi_second_chan_t second);
esp_err_t esp_wifi_set_ps(wifi_ps_type_t t);
