import asyncio
from bleak import BleakClient

ADDRESS = "F4:58:6B:B4:FE:06"

async def main():
    async with BleakClient(ADDRESS) as client:
        if client.is_connected:
            print(f"Connected to {ADDRESS}")
            for service in client.services:
                print(f"Service: {service.uuid} - {service.description}")
                for char in service.characteristics:
                    print(f"  Characteristic: {char.uuid} - Properties: {char.properties}")
        else:
            print(f"Failed to connect to {ADDRESS}")

asyncio.run(main())