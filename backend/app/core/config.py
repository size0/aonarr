import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "aonarr")
    app_env: str = os.getenv("APP_ENV", "development")
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "change-me")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    data_dir: str = os.getenv("DATA_DIR", "local-data")
    storage_backend: str = os.getenv("STORAGE_BACKEND", "json")
    database_url: str = os.getenv("DATABASE_URL", "postgresql://serial_writer:change-me@localhost:5432/serial_writer")
    llm_mode: str = os.getenv("LLM_MODE", "mock")
    llm_request_timeout_seconds: float = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "30"))
    revision_max_attempts: int = int(os.getenv("REVISION_MAX_ATTEMPTS", "1"))
    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
