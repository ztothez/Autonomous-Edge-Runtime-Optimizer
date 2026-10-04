import asyncio
import time
from bleak import BleakClient
import struct

ADDRESS = "F4:58:6B:B4:FE:06"
TELEM_UUID = "e5a10002-4a1b-4c3d-8f00-0123456789ab"


PKT = struct.Struct("<IIiI")   # little-endian: seq, uptime_ms, sample, proc_time_us
last_seq = None
lost = 0

def on_telemetry(sender, data):
    global last_seq, lost
    seq, uptime_ms, sample, proc_us = PKT.unpack(data)
    if last_seq is not None and seq > last_seq + 1:
        lost += seq - last_seq - 1
    last_seq = seq

    print(f"Seq: {seq}, Uptime: {uptime_ms}, Sample: {sample}, Proc Time: {proc_us}, Lost: {lost}")
async def main():
    async with BleakClient(ADDRESS) as client:
        print(f"Connected to {ADDRESS}")
        await client.start_notify(TELEM_UUID, on_telemetry)
        await asyncio.sleep(10)   # listen for 10 seconds
        await client.stop_notify(TELEM_UUID)

asyncio.run(main())