#pragma once
#include <stdint.h>
#include <zephyr/toolchain.h>

/* Phase 1/2: BLE telemetry out, runtime configuration in */

struct telemetry_pkt {
    uint32_t seq;
    uint32_t uptime_ms;
    int32_t  sample;
    uint32_t proc_time_us;
} __packed;

/* Enable Bluetooth and start advertising as CONFIG_BT_DEVICE_NAME.
 * Returns 0 on success, otherwise the Zephyr error code. */
int ble_svc_init(void);

/* Send one telemetry notification to the subscribed host.
 * Returns 0 on success, negative errno otherwise. */
int ble_svc_notify(const struct telemetry_pkt *pkt);
