import asyncio
import struct
from bleak import BleakClient

ADDRESS = "F4:58:6B:B4:FE:06"
TELEM_UUID = "e5a10002-4a1b-4c3d-8f00-0123456789ab"
CFG_UUID = "e5a10003-4a1b-4c3d-8f00-0123456789ab"

PKT = struct.Struct("<IIiI")
last_seq = None
lost = 0

def on_telemetry(sender, data):
    global last_seq, lost
    seq, uptime_ms, sample, proc_us = PKT.unpack(data)
    if last_seq is not None and seq > last_seq + 1:
        lost += seq - last_seq - 1
    last_seq = seq
    print(f"Seq: {seq}, Uptime: {uptime_ms}, Sample: {sample}, Proc Time: {proc_us}, Lost: {lost}")

async def read_period(client):
    data = await client.read_gatt_char(CFG_UUID)
    return struct.unpack("<H", data)[0]

async def main():
    async with BleakClient(ADDRESS) as client:
        print(f"Connected to {ADDRESS}")
        print(f"Current period: {await read_period(client)} ms")

        await client.start_notify(TELEM_UUID, on_telemetry)
        try:
            await asyncio.sleep(5)                       # baseline, about 1 s gaps

            await client.write_gatt_char(CFG_UUID, struct.pack("<H", 500), response=True)
            print(f"New period: {await read_period(client)} ms")
            await asyncio.sleep(5)                       # gaps should drop to about 500 ms

            try:
                await client.write_gatt_char(CFG_UUID, struct.pack("<H", 10), response=True)
            except Exception as e:
                print(f"Write of 10 rejected: {e}")
            print(f"Period after bad write: {await read_period(client)} ms")  # still 500
        finally:
            await client.write_gatt_char(CFG_UUID, struct.pack("<H", 1000), response=True)
            await client.stop_notify(TELEM_UUID)

asyncio.run(main())