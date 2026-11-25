/* turn: who is squeezing right now (half duplex).
 *
 * A unit cannot tell its holder squeezing from its own plates pushing into a
 * still hand: both raise the pressure. So the pair takes turns:
 *   IDLE   -> TALK   when the holder squeezes (local wins a tie)
 *   IDLE   -> LISTEN when the partner's squeeze arrives
 *   TALK   -> IDLE   tail_ms after the holder lets go (zeros are sent in the tail)
 *   LISTEN -> IDLE   tail_ms after the partner let go AND the plates are back at rest
 * While LISTENing the holder's pressure is ignored (mask).
 *
 * Pure C, host-tested.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef enum { TURN_IDLE, TURN_TALK, TURN_LISTEN } turn_state_t;

typedef struct {
    turn_state_t st;
    uint32_t tail_ms;
    uint32_t quiet_since_ms;
    bool quiet;
} turn_t;

typedef struct {
    bool send; /* stream this unit's level to the partner */
    bool play; /* drive the plates from the partner's level */
    bool mask; /* ignore this unit's pressure */
} turn_out_t;

void turn_init(turn_t *t, uint32_t tail_ms);
turn_out_t turn_update(turn_t *t, bool local_active, bool remote_active, bool plates_busy, uint32_t now_ms);
