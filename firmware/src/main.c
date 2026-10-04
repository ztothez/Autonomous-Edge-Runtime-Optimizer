#include <zephyr/bluetooth/bluetooth.h>
static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME,
            sizeof(CONFIG_BT_DEVICE_NAME) - 1),
			
};
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
	return 0;
}

