"""Phase 9: real-sensor sanity check. Shake the GY-521 and watch Events rise."""
import asyncio
import sys
import experiment as ex
from bleak import BleakClient


async def main(seconds):
    async with BleakClient(ex.ADDRESS) as client:
        def on_tel(_s, data):
            p = ex.Packet(*ex.PKT.unpack(data))
            print(f"up={p.uptime_ms:>7} ms rms={p.rms_mg:>4} mg ev={p.events} | "
                  f"BMP {p.temp_c100/100:.2f} C {p.press_dhpa/10:.1f} hPa | "
                  f"DHT {p.dht_temp_c100/100:.0f} C {p.dht_hum_c100/100:.0f} % | env={p.env_status:#x}", flush=True)
        print("Config:", ex.CFG.unpack(await client.read_gatt_char(ex.CFG_UUID)))
        await client.start_notify(ex.TELEM_UUID, on_tel)
        await asyncio.sleep(seconds)
        await client.stop_notify(ex.TELEM_UUID)

asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 30))