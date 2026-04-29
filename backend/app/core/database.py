from typing import Any

from app.core.config import get_settings


def postgres_available() -> bool:
    try:
        import psycopg
    except ImportError:
        return False
    settings = get_settings()
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                return cur.fetchone() == (1,)
    except Exception:
        return False


def storage_status() -> dict[str, Any]:
    settings = get_settings()
    status: dict[str, Any] = {
        "backend": settings.storage_backend,
        "json_ready": True,
        "postgres_ready": None,
    }
    if settings.storage_backend == "postgres":
        status["postgres_ready"] = postgres_available()
    return status
