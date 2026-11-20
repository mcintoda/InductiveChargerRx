idf_component_register(
    SRCS "main.c" "sensor_bus.c" "fdc1004.c" "fdclevel.c" "level.c" "rate.c" "policy.c" "sense_touch.c" "tmp117.c" "power.c" "settings.c" "net.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_adc esp_wifi esp_netif esp_event nvs_flash esp_http_client esp_http_server
             esp-tls app_update esp_pm esp_timer)
