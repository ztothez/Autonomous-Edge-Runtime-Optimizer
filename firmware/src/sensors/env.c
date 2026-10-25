/* Phase 1: BMP280 read-out through the Zephyr bme280 driver, integer-only conversion (no FPU) */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <errno.h>
#include "env.h"

static const struct device *const bme = DEVICE_DT_GET_ANY(bosch_bme280);

uint16_t env_init(void)
{
    uint16_t mask = 0;

    if (bme != NULL && device_is_ready(bme)) {
        mask |= ENV_BME_OK;
    } else {
        printk("BMP280 not ready\n");
    }
    return mask;
}

int env_read_bme(struct env_sample *out)
{
    struct sensor_value t, h, p;
    int rc = sensor_sample_fetch(bme);

    if (rc) {
        printk("BMP280 fetch failed: %d\n", rc);
        out->status &= ~ENV_BME_OK;
        return rc;
    }
    sensor_channel_get(bme, SENSOR_CHAN_AMBIENT_TEMP, &t);
    sensor_channel_get(bme, SENSOR_CHAN_HUMIDITY, &h);
    sensor_channel_get(bme, SENSOR_CHAN_PRESS, &p);       /* kPa */

    out->temp_c100  = (int16_t)(t.val1 * 100 + t.val2 / 10000);
    out->hum_c100   = (uint16_t)(h.val1 * 100 + h.val2 / 10000);
    out->press_dhpa = (uint16_t)((p.val1 * 1000 + p.val2 / 1000) / 10);
    out->status |= ENV_BME_OK;
    return 0;
}
