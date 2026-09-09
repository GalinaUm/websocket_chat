import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis
from sqlalchemy import select, func, delete
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.security import decode_token
from app.db import SessionLocal
from app.models import RoomRequest
from app.models.message import Message
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.user import User

router = APIRouter()


async def dispatch(db, current_user: User, room_id: int, msg: dict, redis):
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
            select(Message)
            .options(joinedload(Message.user))
            .where(Message.room_id == room.id)
        ).scalars().all()
        return "reply", {
            "type": "history",
            "messages": [
                {
                    "id": m.id,
                    "user_id": m.user_id,
                    "username": m.user.username if m.user else "?",
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }

    if mtype == "delete_message":
        message = db.get(Message, msg["message_id"])
        room = db.get(Room, room_id)
        if room is None or message is None or message.room_id != room.id:
            return "reply", {"type": "error", "detail": "Message not found"}
        if message.user_id != current_user.id and room.created_by != current_user.id:
            return "reply", {"type": "error", "detail": "Only author or room creator can delete"}
        db.delete(message)
        db.commit()
        return "broadcast", {"type": "message_deleted", "room_id": room_id, "id": msg["message_id"]}

    if mtype == "get_members":
        rows = db.execute(
            select(RoomMember)
            .options(joinedload(RoomMember.user))
            .where(RoomMember.room_id == room_id)
        ).scalars().all()
        online_ids = {int(x) for x in await redis.smembers("online_users")}
        return "reply", {
            "type": "members",
            "members": [
                {"id": r.user_id, "username": r.user.username, "online": r.user_id in online_ids}
                for r in rows
            ],
        }

    if mtype == "get_requests":
        room = db.get(Room, room_id)
        if room is None:
            return "reply", {"type": "error", "detail": "Room not found"}
        if room.created_by != current_user.id:
            return "reply", {"type": "error", "detail": "Only room creator can view requests"}
        rows = db.execute(
            select(RoomRequest)
            .options(joinedload(RoomRequest.user))
            .where(
                RoomRequest.room_id == room_id,
                RoomRequest.status == "pending",
            )
        ).scalars().all()
        return "reply", {
            "type": "requests", "requests": [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "username": r.user.username,
                    "status": r.status
                } for r in rows
            ]
        }

    if mtype == "approve_request":
        room = db.get(Room, room_id)
        if room is None:
            return "reply", {"type": "error", "detail": "Room not found"}
        if room.created_by != current_user.id:
            return "reply", {"type": "error", "detail": "Only room creator can approve"}
        req = db.get(RoomRequest, msg["request_id"])
        if req is None or req.room_id != room.id:
            return "reply", {"type": "error", "detail": "Request not found"}
        if req.status != "pending":
            return "reply", {"type": "error", "detail": "Request already processed"}
        user_count = db.execute(
            select(func.count(RoomMember.id)).where(RoomMember.user_id == req.user_id)
        ).scalar_one()
        if user_count >= settings.max_rooms_per_user:
            req.status = "rejected"
            db.commit()
            return "broadcast", {
                "type": "request_resolved",
                "room_id": room_id,
                "user_id": req.user_id,
                "username": req.user.username,
                "status": "rejected"
            }
        req.status = "approved"
        db.add(RoomMember(room_id=room.id, user_id=req.user_id))
        db.commit()
        return "broadcast", {
            "type": "member_joined",
            "room_id": room_id,
            "user_id": req.user_id,
            "username": req.user.username,
        }

    if mtype == "reject_request":
        room = db.get(Room, room_id)
        if room is None:
            return "reply", {"type": "error", "detail": "Room not found"}
        if room.created_by != current_user.id:
            return "reply", {"type": "error", "detail": "Only room creator can reject"}
        req = db.get(RoomRequest, msg["request_id"])
        if req is None or req.room_id != room.id:
            return "reply", {"type": "error", "detail": "Request not found"}
        if req.status != "pending":
            return "reply", {"type": "error", "detail": "Request already processed"}
        req.status = "rejected"
        db.commit()
        return "broadcast", {
            "type": "request_resolved",
            "room_id": room_id,
            "user_id": req.user_id,
            "username": req.user.username,
            "status": "rejected",
        }

    if mtype == "delete_room":
        room = db.get(Room, room_id)
        if room is None:
            return "reply", {"type": "error", "detail": "Room not found"}
        if room.created_by != current_user.id:
            return "reply", {"type": "error", "detail": "Only room creator can delete"}
        db.execute(delete(Message).where(Message.room_id == room.id))
        db.execute(delete(RoomMember).where(RoomMember.room_id == room.id))
        db.execute(delete(RoomRequest).where(RoomRequest.room_id == room.id))
        db.delete(room)
        db.commit()
        return "broadcast", {"type": "room_deleted", "room_id": room_id}

    if mtype == "leave_room":
        room = db.get(Room, room_id)
        if room is None:
            return "reply", {"type": "error", "detail": "Room not found"}
        if room.created_by == current_user.id:
            return "reply", {"type": "error", "detail": "Creator cannot leave, delete room instead"}
        member = db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room.id,
                RoomMember.user_id == current_user.id,
            )
        ).scalar_one_or_none()
        if member is None:
            return "reply", {"type": "error", "detail": "Not a member"}
        db.delete(member)
        db.commit()
        return "broadcast", {
            "type": "member_left",
            "room_id": room_id,
            "user_id": current_user.id,
            "username": current_user.username,
        }

    if mtype == "typing":
        return "broadcast", {
            "type": "typing",
            "room_id": room_id,
            "user_id": current_user.id,
            "username": current_user.username,
        }

    if mtype == "edit_message":
        message = db.get(Message, msg["message_id"])
        room = db.get(Room, room_id)
        if room is None or message is None or message.room_id != room.id:
            return "reply", {"type": "error", "detail": "Message not found"}
        if message.user_id != current_user.id:
            return "reply", {"type": "error", "detail": "Only author can edit"}
        content = msg.get("content", "").strip()
        if not content:
            return "reply", {"type": "error", "detail": "Message cannot be empty"}
        message.content = content
        db.commit()
        return "broadcast", {
            "type": "message_edited",
            "room_id": room_id,
            "id": message.id,
            "username": current_user.username,
            "content": message.content,
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

    is_member.last_read_at = datetime.now(timezone.utc)
    db.commit()

    await websocket.accept()
    redis = Redis.from_url(settings.redis_url, decode_responses=True,  protocol=2)

    await redis.sadd("online_users", current_user.id)

    room = db.get(Room, room_id)
    await websocket.send_json({
        "type": "welcome",
        "my_id": current_user.id,
        "room": {
            "id": room.id,
            "name": room.name,
            "created_by": room.created_by,
        },
    })

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
            mode, event = await dispatch(db, current_user, room_id, msg, redis)
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
        user_id = current_user.id
        sender_task.cancel()
        listener_task.cancel()
        db.close()
        await redis.srem("online_users", user_id)
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.close()
