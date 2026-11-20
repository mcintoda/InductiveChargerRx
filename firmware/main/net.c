#include "net.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

static const char *TAG = "net";
static EventGroupHandle_t s_ev;
#define EV_GOT_IP BIT0
#define EV_SAVED BIT1
static httpd_handle_t s_httpd;
static settings_t *s_settings;
static const net_status_t *s_status;
static bool s_saved, s_ota_done, s_wifi_started;
static esp_netif_t *s_sta, *s_ap;

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) xEventGroupSetBits(s_ev, EV_GOT_IP);
}

esp_err_t net_init(void)
{
    s_ev = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL));
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    return esp_wifi_init(&cfg);
}

bool net_wifi_connect(const settings_t *s, int timeout_ms)
{
    if (!s_sta) s_sta = esp_netif_create_default_wifi_sta();
    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, s->ssid, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, s->pass, sizeof(wc.sta.password));
    wc.sta.threshold.authmode = s->pass[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_config(WIFI_IF_STA, &wc);
    esp_wifi_set_ps(WIFI_PS_MIN_MODEM);       // modem sleep between DTIM beacons
    xEventGroupClearBits(s_ev, EV_GOT_IP);
    if (!s_wifi_started) { esp_wifi_start(); s_wifi_started = true; }
    esp_wifi_connect();
    EventBits_t b = xEventGroupWaitBits(s_ev, EV_GOT_IP, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms));
    if (!(b & EV_GOT_IP)) ESP_LOGW(TAG, "Wi-Fi connect timed out");
    return b & EV_GOT_IP;
}

void net_wifi_stop(void)
{
    if (s_wifi_started) { esp_wifi_disconnect(); esp_wifi_stop(); s_wifi_started = false; }
}

esp_err_t net_ntfy(const settings_t *s, const char *title, const char *msg, int priority, const char *tags)
{
    char url[128], prio[4];
    snprintf(url, sizeof(url), "https://%s/%s", s->ntfy_host, s->topic);
    snprintf(prio, sizeof(prio), "%d", priority);
    esp_http_client_config_t cfg = {.url = url, .method = HTTP_METHOD_POST, .timeout_ms = 8000,
                                    .crt_bundle_attach = esp_crt_bundle_attach};
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    esp_http_client_set_header(c, "Title", title);
    esp_http_client_set_header(c, "Priority", prio);
    if (tags && tags[0]) esp_http_client_set_header(c, "Tags", tags);
    esp_http_client_set_post_field(c, msg, strlen(msg));
    esp_err_t err = esp_http_client_perform(c);
    int code = esp_http_client_get_status_code(c);
    esp_http_client_cleanup(c);
    if (err == ESP_OK && code != 200) err = ESP_FAIL;
    ESP_LOGI(TAG, "ntfy '%s' -> %s (%d)", title, esp_err_to_name(err), code);
    return err;
}

// ---------------- web pages ----------------
static void url_decode(char *s)
{
    char *o = s;
    for (; *s; s++, o++) {
        if (*s == '+') *o = ' ';
        else if (*s == '%' && isxdigit((unsigned char)s[1]) && isxdigit((unsigned char)s[2])) {
            char h[3] = {s[1], s[2], 0};
            *o = (char)strtol(h, NULL, 16);
            s += 2;
        } else *o = *s;
    }
    *o = 0;
}

static bool form_get(const char *body, const char *key, char *out, size_t n)
{
    if (httpd_query_key_value(body, key, out, n) != ESP_OK) return false;
    url_decode(out);
    return true;
}

static const char *PAGE_HEAD =
    "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>brim</title>"
    "<style>body{font-family:system-ui;margin:24px;max-width:420px;color:#2F3A45;background:#E8ECEA}"
    "label{display:block;margin-top:14px;font-size:14px}input,select{width:100%;padding:8px;font-size:16px}"
    "button{margin-top:18px;padding:10px 16px;font-size:16px;background:#61798A;color:#fff;border:0;border-radius:6px}"
    "code{background:#fff;padding:2px 6px;border-radius:4px}</style><h2>brim</h2>";

