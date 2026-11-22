#include "net.h"

#include "brand_icon.h"

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
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "lwip/sockets.h"

static const char *TAG = "net";
static EventGroupHandle_t s_ev;
#define EV_GOT_IP BIT0
#define EV_SAVED BIT1
static httpd_handle_t s_httpd;
static settings_t *s_settings;
static const net_status_t *s_status;
static bool s_saved, s_ota_done, s_wifi_started;
static esp_netif_t *s_sta, *s_ap;
static volatile bool s_dns_run;
static char s_ip[16];
static char s_key[17];                     // per-session anti-CSRF key, embedded in the page's forms
static volatile int64_t s_unlock_until;    // esp_timer us: settings / firmware changes allowed until then

// ---------------- request hygiene ----------------
static void new_key(void)
{
    for (int i = 0; i < 16; i++) s_key[i] = "0123456789abcdef"[esp_random() & 15];
    s_key[16] = 0;
}

void net_unlock(int seconds) { s_unlock_until = esp_timer_get_time() + (int64_t)seconds * 1000000; }
static bool unlocked(void) { return esp_timer_get_time() < s_unlock_until; }

// Host header must name this device (blocks DNS-rebinding pages from reading or driving it)
static bool host_ok(httpd_req_t *req)
{
    char h[48];
    if (httpd_req_get_hdr_value_str(req, "Host", h, sizeof(h)) != ESP_OK) return false;
    char *colon = strchr(h, ':');
    if (colon) *colon = 0;
    return !strcmp(h, s_status ? s_ip : "192.168.4.1");
}

// HTML-escape for text and attribute values (SSIDs may contain ' " < > &)
static const char *esc(const char *in, char *out, size_t n)
{
    size_t o = 0;
    for (; *in && o + 7 < n; in++) {
        const char *r = NULL;
        switch (*in) {
        case '&': r = "&amp;"; break;
        case '<': r = "&lt;"; break;
        case '>': r = "&gt;"; break;
        case '"': r = "&quot;"; break;
        case '\'': r = "&#39;"; break;
        }
        if (r) { size_t l = strlen(r); memcpy(out + o, r, l); o += l; }
        else out[o++] = *in;
    }
    out[o] = 0;
    return out;
}

// ntfy server: a bare host name with an optional port, nothing that could change the URL's path or user
static bool host_name_ok(const char *h)
{
    if (!h[0] || strlen(h) >= 64) return false;
    for (; *h; h++)
        if (!isalnum((unsigned char)*h) && *h != '.' && *h != '-' && *h != ':') return false;
    return true;
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *e = data;
        snprintf(s_ip, sizeof(s_ip), IPSTR, IP2STR(&e->ip_info.ip));
        xEventGroupSetBits(s_ev, EV_GOT_IP);
    }
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

const char *net_ip(void) { return s_ip; }

esp_err_t net_ntfy(const settings_t *s, const char *title, const char *msg, int priority, const char *tags)
{
    return net_ntfy_click(s, title, msg, priority, tags, NULL);
}

esp_err_t net_ntfy_click(const settings_t *s, const char *title, const char *msg, int priority, const char *tags,
                         const char *click)
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
    if (click && click[0]) esp_http_client_set_header(c, "Click", click);
    esp_http_client_set_post_field(c, msg, strlen(msg));
    esp_err_t err = esp_http_client_perform(c);
    int code = esp_http_client_get_status_code(c);
    esp_http_client_cleanup(c);
    if (err == ESP_OK && code != 200) err = ESP_FAIL;
    ESP_LOGI(TAG, "ntfy '%s' -> %s (%d)", title, esp_err_to_name(err), code);
    return err;
}

// ---------------- web pages ----------------
static esp_err_t page_redirect(httpd_req_t *req, httpd_err_code_t err);
static const char *PAGE_HEAD;

static esp_err_t send_locked(httpd_req_t *req)
{
    httpd_resp_set_status(req, "403 Forbidden");
    httpd_resp_set_type(req, "text/html");
    char resp[1000];
    int n = snprintf(resp, sizeof(resp), "%s<p><b>Locked.</b> Double-tap brim on its charger (it flashes green), "
                     "then press Save or Upload again within 2 minutes.</p><p><a href=/>Back</a></p>", PAGE_HEAD);
    return httpd_resp_send(req, resp, n);
}
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
    "<link rel=icon type=image/svg+xml href=/icon.svg>"
    "<style>body{font-family:system-ui;margin:24px;max-width:420px;color:#2F3A45;background:#E8ECEA}"
    "label{display:block;margin-top:14px;font-size:14px}input,select{width:100%;padding:8px;font-size:16px}"
    "button{margin-top:18px;padding:10px 16px;font-size:16px;background:#61798A;color:#fff;border:0;border-radius:6px}"
    "code{background:#fff;padding:2px 6px;border-radius:4px}</style>"
    "<h2><img src=/icon.svg width=32 height=32 alt='' style='vertical-align:-7px;margin-right:6px'>brim</h2>";

