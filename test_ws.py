import asyncio
import websockets

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhbGljZSIsImV4cCI6MTgxMTU5OTM2N30.cwlTE8XCKZTfILJrwxO2e8QGGBvURhaqMTIAFYc1DBw"

async def main():
    async with websockets.connect(f"ws://localhost:8000/ws/rooms/1?token={TOKEN}") as ws:
        while True:
            print("ПОЛУЧЕНО:", await ws.recv())

asyncio.run(main())