#pragma once
#include <stdio.h>
#include <stdlib.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_NOT_FOUND 0x105
#define ESP_ERR_TIMEOUT 0x107
#define ESP_ERR_NVS_NO_FREE_PAGES 0x110d
#define ESP_ERR_NVS_NEW_VERSION_FOUND 0x1110
#define ESP_ERROR_CHECK(x) do { esp_err_t rc_ = (x); if (rc_ != ESP_OK) { \
    fprintf(stderr, "ESP_ERROR_CHECK failed: %s = %d\n", #x, rc_); abort(); } } while (0)