static esp_err_t page_root(httpd_req_t *req)
{
    if (!host_ok(req)) return page_redirect(req, HTTPD_404_NOT_FOUND);
    static char buf[4096];   // static: the httpd task is single-threaded; keeps 4 kB off its stack
    static char e_ssid[200], e_host[400], e_topic[200];
    const settings_t *s = s_settings;
    esc(s->ssid, e_ssid, sizeof(e_ssid));
    esc(s->ntfy_host, e_host, sizeof(e_host));
    esc(s->topic, e_topic, sizeof(e_topic));
    int n = snprintf(buf, sizeof(buf), "%s", PAGE_HEAD);
    if (!s_status && s->ssid[0] && !s->wifi_ok)
        n += snprintf(buf + n, sizeof(buf) - n,
                      "<p style='background:#fde2e1;padding:10px;border-radius:6px'>brim couldn't join <b>%s</b>. "
                      "Check the password, and that it is a 2.4 GHz network, then save again.</p>", e_ssid);
    if (s_status && !unlocked())
        n += snprintf(buf + n, sizeof(buf) - n,
                      "<p style='background:#fff3cd;padding:10px;border-radius:6px'><b>Double-tap brim</b> on its "
                      "charger to unlock changes for 2 minutes.</p>");
    if (s_status)
        n += snprintf(buf + n, sizeof(buf) - n, "<p>Battery %d %% %s &middot; water %s</p>", s_status->battery_pct,
                      s_status->charging ? "(charging)" : "", isnan(s_status->temp_c) ? "--" : "measured");
    n += snprintf(buf + n, sizeof(buf) - n,
                  "<form method=post action=/save><input type=hidden name=k value=%s>"
                  "<label>Wi-Fi name<input name=ssid value='%s' required></label>"
                  "<label>Wi-Fi password<input name=pass type=password placeholder='%s'></label>"
                  "<label>Alarm at the top of pad<select name=pad>",
                  s_key, e_ssid, s->pass[0] ? "unchanged" : "");
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
                  "<p><b>Alerts:</b> install the free <b>ntfy</b> app, tap <b>+</b> and subscribe to this topic:</p>"
                  "<input id=t readonly value='%s' onclick='this.select()'>"
                  "<button type=button onclick=\"t.select();document.execCommand('copy');this.textContent='Copied'\">"
                  "Copy topic</button><br>"
                  "<button>Save</button></form>",
                  s->temp_limit_c, s->notify_filling ? " checked" : "", e_host,
                  s->sense_mode == SENSE_TOUCH ? " selected" : "", s->sense_mode == SENSE_FDC ? " selected" : "",
                  s->sense_mode == SENSE_COMPARE ? " selected" : "", e_topic);
    if (s_status)
        n += snprintf(buf + n, sizeof(buf) - n,
                      "<form method=post action=/test><input type=hidden name=k value=%s>"
                      "<button>Send a test alert</button></form>"
                      "<h3>Firmware update</h3><form method=post action=/update enctype=application/octet-stream "
                      "onsubmit=\"event.preventDefault();fetch('/update',{method:'POST',headers:{'X-Brim-Key':'%s'},"
                      "body:this.f.files[0]}).then(r=>r.text()).then(t=>document.body.innerHTML+='<p>'+t+'</p>')\">"
                      "<input name=f type=file accept=.bin><button>Upload</button></form>", s_key, s_key);
    if (n >= (int)sizeof(buf)) n = sizeof(buf) - 1;   // never send past the end if a field grows
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, buf, n);
}

