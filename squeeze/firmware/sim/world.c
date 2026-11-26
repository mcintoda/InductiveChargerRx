/* squeeze virtual test bench: two copies of the real firmware in a simulated world.
 *
 *   ./sim scenario.txt out_prefix      -> out_prefix.events.csv, out_prefix.log, summary on stdout
 *
 * Lockstep scheduler: each unit runs in its own thread, but only one runs at a time, and only between
 * blocking calls (vTaskDelay, queue waits, deep sleep), so the simulation is deterministic for a seed.
 * Models (all documented in sim/README.md): BMP280 registers, servo + oval cam + plates, hand and air,
 * ESP-NOW radio, battery current, and the people holding the units.
 */
#include <math.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "../main/bmp280_comp.h"
#include "world.h"

void uA_sim_unit_run(const world_api_t *w, int unit);
void uB_sim_unit_run(const world_api_t *w, int unit);

#define NU 2
#define TICK_US 5000            /* physics / people step */
#define P0 101325.0

/* ---------------- pins (firmware/main/board.h) ---------------- */
#define PIN_VBUS 1
#define PIN_LED_R 3
#define PIN_LED_G 4
#define PIN_LED_B 5
#define PIN_CHG 8
#define PIN_PWM 10
#define PIN_SERVO_EN 20

/* ---------------- scenario ---------------- */
typedef struct { double t, dur, force; } squeeze_t;
enum { AG_NONE, AG_PARENT, AG_CHILD };

typedef struct {
    /* config */
    double start_s, vbat_soc, held_from, held_to;
    int usb, charging, sensor, agent;
    double agent_force, agent_start, grip_n, tremor_n, tremor_state;
    int agent_rounds;
    squeeze_t sq[256];
    int nsq;
    /* scheduler */
    pthread_cond_t cv;
    int64_t wake;
    int waiting, radio_wait, granted;
    /* hardware */
    int servo_en, asleep, lightsleep;
    double pulse_us, led[3];
    int radio_on, channel;
    struct { int64_t t; int n; uint8_t b[64]; } rx[64];
    int nrx;
    uint8_t ctrl_meas, bmp_cfg;
    int64_t conv_end;
    double last_p;
    /* physics */
    double angle, t_air, felt_n, sq_force;
    int felt_on;
    int64_t felt_change;
    double felt_peak;
    /* power */
    double mah, soc;
    int64_t last_power_t;
    int boots, sleeps, wakes_squeeze;
    /* people */
    int64_t felt_starts[64], felt_ends[64];
    int nfelt;
    int64_t last_felt_end;
    int rounds_done, replying;
    char last_led[24];
} unit_t;

static unit_t U[NU];
static pthread_mutex_t M = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t main_cv = PTHREAD_COND_INITIALIZER;
static int64_t now;
static int running = -1, registered;
static double T_end = 60, loss = 0.0, out_from = -1, out_to = -1;
static unsigned seed = 1;
static FILE *ev, *lg;

static double rnd(void) { seed = seed * 1103515245u + 12345u; return ((seed >> 8) & 0xffffff) / (double)0x1000000; }
static double gauss(void) { double u = rnd() + 1e-12, v = rnd(); return sqrt(-2 * log(u)) * cos(2 * M_PI * v); }
static const char *NAME[NU] = { "A", "B" };

static void event(int u, const char *kind, const char *fmt, ...)
{
    char buf[256] = "";
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    fprintf(ev, "%.3f,%s,%s,%s\n", now / 1e6, u >= 0 ? NAME[u] : "-", kind, buf);
}

/* ---------------- battery ---------------- */
static double soc_to_v(double s)
{
    static const double pts[][2] = { { 0, 3.30 }, { 0.05, 3.45 }, { 0.10, 3.55 }, { 0.30, 3.70 }, { 0.60, 3.85 },
                                     { 0.90, 4.05 }, { 1.0, 4.15 } };
    for (int i = 1; i < 7; i++)
        if (s <= pts[i][0])
            return pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * (s - pts[i - 1][0]) / (pts[i][0] - pts[i - 1][0]);
    return 4.15;
}

static double lift_mm(double deg)
{
    double t = fmin(fmax(deg - 45.0, 0), 90) * M_PI / 180;
    return sqrt(25 * cos(t) * cos(t) + 64 * sin(t) * sin(t)) - 5;
}

