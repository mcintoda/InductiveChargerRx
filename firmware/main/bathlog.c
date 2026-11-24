#include "bathlog.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_attr.h"
#include "settings.h"

typedef struct {
    uint16_t t2;      // seconds since the bath started / 2
    int16_t level10;  // mm x 10
    int16_t temp100;  // C x 100, INT16_MIN = no reading
    uint8_t top;      // highest full pad
    uint8_t flags;    // bit 0 wet, bit 1 alarm active
} sample_t;

typedef struct {
    uint16_t n;
    sample_t s[BATHLOG_N];
} log_t;

static log_t s_log;                         // RAM copy while awake (4 kB: too big for RTC memory)
static RTC_DATA_ATTR double s_t0;            // bath start, survives the in-bath sleeps
static bool s_dirty;

void bathlog_begin(bool new_bath, double now_s)
{
    if (new_bath || !store_load("bathlog", &s_log, sizeof(s_log))) {
        memset(&s_log, 0, sizeof(s_log));
        s_t0 = now_s;
        s_dirty = true;
    }
}

void bathlog_add(double now_s, float level_mm, float temp_c, int top_pad, bool wet, bool alarm)
{
    if (s_log.n == BATHLOG_N) {                                  // full: drop the oldest
        memmove(&s_log.s[0], &s_log.s[1], sizeof(sample_t) * (BATHLOG_N - 1));
        s_log.n--;
    }
    double dt = (now_s - s_t0) / 2;
    s_log.s[s_log.n++] = (sample_t){
        .t2 = (uint16_t)(dt < 0 ? 0 : dt > 65535 ? 65535 : dt),
        .level10 = (int16_t)lroundf(level_mm * 10),
        .temp100 = isnan(temp_c) ? INT16_MIN : (int16_t)lroundf(temp_c * 100),
        .top = (uint8_t)top_pad,
        .flags = (uint8_t)((wet ? 1 : 0) | (alarm ? 2 : 0)),
    };
    s_dirty = true;
}

void bathlog_save(void)
{
    if (s_dirty && store_save("bathlog", &s_log, sizeof(s_log)) == ESP_OK) s_dirty = false;
}

int bathlog_csv(void (*emit)(const char *text, size_t len, void *ctx), void *ctx)
{
    static log_t saved;                                          // the httpd / console task, one at a time
    if (!store_load("bathlog", &saved, sizeof(saved))) saved.n = 0;
    static const char hdr[] = "t_s,level_mm,temp_c,top_pad,wet,alarm\n";
    emit(hdr, sizeof(hdr) - 1, ctx);
    char line[64];
    for (int i = 0; i < saved.n; i++) {
        const sample_t *p = &saved.s[i];
        char temp[12] = "";
        if (p->temp100 != INT16_MIN) snprintf(temp, sizeof(temp), "%.2f", p->temp100 / 100.0);
        int l = snprintf(line, sizeof(line), "%u,%.1f,%s,%u,%u,%u\n", p->t2 * 2u, p->level10 / 10.0, temp, p->top,
                         p->flags & 1u, (p->flags >> 1) & 1u);
        emit(line, (size_t)l, ctx);
    }
    return saved.n;
}
