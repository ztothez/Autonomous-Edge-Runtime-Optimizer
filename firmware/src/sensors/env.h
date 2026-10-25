/* Phase 1: environmental sensing, BME280 (I2C) and DHT11 (GPIO) */
#ifndef ENV_H
#define ENV_H

#include <stdint.h>

#define ENV_BME_PERIOD_MS 2000U
#define ENV_DHT_PERIOD_MS 10000U   /* DHT11 allows at most 1 Hz, and its read blocks ~25 ms */

#define ENV_BME_OK (1U << 0)
#define ENV_DHT_OK (1U << 1)

struct env_sample {
    int16_t  temp_c100;       /* BME280, 0.01 degC */
    uint16_t hum_c100;        /* BME280, 0.01 %RH */
    uint16_t press_dhpa;      /* BME280, 0.1 hPa */
    uint16_t status;          /* ENV_BME_OK / ENV_DHT_OK: last read of each sensor succeeded */
};

uint16_t env_init(void);                       /* returns mask of sensors that are ready */
int env_read_bme(struct env_sample *out);
int env_read_dht(struct env_sample *out);

#endif