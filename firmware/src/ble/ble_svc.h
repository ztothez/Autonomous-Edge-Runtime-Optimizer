#pragma once
#include <stdint.h>
#include <zephyr/toolchain.h>

/* Phase 1/2: BLE telemetry out, runtime configuration in */

struct telemetry_pkt {
    uint32_t seq;
    uint32_t uptime_ms;
    uint32_t rms_mg;
    uint32_t proc_us;
    uint32_t events;
    uint32_t windows;
    uint32_t sent;
    uint16_t notify_err;
    uint16_t duty_permille;
    uint16_t stack_free;
    uint16_t period_ms;
} __packed;

_Static_assert(sizeof(struct telemetry_pkt) == 36, "telemetry_pkt must be 36 bytes");

/* Enable Bluetooth and start advertising as CONFIG_BT_DEVICE_NAME.
 * Returns 0 on success, otherwise the Zephyr error code. */
int ble_svc_init(void);

/* Send one telemetry notification to the subscribed host.
 * Returns 0 on success, negative errno otherwise. */
int ble_svc_notify(const struct telemetry_pkt *pkt);
