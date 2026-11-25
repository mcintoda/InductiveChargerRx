/* squeeze main board rev A: ESP32-C3-MINI-1U (hardware/tools/parts.py is the source of truth).
 * Strapping pins: GPIO2 pulled up (unused), GPIO8 pulled up (also the charger's open-drain CHG),
 * GPIO9 = BOOT test pad (internal pull-up). */
#pragma once

#define PIN_VBAT_ADC    0   /* battery / 2 (1M/1M + 100 nF), ADC1_CH0 */
#define ADC_CH_VBAT     ADC_CHANNEL_0
#define PIN_VBUS_SENSE  1   /* USB plugged in: 5 V x 100k/156k = 3.2 V */
#define PIN_LED_R       3   /* RGB LED cathodes via 220 / 68 / 68 ohm; common anode on 3V3: active low */
#define PIN_LED_G       4
#define PIN_LED_B       5
#define PIN_SDA         6   /* BMP280 */
#define PIN_SCL         7
#define PIN_CHG_N       8   /* BQ51050B CHG, low while charging */
#define PIN_SERVO_PWM   10  /* 100 ohm to the servo signal wire */
#define PIN_SERVO_EN    20  /* TPS61023 EN (100k pull-down): 5 V on, fully disconnected when low */

#define LED_ACTIVE_LOW  1
#define BMP280_ADDR     0x76 /* SDO to GND */
