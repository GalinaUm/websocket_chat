from fastapi import FastAPI

from app.api import auth

app = FastAPI(title="WebSocket Chat")

app.include_router(auth.router)