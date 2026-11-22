// brim bath monitor - pin map (schematic rev B, hardware/kicad/bath_monitor.kicad_sch)
#pragma once
#include "driver/gpio.h"
#include "driver/touch_pad.h"

#define N_LEVEL_PADS 6
#define N_SENSE_PADS 7                    // 6 level pads + dry reference pad
// touch channels: index 0..5 = PAD1 (bottom, wake) .. PAD6 (top), index 6 = REF
static const touch_pad_t SENSE_CH[N_SENSE_PADS] = {
    TOUCH_PAD_NUM1, TOUCH_PAD_NUM2, TOUCH_PAD_NUM3, TOUCH_PAD_NUM4, TOUCH_PAD_NUM5, TOUCH_PAD_NUM6, TOUCH_PAD_NUM7};
// deep-sleep wake pad: PAD1, or PAD2 when the FDC1004 links are fitted (its ESD diodes clamp PAD1 with the rail off)
#define GUARD_CH         TOUCH_PAD_NUM8   // unconnected (IO8); the shield, not a guard ring, does the work
// shield = TOUCH_PAD_NUM14 (GPIO14), selected automatically by the waterproof function

#define PIN_VBAT_SENSE   GPIO_NUM_9       // ADC1_CH8, 1M/1M divider
#define PIN_SDA          GPIO_NUM_10
#define PIN_SCL          GPIO_NUM_11
#define PIN_SENSE_PWR    GPIO_NUM_12      // powers TMP117, FDC1004, SHTC3, AW2013 + RGB LED, I2C pull-ups
#define PIN_QI_DET_N     GPIO_NUM_13      // low while on a Qi pad (RTC GPIO, ext1 wake)
#define PIN_CHG_N        GPIO_NUM_40      // BQ51050B CHG, open drain, low while charging
#define PIN_ACC_INT      GPIO_NUM_21      // LIS2DW12 INT1, active low push-pull (RTC GPIO, ext1 wake)
#define PIN_BUZ_A        GPIO_NUM_16      // piezo disc, driven in antiphase with BUZ_B through 1k each
#define PIN_BUZ_B        GPIO_NUM_17

#define TMP117_ADDR      0x48
#define LIS2DW12_ADDR    0x19             // SA0 tied high (no pull-up current)
#define SHTC3_ADDR       0x70
#define AW2013_ADDR      0x45

// geometry (mm) - see docs/placement-and-electrodes.md
#define PAD_PITCH_MM     10.0f
#define PAD_HEIGHT_MM    9.0f
#define FRINGE_OFFSET_MM 1.7f             // fixed fringe offset from the field simulation
#define RANGE_MM         60.0f
