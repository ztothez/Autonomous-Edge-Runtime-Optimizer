#pragma once
#include <stdint.h>

/* Phase 0/1: hardware validation and sensor acquisition */

/* Print every device that answers on the I2C bus (and identify MPU/BMP chips). */
void sensor_i2c_scan(void);

/* Check the bus and wake the MPU-6050. Returns 0 on success, negative errno on failure. */
int sensor_init(void);

/* One accelerometer sample: vector magnitude in (uncalibrated) mg.
 * Returns 0 if the I2C read fails. */
int32_t sensor_read_mg(void);
