from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "WebSocket Chat"
    database_url: str = "postgresql+psycopg://postgres:1234@localhost:5432/websocket_chat"


settings = Settings()