static double current_ma(unit_t *u, double ang_speed)
{
    if (u->asleep)
        return 0.012;
    if (u->lightsleep)
        return 0.13;                                     /* ESP32-C3 light sleep, RF off */                                    /* ESP32 5 uA + LDO 2 + divider 2 + charger/BMP ~3 */
    double v = soc_to_v(u->soc);
    double i = 20.0;                                     /* CPU */
    if (u->radio_on) i += 65.0;                          /* ESP-NOW receive, PS off */
    if (u->ctrl_meas & 3) i += 0.4;                      /* BMP280 converting */
    i += 6.0 * u->led[0] + 5.0 * u->led[1] + 5.0 * u->led[2];
    if (u->servo_en) {
        double p5 = 8.0;                                 /* mA at 5 V: idle with pulses */
        if (fabs(ang_speed) > 5) p5 += 180.0;            /* moving */
        if (u->held_from <= now / 1e6 && now / 1e6 < u->held_to) p5 += 40.0 * lift_mm(u->angle);   /* pushing a hand */
        i += p5 * 5.0 / (v * 0.88);                      /* through the boost */
    }
    return i;
}

static void account(unit_t *u, double ang_speed)
{
    double dt_h = (now - u->last_power_t) / 3.6e9;
    if (dt_h > 0) {
        double i = current_ma(u, ang_speed);
        u->mah += i * dt_h;
        if (!u->charging && !u->usb)
            u->soc -= i * dt_h / 400.0;
        if (u->soc < 0) u->soc = 0;
    }
    u->last_power_t = now;
}

/* ---------------- physics and people ---------------- */
static int held(unit_t *u) { double t = now / 1e6; return t >= u->held_from && t < u->held_to; }

static double squeeze_force(unit_t *u)
{
    double t = now / 1e6, f = 0;
    for (int i = 0; i < u->nsq; i++) {
        squeeze_t *s = &u->sq[i];
        if (t < s->t || t > s->t + s->dur + 0.06)
            continue;
        double a = fmin(1, (t - s->t) / 0.06), b = fmin(1, (s->t + s->dur + 0.06 - t) / 0.06);
        f = fmax(f, s->force * fmin(a, b));
    }
    if (!held(u))
        return 0;
    /* holding force (picking up = a step) + hand tremor (smoothed noise) + squeezes */
    return u->grip_n + u->tremor_n * u->tremor_state + f;
}

static double pressure(unit_t *u)
{
    double p = P0 + 340.0 * (u->t_air - 22.0);           /* +1 degC -> +0.34 kPa (sealed volume) */
    p += 80.0 * u->sq_force;                             /* the holder: 25 N firm adult ~2 kPa (CAD) */
    p += (held(u) ? 250.0 : 20.0) * lift_mm(u->angle);   /* own plates pushing into a hand / into air */
    return p + 2.0 * gauss();                            /* BMP280 x4 noise */
}

static void add_squeeze(unit_t *u, double t, double dur, double force)
{
    if (u->nsq < 256) u->sq[u->nsq++] = (squeeze_t){ t, dur, force };
    event(u - U, "squeeze_planned", "%.3f,%.3f,%.1f", t, dur, force);
}

static void people(int k)
{
    unit_t *u = &U[k];
    double t = now / 1e6;
    if (u->agent == AG_PARENT) {
        /* sends a new pattern when it is its turn: at start, then 2 s after the child's reply ended (or 12 s) */
        static const double pat[][8] = { { 0.3, 0.4, 0.3, 0, 0, 0, 0, 0 },          /* 2 squeezes (dur, gap, dur) */
                                         { 0.25, 0.35, 0.25, 0.35, 0.6, 0, 0, 0 },  /* short short long */
                                         { 0.6, 0.5, 0.2, 0.3, 0.2, 0.3, 0.2, 0 } };/* long + 3 quick */
        static double next_t = -1;
        if (next_t < 0) next_t = u->agent_start;
        if (u->rounds_done < u->agent_rounds && t >= next_t) {
            const double *p = pat[u->rounds_done % 3];
            double s = t;
            for (int i = 0; i < 8 && p[i] > 0; i += 2) {
                add_squeeze(u, s, p[i], u->agent_force);
                s += p[i] + (i + 1 < 8 ? p[i + 1] : 0);
            }
            event(k, "pattern_sent", "%d", u->rounds_done);
            u->rounds_done++;
            next_t = s + 12.0;                            /* give up waiting for a reply after 12 s */
        }
        /* the child's reply ended (no felt squeeze for 1.5 s): next pattern 2 s later */
        if (u->nfelt && u->last_felt_end && t - u->last_felt_end / 1e6 > 1.5 && !u->felt_on) {
            next_t = fmin(next_t, t + 2.0);
            u->nfelt = 0;
        }
    } else if (u->agent == AG_CHILD) {
        /* copies what it felt: same count, durations and gaps +-20 %, after 0.6-1.2 s */
        if (u->nfelt && !u->felt_on && t - u->last_felt_end / 1e6 > 1.2) {
            double s = t + 0.6 * (1 + rnd());
            for (int i = 0; i < u->nfelt; i++) {
                double dur = (u->felt_ends[i] - u->felt_starts[i]) / 1e6 * (0.8 + 0.4 * rnd());
                add_squeeze(u, s, fmax(0.15, dur), u->agent_force);
                if (i + 1 < u->nfelt)
                    s += dur + (u->felt_starts[i + 1] - u->felt_ends[i]) / 1e6 * (0.8 + 0.4 * rnd());
            }
            event(k, "reply_planned", "%d", u->nfelt);
            u->nfelt = 0;
        }
    }
}

