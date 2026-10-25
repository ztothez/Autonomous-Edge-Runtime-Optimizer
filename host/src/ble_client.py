import asyncio
import struct
from bleak import BleakClient

ADDRESS = "F4:58:6B:B4:FE:06"
TELEM_UUID = "e5a10002-4a1b-4c3d-8f00-0123456789ab"
CFG_UUID = "e5a10003-4a1b-4c3d-8f00-0123456789ab"

PKT = struct.Struct("<IIIIIIIHHHH")   # 36 bytes, must match telemetry_pkt in ble_svc.h
CFG = struct.Struct("<HHHH")          # T, N, R, source, must match config_pkt

SAFE = (50, 16, 2, 0)                 # safe default: real sensor

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


async def write_config(client, t, n, r, src=0):
    await client.write_gatt_char(CFG_UUID, CFG.pack(t, n, r, src), response=True)


async def main():
    async with BleakClient(ADDRESS) as client:
        print(f"Connected to {ADDRESS}")
        print(f"Current config (T, N, R, src): {await read_config(client)}")

        await write_config(client, *SAFE)                # always start from the safe default
        print(f"Reset to: {await read_config(client)}")

        await client.start_notify(TELEM_UUID, on_telemetry)
        try:
            # Test 1: good config, synthetic source: Events should rise by about 1 per 5 s
            await write_config(client, 50, 16, 2, 1)
            print(f"Test 1 config: {await read_config(client)}")
            await asyncio.sleep(40)

            # Test 2: slow and long window, synthetic source: bursts should be mostly missed
            await write_config(client, 200, 64, 10, 1)
            print(f"Test 2 config: {await read_config(client)}")
            await asyncio.sleep(60)

            # Test 3: an invalid write must be rejected and change nothing
            try:
                await write_config(client, 100, 8, 0, 1)         # R=0 is invalid
            except Exception as e:
                print(f"Write of R=0 rejected: {e}")
            print(f"Config after bad write: {await read_config(client)}")   # still (200, 64, 10, 1)
        finally:
            await write_config(client, *SAFE)                    # restore the safe default
            await client.stop_notify(TELEM_UUID)


asyncio.run(main())