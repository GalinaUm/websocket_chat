from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "WebSocket Chat"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/websocket_chat"
    redis_url: str = "redis://127.0.0.1:6379/0"
    max_rooms_per_user: int = 20
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()