/* Phase 1: environmental sensing, BMP280 on I2C 0x76 (temperature and pressure).
 * A DHT11 for humidity was tried and removed (defective part, see README). */
#ifndef ENV_H
#define ENV_H

#include <stdint.h>

#define ENV_BME_PERIOD_MS 2000U

#define ENV_BME_OK (1U << 0)      /* env_status bit 0: last BMP280 read succeeded */

struct env_sample {
    int16_t  temp_c100;       /* 0.01 degC */
    uint16_t hum_c100;        /* always 0: the BMP280 has no humidity channel */
    uint16_t press_dhpa;      /* 0.1 hPa */
    uint16_t status;          /* ENV_BME_OK */
};

uint16_t env_init(void);                       /* returns mask of sensors that are ready */
int env_read_bme(struct env_sample *out);

#endif
