#pragma once
#include <stdint.h>

/* Phase 1: Embedded Baseline - windowed feature extraction */

/* Integer square root (the nRF52833 has no FPU). */
uint32_t isqrt64(uint64_t v);

/* RMS of buf[0..n-1] around its mean, in the same units as the samples.
 * Returns 0 for n == 0. */
uint32_t window_rms(const int32_t *buf, uint16_t n);
