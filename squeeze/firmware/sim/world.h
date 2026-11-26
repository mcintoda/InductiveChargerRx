/* The simulated world that two copies of the real firmware run in (see sim/README.md).
 * shim.c (compiled once per unit, symbols prefixed) calls these; world.c implements them. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct world_api {
    int64_t (*now_us)(void);
    void (*wait_until)(int unit, int64_t t_us);           /* block this unit's thread until sim time t */
    void (*wait_radio)(int unit, int64_t deadline_us);    /* ...until a frame arrives or the deadline */
    void (*log)(int unit, char level, const char *tag, const char *msg);
    /* devices */
    bool (*i2c_present)(int unit, uint8_t addr);
    void (*i2c_write)(int unit, uint8_t reg, uint8_t val);
    void (*i2c_read)(int unit, uint8_t reg, uint8_t *buf, size_t n);
    void (*gpio_set)(int unit, int pin, int level);
    int (*gpio_get)(int unit, int pin);
    void (*pwm)(int unit, int gpio, double duty_frac, double freq_hz); /* duty as driven on the pin */
    int (*adc_mv)(int unit, int channel);                              /* voltage at the ADC pin */
    void (*radio_on)(int unit, bool on, int channel);
    void (*radio_send)(int unit, const uint8_t *data, int len);
    int (*radio_take)(int unit, uint8_t *buf, int max);                /* next arrived frame, or -1 */
    void (*deep_sleep)(int unit, int64_t us);                          /* record; the shim then longjmps */
    void (*light_sleep)(int unit, bool on);                            /* CPU halted, RAM kept */
} world_api_t;

/* Each unit object exports (prefixed uA_ / uB_): */
void sim_unit_run(const world_api_t *w, int unit);   /* boots, runs app_main, handles deep sleep: never returns */
