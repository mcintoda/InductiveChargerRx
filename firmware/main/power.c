#include "power.h"

#include "board.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_check.h"

static const char *TAG = "power";
static adc_oneshot_unit_handle_t s_adc;
static adc_cali_handle_t s_cali;
static adc_channel_t s_vbat_ch;

esp_err_t power_init(void)
{
    gpio_config_t in = {.pin_bit_mask = (1ULL << PIN_QI_DET_N) | (1ULL << PIN_CHG_N), .mode = GPIO_MODE_INPUT,
                        .pull_up_en = GPIO_PULLUP_ENABLE};
    ESP_RETURN_ON_ERROR(gpio_config(&in), TAG, "gpio in");

    adc_unit_t unit;
    ESP_RETURN_ON_ERROR(adc_oneshot_io_to_channel(PIN_VBAT_SENSE, &unit, &s_vbat_ch), TAG, "vbat pin");
    adc_oneshot_unit_init_cfg_t ucfg = {.unit_id = unit};
    ESP_RETURN_ON_ERROR(adc_oneshot_new_unit(&ucfg, &s_adc), TAG, "adc");
    adc_oneshot_chan_cfg_t ccfg = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
    ESP_RETURN_ON_ERROR(adc_oneshot_config_channel(s_adc, s_vbat_ch, &ccfg), TAG, "adc ch");
    adc_cali_curve_fitting_config_t cal = {.unit_id = unit, .chan = s_vbat_ch, .atten = ADC_ATTEN_DB_12,
                                           .bitwidth = ADC_BITWIDTH_DEFAULT};
    if (adc_cali_create_scheme_curve_fitting(&cal, &s_cali) != ESP_OK) s_cali = NULL;
    return ESP_OK;
}

int power_battery_mv(void)
{
    int raw = 0, mv = 0, sum = 0;
    for (int i = 0; i < 8; i++) {
        if (adc_oneshot_read(s_adc, s_vbat_ch, &raw) != ESP_OK) return -1;
        if (s_cali) adc_cali_raw_to_voltage(s_cali, raw, &mv);
        else mv = raw * 3100 / 4095;
        sum += mv;
    }
    return sum / 8 * 2;   // 1M/1M divider
}

int power_battery_pct(int mv)
{
    // open-circuit-ish Li-ion curve (light load), linear between points
    static const int pts[][2] = {{3300, 0}, {3600, 8}, {3700, 22}, {3750, 35}, {3800, 50},
                                 {3870, 62}, {3950, 75}, {4050, 88}, {4150, 97}, {4200, 100}};
    if (mv <= pts[0][0]) return 0;
    for (int i = 1; i < (int)(sizeof(pts) / sizeof(pts[0])); i++)
        if (mv <= pts[i][0])
            return pts[i - 1][1] + (mv - pts[i - 1][0]) * (pts[i][1] - pts[i - 1][1]) / (pts[i][0] - pts[i - 1][0]);
    return 100;
}

int power_battery_level(void)
{
    int mv = power_battery_mv();
    return mv > 0 ? power_battery_pct(mv) : -1;
}

bool power_on_charger(void) { return gpio_get_level(PIN_QI_DET_N) == 0; }
bool power_charging(void) { return gpio_get_level(PIN_CHG_N) == 0; }