static void physics_step(void)
{
    for (int k = 0; k < NU; k++) {
        unit_t *u = &U[k];
        double dt = TICK_US / 1e6;
        /* servo: follows the PWM when powered; unpowered, the plate bands push the cam back to rest */
        double target = 45, speed = 300, prev = u->angle;
        if (u->servo_en && !u->asleep && u->pulse_us > 400 && u->pulse_us < 2600) {
            target = (u->pulse_us - 500) / 1900.0 * 180.0;
            speed = 600;
        }
        double d = target - u->angle, step = speed * dt;
        u->angle += fmax(-step, fmin(step, d));
        /* air temperature: warms toward the hand when held */
        double tt = held(u) ? 27.0 : 22.0, tau = held(u) ? 300.0 : 600.0;
        u->t_air += (tt - u->t_air) * dt / tau;
        u->tremor_state += (-u->tremor_state * dt / 0.15) + gauss() * sqrt(2 * dt / 0.15);   /* OU, unit variance */
        u->sq_force = squeeze_force(u);
        /* what the holder feels */
        u->felt_n = held(u) ? 4.0 * lift_mm(u->angle) : 0;
        int on = u->felt_n > (u->felt_on ? 0.6 : 1.0);
        if (on != u->felt_on) {
            if (now - u->felt_change > 60000 || u->felt_change == 0) {
                u->felt_on = on;
                u->felt_change = now;
                if (on) {
                    u->felt_peak = 0;
                    if (u->nfelt < 64) u->felt_starts[u->nfelt] = now;
                    event(k, "felt_start", "");
                } else {
                    if (u->nfelt < 64) u->felt_ends[u->nfelt++] = now;
                    u->last_felt_end = now;
                    event(k, "felt_end", "%.1f", u->felt_peak);
                }
            }
        } else {
            u->felt_change = now;
        }
        if (u->felt_on) u->felt_peak = fmax(u->felt_peak, u->felt_n);
        account(u, (u->angle - prev) / dt);
        people(k);
        /* LED as seen: colour name + brightness bucket, logged on change */
        double r = u->led[0], g = u->led[1], b = u->led[2], m = fmax(r, fmax(g, b));
        char led[24] = "off";
        if (!u->asleep && m > 0.01) {
            const char *c = "white";
            if (b > 0.6 * m && r < 0.3 * m) c = "blue";
            else if (r > 0.6 * m && g < 0.15 * m && b < 0.15 * m) c = "red";
            else if (r > 0.6 * m && g >= 0.15 * m && g < 0.6 * m && b < 0.2 * m) c = "orange";
            else if (g > 0.6 * m && r < 0.3 * m && b < 0.3 * m) c = "green";
            snprintf(led, sizeof led, "%s:%s", c, m < 0.08 ? "faint" : m < 0.3 ? "dim" : m < 0.7 ? "mid" : "bright");
        }
        if (strcmp(led, u->last_led)) {
            strcpy(u->last_led, led);
            event(k, "led", "%s,%.2f,%.2f,%.2f", led, r, g, b);
        }
    }
}

/* ---------------- world API for the shims ---------------- */
static int64_t w_now(void) { return now; }

static void block(int k)
{
    unit_t *u = &U[k];
    u->waiting = 1;
    u->granted = 0;
    running = -1;
    pthread_cond_signal(&main_cv);
    while (!u->granted)
        pthread_cond_wait(&u->cv, &M);
}

