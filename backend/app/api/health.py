from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from app.core.database import storage_status

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, dict[str, Any]]:
    return {
        "data": {
            "status": "ok",
            "service": "aonarr-api",
            "time": datetime.now(UTC).isoformat(),
            "storage": storage_status(),
        }
    }
