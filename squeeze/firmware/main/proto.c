#include "proto.h"

uint32_t sq_pair_id(const char *secret)
{
    uint32_t h = 2166136261u;
    for (const unsigned char *p = (const unsigned char *)secret; *p; p++) {
        h ^= *p;
        h *= 16777619u;
    }
    return h;
}

size_t sq_pack(uint8_t out[SQ_PKT_LEN], uint32_t pair_id, const sq_msg_t *m)
{
    out[0] = 'S';
    out[1] = 'Q';
    out[2] = SQ_VERSION;
    out[3] = m->type;
    out[4] = (uint8_t)pair_id;
    out[5] = (uint8_t)(pair_id >> 8);
    out[6] = (uint8_t)(pair_id >> 16);
    out[7] = (uint8_t)(pair_id >> 24);
    out[8] = (uint8_t)m->seq;
    out[9] = (uint8_t)(m->seq >> 8);
    out[10] = m->level;
    out[11] = m->flags;
    return SQ_PKT_LEN;
}

bool sq_unpack(const uint8_t *b, size_t len, uint32_t pair_id, sq_msg_t *m)
{
    if (len != SQ_PKT_LEN || b[0] != 'S' || b[1] != 'Q' || b[2] != SQ_VERSION)
        return false;
    uint32_t id = (uint32_t)b[4] | (uint32_t)b[5] << 8 | (uint32_t)b[6] << 16 | (uint32_t)b[7] << 24;
    if (id != pair_id || b[3] < SQ_LEVEL || b[3] > SQ_BYE)
        return false;
    m->type = b[3];
    m->seq = (uint16_t)(b[8] | b[9] << 8);
    m->level = b[10];
    m->flags = b[11];
    return true;
}

bool sq_seq_accept(uint16_t seq, uint16_t last)
{
    uint16_t ahead = (uint16_t)(seq - last);
    return (ahead != 0 && ahead < 0x8000u) || (uint16_t)(last - seq) > 512u;
}
