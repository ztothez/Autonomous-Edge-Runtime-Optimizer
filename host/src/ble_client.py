import asyncio
import time
from bleak import BleakClient

ADDRESS = "F4:58:6B:B4:FE:06"
TELEM_UUID = "e5a10002-4a1b-4c3d-8f00-0123456789ab"

def on_telemetry(sender, data):
    value = int.from_bytes(data, "little")
    print(f"Telemetry: {value} at {time.time()}")

async def main():
    async with BleakClient(ADDRESS) as client:
        print(f"Connected to {ADDRESS}")
        await client.start_notify(TELEM_UUID, on_telemetry)
        await asyncio.sleep(10)
        await client.stop_notify(TELEM_UUID)

asyncio.run(main())