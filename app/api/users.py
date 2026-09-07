from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserOut])
async def list_users(q: str = "", db: Session = Depends(get_db)):
    if q:
        return  db.execute(
            select(User).where(User.username.ilike(f"%{q}%")).order_by(User.username)
        ).scalars().all()
    return db.execute(
        select(User).order_by(User.username)
    ).scalars().all()