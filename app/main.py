from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from app.api import auth, rooms, ws

app = FastAPI(title="WebSocket Chat")

app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(ws.router)



app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)