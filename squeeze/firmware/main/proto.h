/* proto: the 12-byte ESP-NOW frame both units broadcast.
 *
 *   0  'S'   1 'Q'   2 version (1)   3 type
 *   4..7  pair id (little endian): FNV-1a of the pair secret, so other
 *         squeeze pairs nearby are ignored
 *   8..9  sequence number (little endian)
 *   10    level 0..255 (LEVEL frames)
 *   11    flags
 *
 * Pure C, host-tested.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SQ_PKT_LEN 12
#define SQ_VERSION 1

enum {
    SQ_LEVEL = 1,     /* live squeeze level, 50 per second while squeezing */
    SQ_HEARTBEAT = 2, /* "I'm awake", once a second */
    SQ_WAKE = 3,      /* "wake up", every 20 ms until the partner answers */
    SQ_AWAKE = 4,     /* answer to WAKE */
    SQ_BYE = 5,       /* going to sleep */
};

#define SQ_FLAG_CHARGING 0x01
#define SQ_FLAG_LOW_BATT 0x02

typedef struct {
    uint8_t type;
    uint16_t seq;
    uint8_t level;
    uint8_t flags;
} sq_msg_t;

uint32_t sq_pair_id(const char *secret);
size_t sq_pack(uint8_t out[SQ_PKT_LEN], uint32_t pair_id, const sq_msg_t *m);
/* false for anything that is not a valid frame of this pair */
bool sq_unpack(const uint8_t *buf, size_t len, uint32_t pair_id, sq_msg_t *m);
/* Accept seq after last: newer, or so far behind that the partner restarted. */
bool sq_seq_accept(uint16_t seq, uint16_t last);
