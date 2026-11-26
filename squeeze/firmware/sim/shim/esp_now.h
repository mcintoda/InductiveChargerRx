#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_wifi.h"
typedef struct { uint8_t *src_addr; uint8_t *des_addr; void *rx_ctrl; } esp_now_recv_info_t;
typedef void (*esp_now_recv_cb_t)(const esp_now_recv_info_t *info, const uint8_t *data, int len);
typedef struct { uint8_t peer_addr[6]; uint8_t lmk[16]; uint8_t channel; wifi_interface_t ifidx; bool encrypt;
                 void *priv; } esp_now_peer_info_t;
esp_err_t esp_now_init(void);
esp_err_t esp_now_deinit(void);
esp_err_t esp_now_register_recv_cb(esp_now_recv_cb_t cb);
esp_err_t esp_now_add_peer(const esp_now_peer_info_t *peer);
esp_err_t esp_now_send(const uint8_t *peer_addr, const uint8_t *data, size_t len);