static esp_err_t page_save(httpd_req_t *req)
{
    static char body[1024], v[200];      // v holds a still-encoded value: 63-char password x 3
    if (!host_ok(req)) return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Wrong host");
    if (req->content_len >= sizeof(body)) return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Form too large");
    int len = 0;
    while (len < (int)req->content_len) {
        int r = httpd_req_recv(req, body + len, req->content_len - len);
        if (r <= 0) return httpd_resp_send_500(req);
        len += r;
    }
    body[len] = 0;
    if (!form_get(body, "k", v, sizeof(v)) || strcmp(v, s_key))
        return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Stale page: reload it and try again");
    if (s_status && !unlocked())
        return send_locked(req);
    settings_t *s = s_settings;
    if (form_get(body, "ssid", v, sizeof(v)) && strcmp(v, s->ssid)) { strlcpy(s->ssid, v, sizeof(s->ssid)); s->wifi_ok = false; }
    if (form_get(body, "pass", v, sizeof(v)) && v[0]) { strlcpy(s->pass, v, sizeof(s->pass)); s->wifi_ok = false; }   // blank = keep
    if (form_get(body, "host", v, sizeof(v)) && v[0] && host_name_ok(v)) strlcpy(s->ntfy_host, v, sizeof(s->ntfy_host));
    if (form_get(body, "pad", v, sizeof(v))) { int p = atoi(v); if (p >= 1 && p <= 6) s->alarm_pad = p; }
    if (form_get(body, "tlim", v, sizeof(v))) { float t = strtof(v, NULL); if (t >= 30 && t <= 50) s->temp_limit_c = t; }
    s->notify_filling = form_get(body, "fill", v, sizeof(v));
    if (form_get(body, "sense", v, sizeof(v))) { int m = atoi(v); if (m >= SENSE_TOUCH && m <= SENSE_COMPARE) s->sense_mode = m; }
    if (!s->topic[0]) settings_new_topic(s->topic, sizeof(s->topic));
    settings_save(s);
    s_saved = true;
    xEventGroupSetBits(s_ev, EV_SAVED);
    char resp[1700], e_ssid[200];
    int n = snprintf(resp, sizeof(resp),
                     "%s<p>Saved. brim will now join <b>%s</b>.</p><p>Within a minute you should get a "
                     "<b>brim is connected</b> alert in ntfy (topic <code>%s</code>).</p><p>No alert and the light blinks "
                     "cyan again? The Wi-Fi password was wrong: rejoin <b>brim-setup</b> and fix it.</p>",
                     PAGE_HEAD, esc(s->ssid, e_ssid, sizeof(e_ssid)), s->topic);
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, resp, n);
}

static esp_err_t page_test(httpd_req_t *req)
{
    char body[64] = {0}, v[24];
    if (!host_ok(req)) return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Wrong host");
    int len = httpd_req_recv(req, body, sizeof(body) - 1);
    if (len <= 0 || !form_get(body, "k", v, sizeof(v)) || strcmp(v, s_key))
        return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Stale page: reload it and try again");
    esp_err_t e = net_ntfy(s_settings, "brim test", "If you can read this, brim's alerts reach this phone.", 4, "bathtub");
    char resp[1000];
    int n = snprintf(resp, sizeof(resp), "%s<p>%s</p><p><a href=/>Back</a></p>", PAGE_HEAD,
                     e == ESP_OK ? "Test alert sent. Check the ntfy app." : "Couldn't reach the ntfy server.");
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, resp, n);
}

// captive portal: every unknown URL (e.g. the phone's captive.apple.com check) redirects to the setup form
static esp_err_t page_redirect(httpd_req_t *req, httpd_err_code_t err)
{
    httpd_resp_set_status(req, "302 Found");
    httpd_resp_set_hdr(req, "Location", "http://192.168.4.1/");
    return httpd_resp_send(req, NULL, 0);
}

// minimal DNS server for setup mode: answers every A query with 192.168.4.1
static void dns_task(void *arg)
{
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(53), .sin_addr.s_addr = htonl(INADDR_ANY)};
    struct timeval tv = {.tv_sec = 1};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    if (sock < 0 || bind(sock, (struct sockaddr *)&a, sizeof(a)) < 0) { if (sock >= 0) close(sock); vTaskDelete(NULL); return; }
    uint8_t p[512];
    while (s_dns_run) {
        struct sockaddr_in from;
        socklen_t fl = sizeof(from);
        int n = recvfrom(sock, p, sizeof(p) - 16, 0, (struct sockaddr *)&from, &fl);
        if (n < 12 || (p[2] & 0x80)) continue;                       // not a query
        int q = 12;
        while (q < n && p[q]) q += p[q] + 1;                          // skip QNAME
        if (q + 5 > n) continue;
        q += 5;                                                       // zero byte + QTYPE + QCLASS
        bool is_a = p[q - 4] == 0 && p[q - 3] == 1;
        p[2] = 0x84 | (p[2] & 0x01);                                  // response, authoritative, keep RD
        p[3] = 0x00;
        p[6] = 0; p[7] = is_a ? 1 : 0;                                // ANCOUNT
        p[8] = p[9] = p[10] = p[11] = 0;
        n = q;
        if (is_a) {
            const uint8_t ans[16] = {0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 60, 0, 4, 192, 168, 4, 1};
            memcpy(p + n, ans, sizeof(ans));
            n += sizeof(ans);
        }
        sendto(sock, p, n, 0, (struct sockaddr *)&from, fl);
    }
    close(sock);
    vTaskDelete(NULL);
}

