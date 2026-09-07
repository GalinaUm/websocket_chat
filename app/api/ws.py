import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import settings
from app.core.security import decode_token
from app.db import SessionLocal
from app.models.message import Message
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.user import User

router = APIRouter()


async def dispatch(db, current_user: User, room_id: int, msg: dict):
    mtype = msg.get("type")

    if mtype == "send_message":
        room = db.get(Room, room_id)
        if room is None:
            return "reply", {"type": "error", "detail": "Room not found"}
        message = Message(
            room_id=room.id,
            user_id=current_user.id,
            content=msg["content"],
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return "broadcast", {
            "type": "new_message",
            "id": message.id,
            "room_id": message.room_id,
            "user_id": message.user_id,
            "username": current_user.username,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }

    if mtype == "get_messages":
        room = db.get(Room, room_id)
        if room is None:
            return "reply", {"type": "error", "detail": "Room not found"}
        messages = db.execute(
            select(Message).where(Message.room_id == room.id)
        ).scalars().all()
        return "reply", {
            "type": "history",
            "messages": [
                {
                    "id": m.id,
                    "user_id": m.user_id,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }

    return "reply", {"type": "error", "detail": f"Unknown message type: {mtype}"}


@router.websocket("/ws/rooms/{room_id}")
async def ws_room(websocket: WebSocket, room_id: int, token: str = ""):
    username = decode_token(token)
    if username is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    db = SessionLocal()
    current_user = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if current_user is None:
        db.close()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    is_member = db.execute(
        select(RoomMember).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == current_user.id,
        )
    ).scalar_one_or_none()
    if is_member is None:
        db.close()
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

    async def client_reader():
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mode, event = await dispatch(db, current_user, room_id, msg)
            if mode == "reply":
                await websocket.send_text(json.dumps(event))
            else:
                await redis.publish(channel, json.dumps(event))

    listener_task = asyncio.create_task(redis_listener())
    sender_task = asyncio.create_task(sender())
    reader_task = asyncio.create_task(client_reader())

    try:
        await reader_task
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        listener_task.cancel()
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.close()
        db.close()
