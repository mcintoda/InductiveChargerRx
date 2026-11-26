/* sdkconfig.h for the simulator: the Kconfig defaults (firmware/main/Kconfig.projbuild) for one role */
#pragma once
#define CONFIG_IDF_TARGET "esp32c3"
#define CONFIG_FREERTOS_HZ 1000
#define CONFIG_SQZ_ROLE_@ROLE@ 1
#define CONFIG_SQZ_PAIR_SECRET "change-me-before-flashing"
#define CONFIG_SQZ_CHANNEL 1
#define CONFIG_SQZ_SWELL_DEG @SWELL@
#define CONFIG_SQZ_SERVO_REST_DEG 45
#define CONFIG_SQZ_SERVO_MIN_US 500
#define CONFIG_SQZ_SERVO_MAX_US 2400
#define CONFIG_SQZ_COLOR_PARENT 0x0080FF
#define CONFIG_SQZ_COLOR_CHILD @CHILD@
#define CONFIG_SQZ_SLEEP_PERIOD_MS @SLEEP@
#define CONFIG_SQZ_SESSION_IDLE_S 90
#define CONFIG_SQZ_DEEP_PERIOD_MS @DEEP@
#define CONFIG_SQZ_RECENT_S 600
#define CONFIG_SQZ_DUPLEX 1
