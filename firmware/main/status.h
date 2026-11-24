// RGB status LED (AW2013 + XL-1615 common-anode LED, both on the switched sensor rail).
// Every channel is limited to 5 mA: the rail is a GPIO and also feeds the FDC1004 (>= 3.0 V).
#pragma once
#include <stdbool.h>

typedef enum {
    LED_OFF = 0,
    LED_SETUP,        // cyan blink: waiting for Wi-Fi setup
    LED_CHARGING,     // amber breathe
    LED_CHARGED,      // green steady
    LED_MONITOR,      // short dim blue blip every 4 s while watching a bath
    LED_NEARLY,       // yellow slow breathe
    LED_ALARM,        // red fast blink
    LED_HOT,          // magenta breathe
    LED_ATTENTION,    // orange double blink: tilted / off the bracket, moisture in the case
    LED_OK,           // soft white steady: alarm silenced on the device (green steady = charged)
} led_state_t;

void status_led(led_state_t s);          // keeps the rail on while the LED shows anything
void status_flash(int r, int g, int b, int n, int ms);   // blocking blink, 0..255 per colour
void status_battery(int pct);            // 1 s: green > 50 %, yellow > 20 %, red below
// the FDC1004 measures on the same rail: pause the LED current for the ~40 ms conversion
void status_quiet(bool quiet);
