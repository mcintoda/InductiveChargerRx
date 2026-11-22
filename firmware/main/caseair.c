#include "caseair.h"

#include <math.h>

float caseair_abs_humidity(float temp_c, float rh)
{
    float es = 6.112f * expf(17.62f * temp_c / (243.12f + temp_c));   // saturation vapour pressure, hPa (Magnus)
    return 216.7f * (rh / 100.0f * es) / (273.15f + temp_c);
}

bool caseair_update(caseair_t *s, float temp_c, float rh, float now_s)
{
    float ah = caseair_abs_humidity(temp_c, rh);
    if (!s->valid) {
        s->valid = true; s->base_ah = ah; s->base_t = now_s; s->high = 0; s->alert_s = 0;
        return false;
    }
    // baseline: follows the minimum at once, creeps up at most CASEAIR_DRIFT_GM3_DAY
    float creep = CASEAIR_DRIFT_GM3_DAY * (now_s - s->base_t) / 86400.0f;
    if (ah < s->base_ah) s->base_ah = ah;
    else s->base_ah = fminf(ah, s->base_ah + creep);
    s->base_t = now_s;
    bool wet = ah > s->base_ah + CASEAIR_RISE_GM3 || rh > CASEAIR_RH_WET;
    s->high = wet ? s->high + 1 : 0;
    if (s->high >= CASEAIR_CONFIRM && (s->alert_s == 0 || now_s - s->alert_s >= CASEAIR_REPEAT_S)) {
        s->alert_s = now_s;
        return true;
    }
    return false;
}
