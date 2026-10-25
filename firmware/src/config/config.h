#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <zephyr/toolchain.h>

/* Phase 2: Runtime Configuration
 * Only parameters with a real, measurable effect on the firmware belong here. */

struct config_pkt {
    uint16_t sample_period_ms;   /* T */
    uint16_t window_n;           /* N */
    uint16_t report_every;       /* R */
    uint16_t source;             /* 0 = real sensor, 1 = synthetic events */
} __packed;

#define SOURCE_MAX      1
#define PERIOD_MIN_MS   20
#define PERIOD_MAX_MS   5000
#define WINDOW_MIN      8
#define WINDOW_MAX      64       /* must stay <= N_MAX (128) in main.c */
#define REPORT_MIN      1
#define REPORT_MAX      10

/* Snapshot of the active configuration. */
struct config_pkt config_get(void);

/* Convenience accessor used by the sampling loop. */
uint16_t config_sample_period_ms(void);

/* true if every field is inside its allowed range. */
bool config_validate(const struct config_pkt *c);

/* Replace the active configuration (caller must validate first). */
void config_set(const struct config_pkt *c);
