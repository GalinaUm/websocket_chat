from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.message import Message
from app.models.room import Room
from app.models.user import User
from app.schemas.message import MessageCreate, MessageOut
from app.schemas.room import RoomCreate, RoomOut

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("/", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
        room_data: RoomCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room = Room(name=room_data.name, created_by=current_user.id)
    db.add(room)
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
def send_messages(
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
    return message