idf_component_register(
    SRCS "main.c" "grip.c" "shaper.c" "turn.c" "proto.c" "bmp280.c" "bmp280_comp.c" "hw.c" "radio.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_driver_i2c esp_driver_ledc esp_driver_gpio esp_adc esp_wifi esp_netif
                  esp_event esp_timer nvs_flash)
