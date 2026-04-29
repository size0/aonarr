import os
from functools import lru_cache

from pydantic import BaseModel, Field


def env_int(name: str, default: str) -> int:
    return int(os.getenv(name, default))


def env_float(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def cors_origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]


class Settings(BaseModel):
    app_name: str = Field(default_factory=lambda: os.getenv("APP_NAME", "aonarr"))
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    admin_username: str = Field(default_factory=lambda: os.getenv("ADMIN_USERNAME", "admin"))
    admin_password: str = Field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", "change-me"))
    secret_key: str = Field(default_factory=lambda: os.getenv("SECRET_KEY", "dev-secret-change-me"))
    admin_session_ttl_seconds: int = Field(
        default_factory=lambda: env_int("ADMIN_SESSION_TTL_SECONDS", "86400")
    )
    sse_token_ttl_seconds: int = Field(
        default_factory=lambda: env_int("SSE_TOKEN_TTL_SECONDS", "60")
    )
    login_rate_limit_max_attempts: int = Field(
        default_factory=lambda: env_int("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "10")
    )
    login_rate_limit_window_seconds: int = Field(
        default_factory=lambda: env_int("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300")
    )
    data_dir: str = Field(default_factory=lambda: os.getenv("DATA_DIR", "local-data"))
    storage_backend: str = Field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "json"))
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql://aonarr:change-me@localhost:5432/aonarr",
        )
    )
    llm_mode: str = Field(default_factory=lambda: os.getenv("LLM_MODE", "mock"))
    llm_request_timeout_seconds: float = Field(
        default_factory=lambda: env_float("LLM_REQUEST_TIMEOUT_SECONDS", "30")
    )
    revision_max_attempts: int = Field(
        default_factory=lambda: env_int("REVISION_MAX_ATTEMPTS", "1")
    )
    cors_origins: list[str] = Field(default_factory=cors_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
