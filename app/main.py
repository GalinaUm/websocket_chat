from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from app.api import auth, rooms, ws
from app.api.users import router as users_router
from app.core.config import settings

app = FastAPI(title="WebSocket Chat")

app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(ws.router)
app.include_router(users_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)