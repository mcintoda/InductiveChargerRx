#include "factory.h"

#include <string.h>

#include "esp_partition.h"
#include "sdkconfig.h"

#define FCTRY_SUBTYPE 0x40
#define FCTRY_MAGIC "brim-fctry-1\n"

bool factory_get(const char *key, char *out, size_t n)
{
    static char buf[256];
    static bool loaded, ok;
    if (!loaded) {
        loaded = true;
        const esp_partition_t *p = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, (esp_partition_subtype_t)FCTRY_SUBTYPE, "fctry");
        if (p && esp_partition_read(p, 0, buf, sizeof(buf) - 1) == ESP_OK) {
            buf[sizeof(buf) - 1] = 0;
            char *end = memchr(buf, 0xFF, sizeof(buf) - 1);      // erased flash ends the text
            if (end) *end = 0;
            ok = !strncmp(buf, FCTRY_MAGIC, strlen(FCTRY_MAGIC));
        }
    }
    if (!ok || n == 0) return false;
    size_t kl = strlen(key);
    for (const char *l = buf + strlen(FCTRY_MAGIC); *l; ) {
        const char *nl = strchr(l, '\n');
        size_t ll = nl ? (size_t)(nl - l) : strlen(l);
        if (ll > kl && l[kl] == '=' && !strncmp(l, key, kl)) {
            size_t vl = ll - kl - 1;
            if (vl >= n) return false;
            memcpy(out, l + kl + 1, vl);
            out[vl] = 0;
            return true;
        }
        if (!nl) break;
        l = nl + 1;
    }
    return false;
}
