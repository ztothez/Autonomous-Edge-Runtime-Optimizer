/* Phase 1: Embedded Baseline - windowed feature extraction
 * Pure C, no Zephyr dependency, so it can also be tested on the PC. */
#include "features.h"

uint32_t isqrt64(uint64_t v)
{
    uint64_t r = 0;
    uint64_t bit = 1ULL << 62;

    while (bit > v) {
        bit >>= 2;
    }

    while (bit) {
        if (v >= r + bit) {
            v -= r + bit;
            r = (r >> 1) + bit;
        } else {
            r >>= 1;
        }
        bit >>= 2;
    }
    return (uint32_t)r;
}

uint32_t window_rms(const int32_t *buf, uint16_t n)
{
    if (n == 0) {
        return 0;
    }

    int64_t sum = 0;
    for (uint16_t i = 0; i < n; i++) {
        sum += buf[i];
    }
    int32_t mean = (int32_t)(sum / n);

    uint64_t var = 0;
    for (uint16_t i = 0; i < n; i++) {
        int32_t diff = buf[i] - mean;
        var += (uint64_t)diff * diff;
    }

    return isqrt64(var / n);
}
