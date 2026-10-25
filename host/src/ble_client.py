"""Phase 2: manual BLE test client (config write, rejection check, safe restore)."""
import asyncio

import experiment as ex
from bleak import BleakClient

SAFE = (50, 16, 2, 0)                 # safe default: real sensor

last_seq = None
lost = 0


def on_telemetry(sender, data):
    global last_seq, lost
    p = ex.Packet(*ex.PKT.unpack(data))
    if last_seq is not None and p.seq > last_seq + 1:
        lost += p.seq - last_seq - 1
    last_seq = p.seq
    print(f"Seq: {p.seq}, Uptime: {p.uptime_ms}, RMS: {p.rms_mg} mg, Proc: {p.proc_us} us, "
          f"Duty: {p.duty}, Stack: {p.stack}, Events: {p.events}, Windows: {p.windows}, "
          f"Sent: {p.sent}, Err: {p.notify_err}, Lost: {lost}, env={p.env_status:#x}")


async def read_config(client):
    return ex.CFG.unpack(await client.read_gatt_char(ex.CFG_UUID))


async def write_config(client, t, n, r, src=0):
    await client.write_gatt_char(ex.CFG_UUID, ex.CFG.pack(t, n, r, src), response=True)


async def main():
    async with BleakClient(ex.ADDRESS) as client:
        print(f"Connected to {ex.ADDRESS}")
        print(f"Current config (T, N, R, src): {await read_config(client)}")

        await write_config(client, *SAFE)                # always start from the safe default
        print(f"Reset to: {await read_config(client)}")

        await client.start_notify(ex.TELEM_UUID, on_telemetry)
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
            await client.stop_notify(ex.TELEM_UUID)


asyncio.run(main())