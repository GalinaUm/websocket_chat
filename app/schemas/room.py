from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RoomCreate(BaseModel):
    name: str


class InviteIn(BaseModel):
    username: str


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_by: int
    created_at: datetime


class RoomMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    online: bool


class RoomRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str
    status: str
    created_at: datetime
