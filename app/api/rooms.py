from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.db import get_db
from app.models import RoomRequest
from app.models.room_member import RoomMember
from app.models.room import Room
from app.models.user import User
from app.schemas.room import RoomCreate, RoomOut

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
