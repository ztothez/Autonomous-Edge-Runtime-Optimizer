/* Phase 0/1: hardware validation and sensor acquisition */
#include <stdio.h>
#include <errno.h>
#include <zephyr/kernel.h>
#include <zephyr/drivers/i2c.h>

#include "sensor.h"
#include "dsp/features.h"

#define MPU_ADDR        0x68
#define MPU_PWR_MGMT_1  0x6B
#define MPU_ACCEL_XOUT  0x3B
#define MPU_LSB_PER_G   16384

static const struct device *const i2c_dev = DEVICE_DT_GET(DT_NODELABEL(i2c0));

void sensor_i2c_scan(void)
{
    uint8_t dummy;
    int found = 0;

    if (!device_is_ready(i2c_dev)) {
        printf("I2C device not ready\n");
        return;
    }

    for (uint8_t addr = 0x08; addr <= 0x77; addr++) {
        if (i2c_read(i2c_dev, &dummy, 1, addr) != 0) {
            continue;
        }
        found++;
        printf("Found device at 0x%02X", addr);

        if (addr == 0x76 || addr == 0x77) {
            uint8_t id;
            if (i2c_reg_read_byte(i2c_dev, addr, 0xD0, &id) == 0) {
                printf("  chip ID 0x%02X (%s)", id,
                       id == 0x60 ? "BME280" : id == 0x58 ? "BMP280" : "unknown");
            }
        } else if (addr == 0x68 || addr == 0x69) {
            uint8_t who;
            if (i2c_reg_read_byte(i2c_dev, addr, 0x75, &who) == 0) {
                printf("  WHO_AM_I 0x%02X", who);
            }
        }
        printf("\n");
    }
    printf("I2C scan done, %d device(s)\n", found);
}

int sensor_init(void)
{
    if (!device_is_ready(i2c_dev)) {
        printf("I2C device not ready\n");
        return -ENODEV;
    }

    int rc = i2c_reg_write_byte(i2c_dev, MPU_ADDR, MPU_PWR_MGMT_1, 0x00);   /* wake MPU-6050 */
    if (rc != 0) {
        printf("MPU wake failed (%d), check wiring\n", rc);
        return rc;
    }
    k_msleep(100);      /* let the sensor settle; the first read after wake is 0 otherwise */
    return 0;
}

int32_t sensor_read_mg(void)
{
    uint8_t b[6];

    if (i2c_burst_read(i2c_dev, MPU_ADDR, MPU_ACCEL_XOUT, b, sizeof(b)) != 0) {
        return 0;
    }

    int32_t x = (int16_t)((b[0] << 8) | b[1]);
    int32_t y = (int16_t)((b[2] << 8) | b[3]);
    int32_t z = (int16_t)((b[4] << 8) | b[5]);

    int64_t m2 = (int64_t)x * x + (int64_t)y * y + (int64_t)z * z;
    return (int32_t)((uint64_t)isqrt64((uint64_t)m2) * 1000 / MPU_LSB_PER_G);
}

/* Phase 3: deterministic synthetic events with known ground truth.
 * Burst k starts at uptime k * SYNTH_PERIOD_MS (k >= 1) and lasts SYNTH_BURST_MS. */
#define SYNTH_PERIOD_MS  5000
#define SYNTH_BURST_MS   400
#define SYNTH_AMP_MG     200
#define SYNTH_NOISE_MG   5

int32_t sensor_synth_mg(uint32_t now_ms)
{
    static uint32_t lcg = 12345;
    lcg = lcg * 1664525u + 1013904223u;
    int32_t noise = (int32_t)((lcg >> 16) % (2 * SYNTH_NOISE_MG + 1)) - SYNTH_NOISE_MG;

    bool in_burst = now_ms >= SYNTH_PERIOD_MS && (now_ms % SYNTH_PERIOD_MS) < SYNTH_BURST_MS;
    return 1000 + noise + (in_burst ? SYNTH_AMP_MG : 0);
}
