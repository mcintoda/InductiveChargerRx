#include "radio.h"

#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

static const char *TAG = "radio";
static const uint8_t BCAST[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };
static QueueHandle_t s_rx;
static uint32_t s_pair;
static uint16_t s_seq;
static uint16_t s_last_seq;
static bool s_have_seq;

static void on_recv(const esp_now_recv_info_t *info, const uint8_t *data, int len)
{
    sq_msg_t m;
    (void)info;
    if (len < 0 || !sq_unpack(data, (size_t)len, s_pair, &m))
        return;
    xQueueSend(s_rx, &m, 0); /* Wi-Fi task context, not an ISR */
}

void radio_start(void)
{
    s_pair = sq_pair_id(CONFIG_SQZ_PAIR_SECRET);
    s_rx = xQueueCreate(16, sizeof(sq_msg_t));

    esp_err_t err = nvs_flash_init(); /* Wi-Fi keeps its RF calibration here */
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
#if CONFIG_SQZ_LONG_RANGE
    ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G |
                                                         WIFI_PROTOCOL_11N | WIFI_PROTOCOL_LR));
#endif
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_channel(CONFIG_SQZ_CHANNEL, WIFI_SECOND_CHAN_NONE));
    esp_wifi_set_ps(WIFI_PS_NONE); /* lowest latency while awake */

    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(on_recv));
    esp_now_peer_info_t peer = { .channel = 0, .ifidx = WIFI_IF_STA, .encrypt = false };
    memcpy(peer.peer_addr, BCAST, 6);
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));

    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    ESP_LOGI(TAG, "ESP-NOW on channel %d, pair %08lx, me %02x:%02x:%02x:%02x:%02x:%02x",
             CONFIG_SQZ_CHANNEL, (unsigned long)s_pair, mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

void radio_send(uint8_t type, uint8_t level, uint8_t flags)
{
    uint8_t b[SQ_PKT_LEN];
    sq_msg_t m = { .type = type, .seq = ++s_seq, .level = level, .flags = flags };
    sq_pack(b, s_pair, &m);
    esp_now_send(BCAST, b, sizeof b); /* broadcast: no ACK, no retries; 50 Hz covers a lost frame */
}

bool radio_recv(sq_msg_t *m, int timeout_ms)
{
    while (xQueueReceive(s_rx, m, pdMS_TO_TICKS(timeout_ms)) == pdTRUE) {
        if (m->type == SQ_WAKE || m->type == SQ_AWAKE) {
            s_have_seq = false; /* the partner just booted */
        }
        if (s_have_seq && !sq_seq_accept(m->seq, s_last_seq)) {
            timeout_ms = 0;
            continue;
        }
        s_have_seq = true;
        s_last_seq = m->seq;
        return true;
    }
    return false;
}
