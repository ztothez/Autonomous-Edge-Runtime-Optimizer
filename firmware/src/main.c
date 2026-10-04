#include <stdio.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/conn.h>

static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME,
            sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(
    BT_UUID_128_ENCODE(0xe5a10001, 0x4a1b, 0x4c3d, 0x8f00, 0x0123456789ab));
static struct bt_uuid_128 telem_uuid = BT_UUID_INIT_128(
    BT_UUID_128_ENCODE(0xe5a10002, 0x4a1b, 0x4c3d, 0x8f00, 0x0123456789ab));

static void ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY) {
        printf("Notifications enabled\n");
    } else {
        printf("Notifications disabled\n");
    }
}

BT_GATT_SERVICE_DEFINE(edge_svc,
    BT_GATT_PRIMARY_SERVICE(&svc_uuid),
    BT_GATT_CHARACTERISTIC(&telem_uuid.uuid, BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_NONE, NULL, NULL, NULL),
    BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
);

static void recycled(void)
{
    int err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), NULL, 0);
    if (err) {
        printf("Failed to restart advertising: %d\n", err);
    } else {
        printf("Advertising restarted\n");
    }
}
BT_CONN_CB_DEFINE(conn_cbs) = { .recycled = recycled };

struct telemetry_pkt {
    uint32_t seq;
    uint32_t uptime_ms;
    int32_t  sample;
    uint32_t proc_time_us;
} __packed;

int main(void)
{
    int err;

    err = bt_enable(NULL);
    if (err) {
        printf("Failed to enable Bluetooth: %d\n", err);
        return 0;
    }

    err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), NULL, 0);
    if (err) {
        printf("Failed to start advertising: %d\n", err);
        return 0;
    }
    printf("Advertising as EdgeOpt\n");

    struct telemetry_pkt pkt = {0};
    while (1) {
        uint32_t t0 = k_cycle_get_32();
        pkt.sample = (pkt.seq % 100);
        uint32_t t1 = k_cycle_get_32();
        pkt.proc_time_us = k_cyc_to_us_floor32(t1 - t0);
        pkt.uptime_ms = k_uptime_get_32();
        bt_gatt_notify(NULL, &edge_svc.attrs[1], &pkt, sizeof(pkt));
        pkt.seq++;
        k_msleep(1000);
    }
}