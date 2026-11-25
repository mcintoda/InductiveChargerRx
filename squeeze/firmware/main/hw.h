/* Servo, LED and power: the small hardware pieces. */
#pragma once
#include <stdbool.h>
#include <stdint.h>

void servo_init(float rest_deg);
/* Sets the angle; powers the boost/load switch up when the plates must move and
 * down again 500 ms after they are back at rest (an idle SG90 still draws ~5 mA). */
void servo_set(float deg, bool at_rest, uint32_t now_ms);
void servo_off(void);

void led_init(void);
void led_rgb(uint32_t rgb, float brightness); /* rgb = 0xRRGGBB, brightness 0..1 */

void power_init(void);
int power_vbat_mv(void);
bool power_charging(void);    /* on the Qi pad and charging */
bool power_usb(void);         /* USB-C plugged in (flashing / monitoring): stay awake */
