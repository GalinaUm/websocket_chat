from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RoomCreate(BaseModel):
    name: str


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_by: int
    created_at: datetime

