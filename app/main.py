from fastapi import FastAPI

from app.api import auth, rooms, ws

app = FastAPI(title="WebSocket Chat")

app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(ws.router)