static esp_err_t page_update(httpd_req_t *req)
{
    char key[24];
    if (!host_ok(req)) return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Wrong host");
    // custom header: a cross-site page can't send it without a CORS preflight, which this server never grants
    if (httpd_req_get_hdr_value_str(req, "X-Brim-Key", key, sizeof(key)) != ESP_OK || strcmp(key, s_key))
        return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Stale page: reload it and try again");
    if (!unlocked()) return send_locked(req);
    const esp_partition_t *part = esp_ota_get_next_update_partition(NULL);
    esp_ota_handle_t h;
    if (!part || req->content_len == 0 || req->content_len > part->size)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Not a brim firmware file");
    if (esp_ota_begin(part, OTA_WITH_SEQUENTIAL_WRITES, &h) != ESP_OK) return httpd_resp_send_500(req);
    char buf[1024];
    int remaining = req->content_len, stalls = 0;
    while (remaining > 0) {
        int r = httpd_req_recv(req, buf, remaining < (int)sizeof(buf) ? remaining : (int)sizeof(buf));
        if (r == HTTPD_SOCK_ERR_TIMEOUT && ++stalls < 5) continue;     // a stalled upload can't hold the server
        stalls = 0;
        if (r <= 0 || esp_ota_write(h, buf, r) != ESP_OK) { esp_ota_abort(h); return httpd_resp_send_500(req); }
        remaining -= r;
    }
    if (esp_ota_end(h) != ESP_OK || esp_ota_set_boot_partition(part) != ESP_OK) return httpd_resp_send_500(req);
    s_ota_done = true;
    return httpd_resp_sendstr(req, "Update written. brim restarts in a moment.");
}

static esp_err_t page_icon(httpd_req_t *req)
{
    httpd_resp_set_type(req, "image/svg+xml");
    httpd_resp_set_hdr(req, "Cache-Control", "max-age=86400");
    return httpd_resp_send(req, BRAND_ICON_SVG, sizeof(BRAND_ICON_SVG) - 1);
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
    httpd_uri_t icon = {.uri = "/icon.svg", .method = HTTP_GET, .handler = page_icon};
    httpd_register_uri_handler(s_httpd, &icon);
    if (s_status) {
        httpd_uri_t upd = {.uri = "/update", .method = HTTP_POST, .handler = page_update};
        httpd_register_uri_handler(s_httpd, &upd);
        httpd_uri_t test = {.uri = "/test", .method = HTTP_POST, .handler = page_test};
        httpd_register_uri_handler(s_httpd, &test);
    } else {
        httpd_register_err_handler(s_httpd, HTTPD_404_NOT_FOUND, page_redirect);
    }
    return ESP_OK;
}

bool net_provision(settings_t *s, int timeout_ms)
{
    s_settings = s;
    s_status = NULL;
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
    // the RNG is only a true RNG while the radio runs: make the secrets after esp_wifi_start()
    if (!s->topic[0]) settings_new_topic(s->topic, sizeof(s->topic));
    new_key();
    start_httpd();
    s_dns_run = true;
    xTaskCreate(dns_task, "dns", 3072, NULL, 5, NULL);
    ESP_LOGI(TAG, "setup: join Wi-Fi '%s' and open http://192.168.4.1", ap.ap.ssid);
    EventBits_t b = xEventGroupWaitBits(s_ev, EV_SAVED, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms));
    vTaskDelay(pdMS_TO_TICKS(1500));   // let the confirmation page go out
    s_dns_run = false;
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
    s_unlock_until = 0;
    new_key();
    return start_httpd();
}

void net_web_stop(void)
{
    if (s_httpd) { httpd_stop(s_httpd); s_httpd = NULL; }
}

bool net_web_saved(void) { return s_saved; }
bool net_ota_done(void) { return s_ota_done; }
