import asyncio
import json

import websockets

from app.core.security import create_access_token


async def client(room_id, username, actions):
    token = create_access_token(username)
    url = f"ws://127.0.0.1:8000/ws/rooms/{room_id}?token={token}"
    async with websockets.connect(url) as ws:
        for action in actions:
            await ws.send(json.dumps(action))
            print(f"[{username}] sent:", action)
            print(f"[{username}] got:", json.loads(await ws.recv()))


async def main():

    async with websockets.connect(
        f"ws://127.0.0.1:8000/ws/rooms/5?token={create_access_token('alice')}"
    ) as a:
        await a.send(json.dumps({"type": "get_requests"}))
        print("[alice] requests:", json.loads(await a.recv()))
        await a.send(json.dumps({"type": "approve_request", "request_id": 3}))
        print("[alice] approve result:", json.loads(await a.recv()))


asyncio.run(main())