static esp_err_t page_root(httpd_req_t *req)
{
    char buf[3000];
    const settings_t *s = s_settings;
    int n = snprintf(buf, sizeof(buf), "%s", PAGE_HEAD);
    if (s_status)
        n += snprintf(buf + n, sizeof(buf) - n, "<p>Battery %d %% %s &middot; water %s</p>", s_status->battery_pct,
                      s_status->charging ? "(charging)" : "", isnan(s_status->temp_c) ? "--" : "measured");
    n += snprintf(buf + n, sizeof(buf) - n,
                  "<form method=post action=/save>"
                  "<label>Wi-Fi name<input name=ssid value='%s' required></label>"
                  "<label>Wi-Fi password<input name=pass type=password placeholder='%s'></label>"
                  "<label>Alarm at the top of pad<select name=pad>",
                  s->ssid, s->pass[0] ? "unchanged" : "");
    for (int p = 1; p <= 6; p++)
        n += snprintf(buf + n, sizeof(buf) - n, "<option value=%d%s>%d%s</option>", p, p == s->alarm_pad ? " selected" : "",
                      p, p == 6 ? " (top, default)" : p == 1 ? " (bottom)" : "");
    n += snprintf(buf + n, sizeof(buf) - n,
                  "</select></label><label>Hot-water warning above (&deg;C)<input name=tlim type=number step=0.5 min=30 "
                  "max=50 value=%.1f></label><label><input name=fill type=checkbox style='width:auto'%s> Also tell me when "
                  "a bath starts filling</label><label>ntfy server<input name=host value='%s'></label>"
                  "<label>Level sensing<select name=sense><option value=0%s>Touch (ratiometric)</option>"
                  "<option value=1%s>FDC1004 (default)</option><option value=2%s>Compare: log both, alarm from touch</option>"
                  "</select></label>"
                  "<p>Notifications go to topic <code>%s</code>. In the ntfy app tap + and subscribe to it.</p>"
                  "<button>Save</button></form>",
                  s->temp_limit_c, s->notify_filling ? " checked" : "", s->ntfy_host,
                  s->sense_mode == SENSE_TOUCH ? " selected" : "", s->sense_mode == SENSE_FDC ? " selected" : "",
                  s->sense_mode == SENSE_COMPARE ? " selected" : "", s->topic);
    if (s_status)
        n += snprintf(buf + n, sizeof(buf) - n,
                      "<h3>Firmware update</h3><form method=post action=/update enctype=application/octet-stream "
                      "onsubmit=\"event.preventDefault();fetch('/update',{method:'POST',body:this.f.files[0]})"
                      ".then(r=>r.text()).then(t=>document.body.innerHTML+='<p>'+t+'</p>')\">"
                      "<input name=f type=file accept=.bin><button>Upload</button></form>");
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, buf, n);
}

static esp_err_t page_save(httpd_req_t *req)
{
    char body[512] = {0}, v[96];
    int len = httpd_req_recv(req, body, sizeof(body) - 1);
    if (len <= 0) return httpd_resp_send_500(req);
    settings_t *s = s_settings;
    if (form_get(body, "ssid", v, sizeof(v))) strlcpy(s->ssid, v, sizeof(s->ssid));
    if (form_get(body, "pass", v, sizeof(v)) && v[0]) strlcpy(s->pass, v, sizeof(s->pass));   // blank = keep
    if (form_get(body, "host", v, sizeof(v)) && v[0]) strlcpy(s->ntfy_host, v, sizeof(s->ntfy_host));
    if (form_get(body, "pad", v, sizeof(v))) { int p = atoi(v); if (p >= 1 && p <= 6) s->alarm_pad = p; }
    if (form_get(body, "tlim", v, sizeof(v))) { float t = strtof(v, NULL); if (t >= 30 && t <= 50) s->temp_limit_c = t; }
    s->notify_filling = form_get(body, "fill", v, sizeof(v));
    if (form_get(body, "sense", v, sizeof(v))) { int m = atoi(v); if (m >= SENSE_TOUCH && m <= SENSE_COMPARE) s->sense_mode = m; }
    if (!s->topic[0]) settings_new_topic(s->topic, sizeof(s->topic));
    settings_save(s);
    s_saved = true;
    xEventGroupSetBits(s_ev, EV_SAVED);
    char resp[800];
    int n = snprintf(resp, sizeof(resp), "%s<p>Saved. brim will now join <b>%s</b>.</p><p>Subscribe to <code>%s</code> "
                     "in the ntfy app to get alerts.</p>", PAGE_HEAD, s->ssid, s->topic);
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, resp, n);
}

