#include <stdio.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/drivers/i2c.h>
#include <string.h>
#include <cmsis_core.h>


static const struct device *const i2c_dev = DEVICE_DT_GET(DT_NODELABEL(i2c0));

#define N_MAX 128
#define WINDOW 16
#define EVENT_RMS_MG 50

static int32_t buf[N_MAX];
static uint16_t n;

static uint32_t isqrt64(uint64_t v)
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

static int32_t acquire(void)
{
    uint8_t b[6];
    if (i2c_burst_read(i2c_dev, 0x68, 0x3B, b, sizeof(b)) != 0) {
        return 0;                       
    }
    int32_t x = (int16_t)((b[0] << 8) | b[1]); 
    int32_t y = (int16_t)((b[2] << 8) | b[3]);
    int32_t z = (int16_t)((b[4] << 8) | b[5]);
    int64_t m2 = (int64_t)x * x + (int64_t)y * y + (int64_t)z * z;
    return (int32_t)((uint64_t)isqrt64((uint64_t)m2) * 1000 / 16384);
}

static void i2c_scan(void)
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
static volatile struct config_pkt cfg = { .sample_period_ms = 50 };  /* safe default */

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
//main function
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
    k_msleep(500);
    i2c_scan();
    i2c_reg_write_byte(i2c_dev, 0x68, 0x6B, 0x00);   /* wake MPU-6050 */
    k_msleep(100);

    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    uint32_t events = 0;
        bool above_prev = false;                 /* before the while loop */


    struct telemetry_pkt pkt = {0};
    while (1) {
        uint32_t t0 = k_cycle_get_32();

        /* ---- Phase 1: Embedded Baseline - windowed RMS feature + processing time ---- */
        pkt.sample = acquire();
        buf[n++] = pkt.sample;
        if (n >= WINDOW) {
            uint32_t c0 = DWT->CYCCNT;
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
            
            uint32_t rms = isqrt64(var / n);
            uint32_t us = (DWT->CYCCNT - c0) / 64;     /* measure first */

            bool above = rms > EVENT_RMS_MG;
            if (above && !above_prev) {                /* rising edge = one new event */
                events++;
                printf("EVENT: rms %u mg  events %u\n", rms, events);
            }
            above_prev = above;

            printf("rms %u mg  proc %u us\n", rms, us);
            n = 0;
        }

        uint32_t t1 = k_cycle_get_32();
        pkt.proc_time_us = k_cyc_to_us_floor32(t1 - t0);
        pkt.uptime_ms = k_uptime_get_32();
        bt_gatt_notify(NULL, &edge_svc.attrs[1], &pkt, sizeof(pkt));
        pkt.seq++;
        k_msleep(cfg.sample_period_ms);
    }
}