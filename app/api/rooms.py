from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.db import get_db
from app.models.room_member import RoomMember
from app.models.message import Message
from app.models.room import Room
from app.models.user import User
from app.schemas.message import MessageCreate, MessageOut
from app.schemas.room import RoomCreate, RoomOut, RoomMemberOut
import json

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("/", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
        room_data: RoomCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    user_room_count = db.execute(
        select(func.count(RoomMember.id)).where(RoomMember.user_id == current_user.id)
    ).scalar_one()
    if user_room_count >= settings.max_rooms_per_user:
        raise HTTPException(status_code=400, detail=f"Limited to {settings.max_rooms_per_user} rooms")
    room = Room(name=room_data.name, created_by=current_user.id)
    db.add(room)
    db.flush()

    db.add(RoomMember(room_id=room.id, user_id=current_user.id))
    db.commit()
    db.refresh(room)
    return room


@router.get("/", response_model=list[RoomOut])
def list_rooms(db: Session = Depends(get_db)):
    return db.execute(
        select(Room).order_by(Room.created_at)
    ).scalars().all()


@router.get("/{room_id}/messages", response_model=list[MessageOut])
def list_messages(room_id: int, db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return db.execute(
        select(Message).where(Message.room_id == room.id)
    ).scalars().all()


@router.post("/{room_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_messages(
        room_id: int,
        message_data: MessageCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    message = Message(
        room_id=room.id,
        user_id=current_user.id,
        content=message_data.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    channel = f"room:{room_id}"
    redis = Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)
    await redis.publish(channel, json.dumps({
        "type": "new_message",
        "room_id": message.room_id,
        "user_id": message.user_id,
        "username": current_user.username,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }))
    await redis.close()

    return message


@router.get("/stats", response_model=dict)
def stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    total_rooms = db.execute(select(func.count(Room.id))).scalar_one()
    my_rooms = db.execute(
        select(func.count(RoomMember.id)).where(RoomMember.user_id == current_user.id)
    ).scalar_one()
    return {
        "total_rooms": total_rooms,
        "my_rooms": my_rooms,
        "max_rooms_per_user": settings.max_rooms_per_user,
    }


@router.get("/{room_id}/members", response_model=list[RoomMemberOut])
def list_members(
        room_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room =db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    members = db.execute(
        select(RoomMember).where(RoomMember.room_id == room.id)
    ).scalars().all()

    result = []
    for m in members:
        result.append(RoomMemberOut(
            id=m.user_id,
            username=m.user.username,
            online=False,
        ))
    return result
