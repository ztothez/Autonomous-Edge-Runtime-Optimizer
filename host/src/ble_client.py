import asyncio
import struct
from bleak import BleakClient

ADDRESS = "F4:58:6B:B4:FE:06"
TELEM_UUID = "e5a10002-4a1b-4c3d-8f00-0123456789ab"
CFG_UUID = "e5a10003-4a1b-4c3d-8f00-0123456789ab"

PKT = struct.Struct("<IIIIIIIHHHH")   # 36 bytes, must match telemetry_pkt in ble_svc.h
CFG = struct.Struct("<HHH")           # T, N, R, must match config_pkt
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
async def read_config(client):
    return CFG.unpack(await client.read_gatt_char(CFG_UUID))

async def write_config(client, t, n, r):
    await client.write_gatt_char(CFG_UUID, CFG.pack(t, n, r), response=True)

async def main():
    async with BleakClient(ADDRESS) as client:
        print(f"Connected to {ADDRESS}")
        print(f"Current config (T, N, R): {await read_config(client)}")

        await write_config(client, 50, 16, 2)            # safe default
        print(f"Reset to: {await read_config(client)}")

        await client.start_notify(TELEM_UUID, on_telemetry)
        try:
            await asyncio.sleep(20)                      # R=2: a packet every 1600 ms

            await write_config(client, 100, 8, 1)
            print(f"New config: {await read_config(client)}")
            await asyncio.sleep(8)                       # window 800 ms, a packet per window

            try:
                await write_config(client, 100, 8, 0)    # R=0 must be rejected
            except Exception as e:
                print(f"Write of R=0 rejected: {e}")
            print(f"Config after bad write: {await read_config(client)}")   # still (100, 8, 1)
        finally:
            await write_config(client, 50, 16, 2)        # restore the safe default
            await client.stop_notify(TELEM_UUID)

asyncio.run(main())