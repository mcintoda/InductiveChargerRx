// The last bath, sample by sample (every 2 s while wet), for tuning from real baths with a sealed device:
// saved to flash before each sleep, downloadable as CSV from the settings page and printed by the bench console.
#pragma once
#include <stdbool.h>
#include <stddef.h>

#define BATHLOG_N 512                      // 17 min at 2 s; older samples roll off

void bathlog_begin(bool new_bath, double now_s);   // new bath: start empty; otherwise continue the saved one
void bathlog_add(double now_s, float level_mm, float temp_c, int top_pad, bool wet, bool alarm);
void bathlog_save(void);                            // no-op if nothing was added since the last save
// CSV of the saved log, written in pieces: emit(text, len, ctx) is called repeatedly. Returns the sample count.
int bathlog_csv(void (*emit)(const char *text, size_t len, void *ctx), void *ctx);
