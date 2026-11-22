// Seal-leak detection from the humidity INSIDE the case (pure logic, host-testable).
// A sealed case holds a fixed amount of water vapour: absolute humidity stays flat while temperature (and so
// relative humidity) swings with the bath. A leak adds water, so absolute humidity climbs and RH heads to 100 %.
#pragma once
#include <stdbool.h>

typedef struct {
    bool valid;
    float base_ah;            // g/m3, slow running minimum (the case's own vapour content)
    float base_t;             // when base_ah was last updated (s)
    int high;                 // consecutive readings above the threshold
    float alert_s;            // last alert (s), 0 = never
} caseair_t;

#define CASEAIR_RISE_GM3 3.0f        // above the baseline ...
#define CASEAIR_RH_WET 90.0f         // ... or RH this high
#define CASEAIR_CONFIRM 3            // consecutive readings
#define CASEAIR_DRIFT_GM3_DAY 0.5f   // baseline may creep up this much per day (desiccant saturating, etc.)
#define CASEAIR_REPEAT_S (24 * 3600.0f)

float caseair_abs_humidity(float temp_c, float rh);    // g/m3
// returns true when a "moisture inside" warning should be sent now
bool caseair_update(caseair_t *s, float temp_c, float rh, float now_s);
