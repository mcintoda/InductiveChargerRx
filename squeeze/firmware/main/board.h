/* Seeed XIAO ESP32-C3 on the squeeze carrier board (docs/design.md §5).
 * GPIO2 and GPIO9 (strapping) are left free; GPIO8 (strapping, must not be
 * pulled low at boot) only reads the charger's open-drain CHG with a 100k pull-up. */
#pragma once

#define PIN_VBAT_ADC    3   /* D1  battery / 2 (1M/1M divider + 100 nF), ADC1_CH3 */
#define PIN_LED_R       4   /* D2  RGB LED, common cathode, 220R per colour */
#define PIN_SERVO_EN    5   /* D3  boost + load switch enable, 100k pull-down */
#define PIN_SDA         6   /* D4  BMP390 */
#define PIN_SCL         7   /* D5  */
#define PIN_LED_G       21  /* D6  (UART0 TX: flickers during the ROM boot log, harmless) */
#define PIN_LED_B       20  /* D7  */
#define PIN_CHG_N       8   /* D8  BQ51050B CHG, low while charging */
#define PIN_SERVO_PWM   10  /* D10 */

#define BMP390_ADDR     0x77 /* SDO high (Adafruit breakout default); 0x76 with SDO low */
