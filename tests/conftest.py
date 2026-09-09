import os
from pathlib import Path

from dotenv import dotenv_values

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# БЕРём DATABASE_URL из .env и подставляем вместо рабочей БД тестовую (websocket_chat_test),
# чтобы не дублировать пароль в коммитимом файле. Если DATABASE_URL уже задана переменной
# окружения (например, в CI) — она в приоритете и не перезаписывается.
_db_url = dotenv_values(BACKEND_ROOT / ".env").get("DATABASE_URL")
if not _db_url:
    _db_url = "postgresql+psycopg://postgres:postgres@localhost:5432/websocket_chat_test"
else:
    _db_url = _db_url.rsplit("/", 1)[0] + "/websocket_chat_test"

# Настраиваем окружение ДО импорта приложения, чтобы engine создался сразу на тестовой БД
os.environ.setdefault("DATABASE_URL", _db_url)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("MAX_ROOMS_PER_USER", "3")
os.environ.setdefault("CORS_ORIGINS", '["http://testserver"]')

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import text

from app.db import Base, engine
from app.main import app


def run_migrations() -> None:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def migrate() -> None:
    run_migrations()


@pytest.fixture(autouse=True)
def clean_db(migrate):
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    Redis.from_url(os.environ["REDIS_URL"], protocol=2).flushdb()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def register_user(client):
    def _register(username: str, email: str | None = None, password: str = "secret123"):
        resp = client.post(
            "/auth/register",
            json={
                "email": email or f"{username}@example.com",
                "username": username,
                "password": password,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()
    return _register


@pytest.fixture()
def get_token(client):
    def _token(username: str, password: str = "secret123") -> str:
        resp = client.post(
            "/auth/login",
            data={"username": username, "password": password},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]
    return _token


@pytest.fixture()
def auth_headers():
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}
    return _headers


@pytest.fixture()
def ws_connect(client):
    def _connect(room_id: int, token: str):
        return client.websocket_connect(f"/ws/rooms/{room_id}?token={token}")
    return _connect