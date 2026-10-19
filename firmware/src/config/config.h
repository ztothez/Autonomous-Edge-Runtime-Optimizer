#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <zephyr/toolchain.h>

/* Phase 2: Runtime Configuration
 * Only parameters with a real, measurable effect on the firmware belong here. */

struct config_pkt {
    uint16_t sample_period_ms;
} __packed;

#define PERIOD_MIN_MS 50
#define PERIOD_MAX_MS 5000

/* Snapshot of the active configuration. */
struct config_pkt config_get(void);

/* Convenience accessor used by the sampling loop. */
uint16_t config_sample_period_ms(void);

/* true if every field is inside its allowed range. */
bool config_validate(const struct config_pkt *c);

/* Replace the active configuration (caller must validate first). */
void config_set(const struct config_pkt *c);
