// Piezo disc bonded inside the plug, driven in antiphase from GPIO16 / GPIO17 (6.6 V peak-to-peak).
#pragma once

void buzzer_tone(int hz, int ms);         // blocking
void buzzer_alarm(void);                  // 3 x (3 short beeps): the local "bath full" alarm, ~3 s
void buzzer_chirp(void);                  // one short confirmation beep
