import asyncio
from bleak import BleakScanner

async def main():

    devices = await BleakScanner.discover(timeout=5.0, return_adv=True)

    for device, adv in devices.values():
        if adv.local_name == "EdgeOpt":
            print(f"Found EdgeOpt device: {device.address}, RSSI: {adv.rssi}")
            break
    else:
        print("EdgeOpt not found")

asyncio.run(main())