#include "status.h"

#include "board.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sensor_bus.h"

static const char *TAG = "status";
enum { RSTR = 0x00, GCR = 0x01, LCTR = 0x30, LCFG0 = 0x31, PWM0 = 0x34, LED0T0 = 0x37 };
enum { IMAX_5MA = 1, MD_BREATH = 0x10 };
// AW2013 timing codes: 0 = 0.13 s, 1 = 0.26, 2 = 0.52, 3 = 1.04, 4 = 2.08, 5 = 4.16
typedef struct { uint8_t r, g, b; bool breath; uint8_t t1, t2, t3, t4; } pattern_t;

static const pattern_t PAT[] = {
    [LED_OFF] = {0},
    [LED_SETUP] = {0, 160, 255, true, 0, 1, 0, 2},
    [LED_CHARGING] = {255, 90, 0, true, 3, 1, 3, 2},
    [LED_CHARGED] = {0, 200, 0, false},
    [LED_MONITOR] = {0, 0, 60, true, 0, 0, 0, 5},
    [LED_NEARLY] = {255, 180, 0, true, 2, 1, 2, 1},
    [LED_ALARM] = {255, 0, 0, true, 0, 1, 0, 1},
    [LED_HOT] = {255, 0, 200, true, 1, 1, 1, 1},
    [LED_ATTENTION] = {255, 80, 0, true, 0, 0, 0, 3},
    [LED_OK] = {160, 160, 160, false},                 // soft white: silenced (green steady means charged)
};
static led_state_t s_state = LED_OFF;
static bool s_rail;

static esp_err_t w(uint8_t reg, uint8_t v) { return sensor_reg_write(AW2013_ADDR, reg, v); }

static void apply(const pattern_t *p)
{
    i2c_master_bus_handle_t bus;
    bool on = p->r || p->g || p->b;
    if (on && !s_rail) s_rail = sensor_bus_acquire(&bus) == ESP_OK;
    if (!s_rail) return;
    esp_err_t err = w(RSTR, 0x55);                     // soft reset: known state
    if (on) {
        err |= w(GCR, 0x01);                           // enable
        const uint8_t pwm[3] = {p->g, p->b, p->r};    // LED0 = green, LED1 = blue, LED2 = red (board layout)
        for (int ch = 0; ch < 3; ch++) {
            err |= w(LCFG0 + ch, IMAX_5MA | (p->breath ? MD_BREATH : 0));
            err |= w(PWM0 + ch, pwm[ch]);
            if (p->breath) {
                err |= w(LED0T0 + 3 * ch, (uint8_t)(p->t1 << 4 | p->t2));
                err |= w(LED0T0 + 3 * ch + 1, (uint8_t)(p->t3 << 4 | p->t4));
                err |= w(LED0T0 + 3 * ch + 2, 0x00);   // no delay, repeat forever
            }
        }
        err |= w(LCTR, (pwm[0] ? 1 : 0) | (pwm[1] ? 2 : 0) | (pwm[2] ? 4 : 0));
    }
    if (err != ESP_OK) ESP_LOGW(TAG, "AW2013 not answering");
    if (!on && s_rail) { sensor_bus_release(); s_rail = false; }
}

void status_led(led_state_t s)
{
    if (s == s_state) return;
    s_state = s;
    apply(&PAT[s]);
}

led_state_t status_current(void) { return s_state; }

void status_flash(int r, int g, int b, int n, int ms)
{
    pattern_t on = {.r = (uint8_t)r, .g = (uint8_t)g, .b = (uint8_t)b}, off = {0};
    led_state_t keep = s_state;
    for (int i = 0; i < n; i++) {
        apply(&on); vTaskDelay(pdMS_TO_TICKS(ms));
        apply(&off); vTaskDelay(pdMS_TO_TICKS(ms));
    }
    s_state = LED_OFF;
    status_led(keep);
}

void status_battery(int pct)
{
    if (pct > 50) status_flash(0, 200, 0, 1, 1000);
    else if (pct > 20) status_flash(255, 180, 0, 1, 1000);
    else status_flash(255, 0, 0, 1, 1000);
}

void status_quiet(bool quiet)
{
    if (s_state == LED_OFF || !s_rail) return;
    w(LCTR, quiet ? 0 : (PAT[s_state].g ? 1 : 0) | (PAT[s_state].b ? 2 : 0) | (PAT[s_state].r ? 4 : 0));
}