static esp_err_t page_update(httpd_req_t *req)
{
    const esp_partition_t *part = esp_ota_get_next_update_partition(NULL);
    esp_ota_handle_t h;
    if (!part || esp_ota_begin(part, OTA_WITH_SEQUENTIAL_WRITES, &h) != ESP_OK) return httpd_resp_send_500(req);
    char buf[1024];
    int remaining = req->content_len;
    while (remaining > 0) {
        int r = httpd_req_recv(req, buf, remaining < (int)sizeof(buf) ? remaining : (int)sizeof(buf));
        if (r == HTTPD_SOCK_ERR_TIMEOUT) continue;
        if (r <= 0 || esp_ota_write(h, buf, r) != ESP_OK) { esp_ota_abort(h); return httpd_resp_send_500(req); }
        remaining -= r;
    }
    if (esp_ota_end(h) != ESP_OK || esp_ota_set_boot_partition(part) != ESP_OK) return httpd_resp_send_500(req);
    s_ota_done = true;
    return httpd_resp_sendstr(req, "Update written. brim restarts in a moment.");
}

static esp_err_t start_httpd(void)
{
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.stack_size = 8192;
    if (httpd_start(&s_httpd, &cfg) != ESP_OK) return ESP_FAIL;
    httpd_uri_t root = {.uri = "/", .method = HTTP_GET, .handler = page_root};
    httpd_uri_t save = {.uri = "/save", .method = HTTP_POST, .handler = page_save};
    httpd_register_uri_handler(s_httpd, &root);
    httpd_register_uri_handler(s_httpd, &save);
    if (s_status) {
        httpd_uri_t upd = {.uri = "/update", .method = HTTP_POST, .handler = page_update};
        httpd_register_uri_handler(s_httpd, &upd);
    }
    return ESP_OK;
}

bool net_provision(settings_t *s, int timeout_ms)
{
    s_settings = s;
    s_status = NULL;
    if (!s->topic[0]) settings_new_topic(s->topic, sizeof(s->topic));
    if (!s_ap) s_ap = esp_netif_create_default_wifi_ap();
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP);
    wifi_config_t ap = {.ap = {.channel = 6, .max_connection = 2, .authmode = WIFI_AUTH_OPEN}};
    int l = snprintf((char *)ap.ap.ssid, sizeof(ap.ap.ssid), "brim-setup-%02X%02X", mac[4], mac[5]);
    ap.ap.ssid_len = l;
    esp_wifi_set_mode(WIFI_MODE_AP);
    esp_wifi_set_config(WIFI_IF_AP, &ap);
    esp_wifi_start();
    s_wifi_started = true;
    start_httpd();
    ESP_LOGI(TAG, "setup: join Wi-Fi '%s' and open http://192.168.4.1", ap.ap.ssid);
    EventBits_t b = xEventGroupWaitBits(s_ev, EV_SAVED, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms));
    vTaskDelay(pdMS_TO_TICKS(1500));   // let the confirmation page go out
    httpd_stop(s_httpd);
    s_httpd = NULL;
    net_wifi_stop();
    return b & EV_SAVED;
}

esp_err_t net_web_start(settings_t *s, const net_status_t *status)
{
    s_settings = s;
    s_status = status;
    s_saved = s_ota_done = false;
    return start_httpd();
}

void net_web_stop(void)
{
    if (s_httpd) { httpd_stop(s_httpd); s_httpd = NULL; }
}

bool net_web_saved(void) { return s_saved; }
bool net_ota_done(void) { return s_ota_done; }
