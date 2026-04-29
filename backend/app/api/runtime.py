from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.config import get_settings

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/settings")
def runtime_settings(_: dict[str, str] = Depends(require_admin)) -> dict[str, dict[str, str | int]]:
    settings = get_settings()
    return {
        "data": {
            "llm_mode": settings.llm_mode,
            "revision_max_attempts": settings.revision_max_attempts,
            "storage_backend": settings.storage_backend,
        }
    }