static void w_wait_until(int k, int64_t t) { pthread_mutex_lock(&M); U[k].wake = t; U[k].radio_wait = 0; block(k); pthread_mutex_unlock(&M); }

static void w_wait_radio(int k, int64_t deadline)
{
    pthread_mutex_lock(&M);
    unit_t *u = &U[k];
    int64_t w = deadline;
    for (int i = 0; i < u->nrx; i++)
        if (u->rx[i].t < w) w = u->rx[i].t;
    u->wake = w > now ? w : now + 1;
    u->radio_wait = 1;
    block(k);
    pthread_mutex_unlock(&M);
}

static void w_log(int k, char level, const char *tag, const char *msg)
{
    fprintf(lg, "%10.3f %s %c (%s) %s\n", now / 1e6, NAME[k], level, tag, msg);
    if (level == 'E' || level == 'W')
        event(k, "log", "%c %s: %s", level, tag, msg);
}

static bool w_i2c_present(int k, uint8_t addr) { return U[k].sensor && addr == 0x76; }

static void bmp_latch(unit_t *u)
{
    u->last_p = pressure(u);
}

static void w_i2c_write(int k, uint8_t reg, uint8_t val)
{
    unit_t *u = &U[k];
    if (reg == 0xE0 && val == 0xB6) { u->ctrl_meas = 0; u->bmp_cfg = 0; }
    if (reg == 0xF5) u->bmp_cfg = val;
    if (reg == 0xF4) {
        u->ctrl_meas = val;
        /* datasheet t_meas (typ) = 1 + 2 x osrs_t + 2 x osrs_p + 0.5 ms: x1/x1 5.5 ms, x1/x4 11.5 ms */
        static const int mult[8] = { 0, 1, 2, 4, 8, 16, 16, 16 };
        int64_t tm = 1000 + 2000 * mult[(val >> 5) & 7] + 2000 * mult[(val >> 2) & 7] + 500;
        if ((val & 3) == 1 || (val & 3) == 2) u->conv_end = now + tm;
        if ((val & 3) == 3) u->conv_end = now + tm + 500;
    }
}

static int32_t adc_for(double pa)
{
    static bmp280_calib_t c;
    static int init;
    if (!init) {
        const uint8_t raw[24] = { 0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC, 0x7D, 0x8E, 0x43, 0xD6, 0xD0, 0x0B,
                                  0x27, 0x0B, 0x8C, 0x00, 0xF9, 0xFF, 0x8C, 0x3C, 0xF8, 0xC6, 0x70, 0x17 };
        bmp280_parse_calib(raw, &c);
        init = 1;
    }
    int32_t lo = 0, hi = (1 << 20) - 1;                 /* pressure falls as adc rises */
    while (lo < hi) {
        int32_t mid = (lo + hi) / 2;
        if (bmp280_compensate(&c, mid, 519888, NULL) > pa) lo = mid + 1; else hi = mid;
    }
    return lo;
}

static const uint8_t CALIB[24] = { 0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC, 0x7D, 0x8E, 0x43, 0xD6, 0xD0, 0x0B,
                                   0x27, 0x0B, 0x8C, 0x00, 0xF9, 0xFF, 0x8C, 0x3C, 0xF8, 0xC6, 0x70, 0x17 };

static void w_i2c_read(int k, uint8_t reg, uint8_t *buf, size_t n)
{
    unit_t *u = &U[k];
    for (size_t i = 0; i < n; i++) {
        uint8_t r = (uint8_t)(reg + i), v = 0;
        if (r == 0xD0) v = 0x58;
        else if (r >= 0x88 && r < 0x88 + 24) v = CALIB[r - 0x88];
        else if (r == 0xF3) v = now < u->conv_end ? 0x08 : 0;
        else if (r == 0xF4) v = u->ctrl_meas;
        else if (r == 0xF5) v = u->bmp_cfg;
        else if (r >= 0xF7 && r <= 0xFC) {
            if (r == 0xF7 && reg <= 0xF7) {
                if ((u->ctrl_meas & 3) == 3 || now >= u->conv_end) bmp_latch(u);
                if ((u->ctrl_meas & 3) != 3 && now >= u->conv_end) u->ctrl_meas &= ~3;   /* forced -> sleep */
            }
            int32_t ap = adc_for(u->last_p ? u->last_p : P0), at = 519888;
            uint8_t d[6] = { (uint8_t)(ap >> 12), (uint8_t)(ap >> 4), (uint8_t)((ap & 15) << 4),
                             (uint8_t)(at >> 12), (uint8_t)(at >> 4), (uint8_t)((at & 15) << 4) };
            v = d[r - 0xF7];
        }
        buf[i] = v;
    }
}

