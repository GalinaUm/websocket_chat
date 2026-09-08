import asyncio
import json

import websockets

from app.core.security import create_access_token


async def client(room_id, username):
    token = create_access_token(username)
    url = f"ws://127.0.0.1:8000/ws/rooms/{room_id}?token={token}"

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"type": "get_messages"}))
        print(f"[{username}] history:", json.loads(await ws.recv()))

        await ws.send(json.dumps({"type": "send_message", "content": f"hello from {username}"}))

        for _ in range(2):
            event = json.loads(await ws.recv())
            print(f"[{username}] event:", event)

        await ws.send(json.dumps({"type": "get_members"}))
        print(f"[{username}] members:", json.loads(await ws.recv()))

        await ws.send(json.dumps({"type": "get_requests"}))
        print(f"[{username}] requests:", json.loads(await ws.recv()))

        await ws.send(json.dumps({"type": "delete_message", "message_id": 21}))
        for _ in range(2):
            print(f"[{username}] delete-event:", json.loads(await ws.recv()))

        await asyncio.sleep(0.5)


async def main():
    t1 = asyncio.create_task(client(5, "alice"))
    t2 = asyncio.create_task(client(5, "bob"))
    await asyncio.gather(t1, t2)


asyncio.run(main())