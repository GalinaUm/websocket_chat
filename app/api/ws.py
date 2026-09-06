import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis

from app.core.config import settings
from app.core.security import decode_token

router = APIRouter()


@router.websocket("/ws/rooms/{room_id}")
async def ws_room(websocket: WebSocket, room_id: int, token: str = ""):
    username = decode_token(token)
    if username is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    redis = Redis.from_url(settings.redis_url, decode_responses=True,  protocol=2)
    pubsub = redis.pubsub()
    channel = f"room:{room_id}"
    await pubsub.subscribe(channel)

    queue: asyncio.Queue = asyncio.Queue()

    async def redis_listener():
        async for message in pubsub.listen():
            if message["type"] == "message":
                await queue.put(message["data"])

    async def sender():
        while True:
            payload = await queue.get()
            await websocket.send_text(payload)

    listener_task = asyncio.create_task(redis_listener())
    sender_task = asyncio.create_task(sender())

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        listener_task.cancel()
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.close()