static void w_gpio_set(int k, int pin, int level)
{
    if (pin == PIN_SERVO_EN && U[k].servo_en != level) {
        U[k].servo_en = level;
        event(k, "servo_power", "%d", level);
    }
}

static int w_gpio_get(int k, int pin)
{
    if (pin == PIN_CHG) return U[k].charging ? 0 : 1;
    if (pin == PIN_VBUS) return U[k].usb ? 1 : 0;
    return 0;
}

static void w_pwm(int k, int gpio, double frac, double freq)
{
    unit_t *u = &U[k];
    if (gpio == PIN_PWM) u->pulse_us = freq > 0 ? frac * 1e6 / freq : 0;
    else if (gpio == PIN_LED_R) u->led[0] = 1 - frac;      /* LED cathode: low = on */
    else if (gpio == PIN_LED_G) u->led[1] = 1 - frac;
    else if (gpio == PIN_LED_B) u->led[2] = 1 - frac;
}

static int w_adc_mv(int k, int ch) { return ch == 0 ? (int)(soc_to_v(U[k].soc) * 1000 / 2) : 0; }

static void w_radio_on(int k, bool on, int ch) { U[k].radio_on = on; U[k].channel = ch; }

static void w_radio_send(int k, const uint8_t *d, int n)
{
    double t = now / 1e6;
    if (t >= out_from && t < out_to) return;                       /* out of range */
    event(k, "tx", "%d", n >= 4 ? d[3] : -1);
    for (int j = 0; j < NU; j++) {
        unit_t *v = &U[j];
        if (j == k || v->asleep || !v->radio_on || v->channel != U[k].channel || rnd() < loss || v->nrx >= 64)
            continue;
        int64_t at = now + 1500 + (int64_t)(rnd() * 1000);            /* ESP-NOW: ~2 ms */
        v->rx[v->nrx].t = at; v->rx[v->nrx].n = n; memcpy(v->rx[v->nrx].b, d, n); v->nrx++;
        if (v->waiting && v->radio_wait && v->wake > at) v->wake = at;
    }
}

static int w_radio_take(int k, uint8_t *buf, int max)
{
    unit_t *u = &U[k];
    for (int i = 0; i < u->nrx; i++)
        if (u->rx[i].t <= now) {
            int n = u->rx[i].n < max ? u->rx[i].n : max;
            memcpy(buf, u->rx[i].b, n);
            memmove(&u->rx[i], &u->rx[i + 1], (u->nrx - i - 1) * sizeof u->rx[0]);
            u->nrx--;
            return n;
        }
    return -1;
}

static void w_deep_sleep(int k, int64_t us)
{
    unit_t *u = &U[k];
    account(u, 0);
    u->asleep = 1; u->servo_en = 0; u->pulse_us = 0; u->led[0] = u->led[1] = u->led[2] = 0; u->nrx = 0;
    u->sleeps++;
    event(k, "sleep", "%lld", (long long)us);
}

static void w_light_sleep(int k, bool on)
{
    unit_t *u = &U[k];
    account(u, 0);
    u->lightsleep = on;
    if (!on) u->mah += 20.0 * 0.0012 / 3600.0;          /* wake-up + I2C: ~1.2 ms at 20 mA */
}

static const world_api_t API = { w_now, w_wait_until, w_wait_radio, w_log, w_i2c_present, w_i2c_write, w_i2c_read,
                                 w_gpio_set, w_gpio_get, w_pwm, w_adc_mv, w_radio_on, w_radio_send, w_radio_take,
                                 w_deep_sleep, w_light_sleep };

static void *thread_main(void *arg)
{
    int k = (int)(intptr_t)arg;
    pthread_mutex_lock(&M);
    U[k].wake = (int64_t)(U[k].start_s * 1e6);
    registered++;
    pthread_cond_signal(&main_cv);
    U[k].waiting = 1;
    while (!U[k].granted) pthread_cond_wait(&U[k].cv, &M);
    pthread_mutex_unlock(&M);
    event(k, "boot", "power on");
    if (k == 0) uA_sim_unit_run(&API, 0); else uB_sim_unit_run(&API, 1);
    return NULL;
}

