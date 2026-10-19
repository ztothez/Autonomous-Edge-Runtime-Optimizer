import asyncio
import struct
from bleak import BleakClient

ADDRESS = "F4:58:6B:B4:FE:06"
TELEM_UUID = "e5a10002-4a1b-4c3d-8f00-0123456789ab"
CFG_UUID = "e5a10003-4a1b-4c3d-8f00-0123456789ab"

PKT = struct.Struct("<IIIIIIIHHHH")   # 36 bytes, must match telemetry_pkt in ble_svc.h
last_seq = None
lost = 0

def on_telemetry(sender, data):
    global last_seq, lost
    (seq, uptime_ms, rms_mg, proc_us, events, windows, sent,
     notify_err, duty_permille, stack_free, period_ms) = PKT.unpack(data)
    if last_seq is not None and seq > last_seq + 1:
        lost += seq - last_seq - 1
    last_seq = seq
    print(f"Seq: {seq}, Uptime: {uptime_ms}, RMS: {rms_mg} mg, Proc: {proc_us} us, "
          f"Duty: {duty_permille}, Stack: {stack_free}, Events: {events}, "
          f"Windows: {windows}, Sent: {sent}, Err: {notify_err}, Lost: {lost}")
async def read_period(client):
    data = await client.read_gatt_char(CFG_UUID)
    return struct.unpack("<H", data)[0]

async def write_period(client, ms):
    await client.write_gatt_char(CFG_UUID, struct.pack("<H", ms), response=True)

async def main():
    async with BleakClient(ADDRESS) as client:
        print(f"Connected to {ADDRESS}")
        print(f"Current period: {await read_period(client)} ms")

        await write_period(client, 50)                   # always start from the safe default
        print(f"Reset to: {await read_period(client)} ms")

        await client.start_notify(TELEM_UUID, on_telemetry)
        try:
            await asyncio.sleep(20)                      # shake test window, about 25 packets

            await write_period(client, 100)
            print(f"New period: {await read_period(client)} ms")
            await asyncio.sleep(8)                       # gaps should be about 1600 ms

            try:
                await write_period(client, 10)
            except Exception as e:
                print(f"Write of 10 rejected: {e}")
            print(f"Period after bad write: {await read_period(client)} ms")  # still 100
        finally:
            await write_period(client, 50)               # restore the safe default
            await client.stop_notify(TELEM_UUID)

asyncio.run(main())