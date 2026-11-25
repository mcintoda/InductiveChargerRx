/* ESP-NOW link to the partner unit: broadcast frames on a fixed channel,
 * filtered by the pair id (proto.h). No router, no pairing step. */
#pragma once
#include <stdbool.h>
#include "proto.h"

void radio_start(void);
void radio_send(uint8_t type, uint8_t level, uint8_t flags);
/* Next valid frame from the partner, waiting up to timeout_ms. */
bool radio_recv(sq_msg_t *m, int timeout_ms);
