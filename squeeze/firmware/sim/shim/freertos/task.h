#pragma once
#include "FreeRTOS.h"
void vTaskDelay(TickType_t ticks);
void vTaskDelayUntil(TickType_t *prev, TickType_t inc);
TickType_t xTaskGetTickCount(void);
