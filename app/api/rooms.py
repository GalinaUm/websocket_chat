from ast import List

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session, joinedload

from app.api.auth import get_current_user
from app.core.config import settings
from app.db import get_db
from app.models import RoomRequest
from app.models.room_member import RoomMember
from app.models.message import Message
from app.models.room import Room
from app.models.user import User
from app.schemas.message import MessageCreate, MessageOut
from app.schemas.room import RoomCreate, RoomOut, RoomMemberOut, RoomRequestOut
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


@router.get("/{room_id}/members", response_model=list[RoomMemberOut])
def list_members(
        room_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room =db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    if db.execute(
        select(RoomMember).where(
RoomMember.room_id == room_id,
            RoomMember.user_id == current_user.id,
        )
    ).scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Not a member")

    members = db.execute(
        select(RoomMember)
        .options(joinedload(RoomMember.user))
        .where(RoomMember.room_id == room.id)
    ).scalars().all()

    result = []
    for m in members:
        result.append(RoomMemberOut(
            id=m.user_id,
            username=m.user.username,
            online=False,
        ))

    return result


@router.post("/{room_id}/request", status_code=status.HTTP_201_CREATED)
def knock(
        room_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    existing = db.execute(
        select(RoomMember).where(
            RoomMember.room_id == room.id,
            RoomMember.user_id == current_user.id,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Already a member")

    pending = db.execute(
        select(RoomRequest).where(
            RoomRequest.room_id == room.id,
            RoomRequest.user_id == current_user.id,
            RoomRequest.status == "pending",
        )
    ).scalar_one_or_none()
    if pending:
        raise HTTPException(status_code=400, detail="Request already sent")

    request = RoomRequest(room_id=room.id, user_id=current_user.id)
    db.add(request)
    db.commit()
    return request


@router.get("/{room_id}/request", response_model=list[RoomRequestOut])
def list_requests(
        room_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only room creator can view requests")

    rows = db.execute(
        select(RoomRequest)
        .options(joinedload(RoomRequest.user))
        .where(
            RoomRequest.room_id == room.id,
            RoomRequest.status == "pending",
        )
    ).scalars().all()

    return [
        RoomRequestOut(
            id=r.id,
            user_id=r.user_id,
            username=r.user.username,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/{room_id}/requests/{request_id}/approve", status_code=status.HTTP_200_OK)
def approve_requests(
        room_id: int,
        request_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only room creator can approve")

    req = db.get(RoomRequest, request_id)
    if req is None or req.room_id != room.id:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Request already processed")

    user_count = db.execute(
        select(func.count(RoomMember.id)).where(RoomMember.user_id == req.user_id)
    ).scalar_one()
    if user_count >= settings.max_rooms_per_user:
        req.status = "rejected"
        db.commit()
        raise HTTPException(status_code=400, detail="User reached room limit")

    req.status = "approved"
    db.add(RoomMember(room_id=room.id, user_id=req.user_id))
    db.commit()
    return {"detail": "approved"}


@router.post("/{room_id}/requests/{request_id}/reject", status_code=status.HTTP_200_OK)
def reject_request(
        room_id: int,
        request_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only room creator can reject")

    req = db.get(RoomRequest, request_id)
    if req is None or req.room_id != room.id:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Request already processed")

    req.status = "rejected"
    db.commit()
    return {"detail": "rejected"}


@router.delete("/{room_id}", status_code=status.HTTP_200_OK)
def delete_room(
        room_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only room creator can delete")

    db.execute(delete(Message).where(Message.room_id == room_id))
    db.execute(delete(RoomMember).where(RoomMember.room_id == room.id))
    db.execute(delete(RoomRequest).where(RoomRequest.room_id == room.id))
    db.delete(room)
    db.commit()
    return {"detail": "room deleted"}


@router.delete("/{room_id}/messages/{message_id}", status_code=status.HTTP_200_OK)
async def delete_message(
        room_id: int,
        message_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    message = db.get(Message, message_id)
    if message is None or message.room_id != room.id:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.user_id != current_user.id and room.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only room creator can delete")

    db.delete(message)
    db.commit()

    channel = f"room:{room_id}"
    redis = Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)
    await redis.publish(channel, json.dumps({
        "type": "message_delete",
        "room_id": room_id,
        "id": message_id,
    }))
    await redis.close()

    return {"detail": "message deleted"}
