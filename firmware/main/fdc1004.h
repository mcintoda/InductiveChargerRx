// FDC1004 4-channel capacitance-to-digital converter (option, see docs/sensing-options.md).
#pragma once
#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "fdclevel.h"

typedef struct {
    uint8_t capdac[FDC_CH];   // offset DAC per channel (3.125 pF steps), auto-ranged, kept across sleeps
} fdc_state_t;

bool fdc_present(void);       // answers at 0x50 (the 0R links / part may not be fitted)
// single-ended measurement of CIN1..CIN4 (100 S/s each); returns total capacitance in pF per channel
esp_err_t fdc_read_all(fdc_state_t *st, float pf[FDC_CH]);