/* ---------------- scenario parsing ---------------- */
static void parse(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(1); }
    char line[512];
    for (int k = 0; k < NU; k++) {
        U[k].sensor = 1; U[k].vbat_soc = 0.8; U[k].held_from = 0; U[k].held_to = 1e9; U[k].t_air = 22;
        U[k].agent_force = 15; U[k].agent_rounds = 3; U[k].channel = 1;
    }
    while (fgets(line, sizeof line, f)) {
        char *h = strchr(line, '#');
        if (h) *h = 0;
        char a[32], b[32];
        double x, y, z;
        int k;
        if (sscanf(line, "duration %lf", &x) == 1) T_end = x;
        else if (sscanf(line, "seed %u", &seed) == 1) {}
        else if (sscanf(line, "loss %lf", &x) == 1) loss = x;
        else if (sscanf(line, "out_of_range %lf %lf", &x, &y) == 2) { out_from = x; out_to = y; }
        else if (sscanf(line, "%31s %31s", a, b) == 2 && (!strcmp(a, "A") || !strcmp(a, "B"))) {
            k = a[0] - 'A';
            unit_t *u = &U[k];
            char *p = line + 1;
            if (sscanf(p, " start %lf", &x) == 1) u->start_s = x;
            else if (sscanf(p, " held %lf %lf", &x, &y) == 2) { u->held_from = x; u->held_to = y; }
            else if (sscanf(p, " usb %d", &u->usb) == 1) {}
            else if (sscanf(p, " charging %d", &u->charging) == 1) {}
            else if (sscanf(p, " sensor %d", &u->sensor) == 1) {}
            else if (sscanf(p, " battery %lf", &x) == 1) u->vbat_soc = x;
            else if (sscanf(p, " grip %lf", &x) == 1) u->grip_n = x;
            else if (sscanf(p, " tremor %lf", &x) == 1) u->tremor_n = x;
            else if (sscanf(p, " squeeze %lf %lf %lf", &x, &y, &z) == 3) add_squeeze(u, x, y, z);
            else if (sscanf(p, " parent %lf %lf %d", &x, &y, &u->agent_rounds) == 3) { u->agent = AG_PARENT; u->agent_start = x; u->agent_force = y; }
            else if (sscanf(p, " child %lf", &x) == 1) { u->agent = AG_CHILD; u->agent_force = x; }
        }
    }
    fclose(f);
    for (int k = 0; k < NU; k++) U[k].soc = U[k].vbat_soc;
}

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: sim scenario.txt out_prefix\n"); return 2; }
    char p[512];
    snprintf(p, sizeof p, "%s.events.csv", argv[2]); ev = fopen(p, "w");
    snprintf(p, sizeof p, "%s.log", argv[2]); lg = fopen(p, "w");
    fprintf(ev, "t,unit,kind,data\n");
    parse(argv[1]);
    pthread_t th[NU];
    pthread_mutex_lock(&M);
    for (int k = 0; k < NU; k++) {
        pthread_cond_init(&U[k].cv, NULL);
        pthread_create(&th[k], NULL, thread_main, (void *)(intptr_t)k);
    }
    while (registered < NU) pthread_cond_wait(&main_cv, &M);
    int64_t next_tick = 0, end = (int64_t)(T_end * 1e6);
    while (now < end) {
        int best = -1;
        for (int k = 0; k < NU; k++)
            if (U[k].waiting && (best < 0 || U[k].wake < U[best].wake)) best = k;
        if (best < 0 || next_tick <= U[best].wake) {
            now = next_tick;
            next_tick += TICK_US;
            physics_step();
            continue;
        }
        unit_t *u = &U[best];
        if (u->wake > now) now = u->wake;
        if (u->asleep) {
            u->asleep = 0; u->boots++;
            u->last_power_t = now;
            event(best, "wake", "");
        }
        u->waiting = 0;
        u->granted = 1;
        running = best;
        pthread_cond_signal(&u->cv);
        while (running >= 0) pthread_cond_wait(&main_cv, &M);
    }
    for (int k = 0; k < NU; k++) {
        account(&U[k], 0);
        printf("unit %s: %.2f mAh used (%.2f mA average), battery %.0f%% -> %.0f%%, %d sleeps\n", NAME[k],
               U[k].mah, U[k].mah / (T_end / 3600.0), U[k].vbat_soc * 100, U[k].soc * 100, U[k].sleeps);
        fprintf(ev, "%.3f,%s,summary,%.4f,%.4f,%.4f\n", T_end, NAME[k], U[k].mah, U[k].vbat_soc, U[k].soc);
    }
    fflush(ev); fflush(lg); fflush(stdout);
    _exit(0);
}
