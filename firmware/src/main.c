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

static struct bt_uuid_128 cfg_uuid = BT_UUID_INIT_128(
    BT_UUID_128_ENCODE(0xe5a10003, 0x4a1b, 0x4c3d, 0x8f00, 0x0123456789ab));

struct config_pkt {
    uint16_t sample_period_ms;
} __packed;

#define PERIOD_MIN_MS 50
#define PERIOD_MAX_MS 5000
static volatile struct config_pkt cfg = { .sample_period_ms = 1000 };  /* safe default */

static ssize_t read_cfg(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                        void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset, (const void *)&cfg, sizeof(cfg));
}

static ssize_t write_cfg(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                         const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{

    if (offset != 0) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }

    if (len != sizeof(cfg)) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    struct config_pkt new_cfg;
    memcpy(&new_cfg, buf, sizeof(new_cfg));

    if (new_cfg.sample_period_ms < PERIOD_MIN_MS || new_cfg.sample_period_ms > PERIOD_MAX_MS) {
        //       return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED) and change nothing
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    cfg = new_cfg;
    printf("New period: %d ms\n", cfg.sample_period_ms);
    return len;
}

BT_GATT_SERVICE_DEFINE(edge_svc,
    BT_GATT_PRIMARY_SERVICE(&svc_uuid),
    BT_GATT_CHARACTERISTIC(&telem_uuid.uuid, BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_NONE, NULL, NULL, NULL),
    BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&cfg_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_READ | BT_GATT_PERM_WRITE,
                           read_cfg, write_cfg, NULL),
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
        k_msleep(cfg.sample_period_ms);
    }
}