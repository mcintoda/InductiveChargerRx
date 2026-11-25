#include "turn.h"

void turn_init(turn_t *t, uint32_t tail_ms)
{
    *t = (turn_t){ .st = TURN_IDLE, .tail_ms = tail_ms };
}

/* Returns true once "busy" has been false for tail_ms. */
static bool finished(turn_t *t, bool busy, uint32_t now)
{
    if (busy) {
        t->quiet = false;
        return false;
    }
    if (!t->quiet) {
        t->quiet = true;
        t->quiet_since_ms = now;
    }
    return (uint32_t)(now - t->quiet_since_ms) >= t->tail_ms;
}

turn_out_t turn_update(turn_t *t, bool local_active, bool remote_active, bool plates_busy, uint32_t now_ms)
{
    switch (t->st) {
    case TURN_IDLE:
        if (local_active) {
            t->st = TURN_TALK;
            t->quiet = false;
        } else if (remote_active) {
            t->st = TURN_LISTEN;
            t->quiet = false;
        }
        break;
    case TURN_TALK:
        if (finished(t, local_active, now_ms))
            t->st = TURN_IDLE;
        break;
    case TURN_LISTEN:
        if (finished(t, remote_active || plates_busy, now_ms))
            t->st = TURN_IDLE;
        break;
    }
    return (turn_out_t){
        .send = t->st == TURN_TALK,
        .play = t->st == TURN_LISTEN,
        .mask = t->st == TURN_LISTEN,
    };
}
