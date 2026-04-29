from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.errors import api_error
from app.core.store import store
from app.models.schemas import StoryBiblePut

router = APIRouter(prefix="/projects/{project_id}/bible", tags=["story-bible"])


def ensure_project(project_id: str) -> dict:
    project = store.get_item("projects", project_id)
    if not project:
        raise api_error(404, "not_found", "Project not found")
    return project


@router.get("")
def get_bible(project_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict | None]:
    ensure_project(project_id)
    return {"data": store.get_bible(project_id)}


@router.put("")
def put_bible(project_id: str, payload: StoryBiblePut, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    return {"data": store.put_bible(project_id, payload.model_dump())}


@router.get("/readiness")
def readiness(project_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    project = ensure_project(project_id)
    bible = store.get_bible(project_id)
    missing = []
    if not project.get("default_llm_profile_id"):
        missing.append({"section": "llm_profile", "message": "Default LLM profile is required"})
    if not bible:
        missing.append({"section": "story_bible", "message": "Story bible is required"})
    else:
        if not bible.get("premise"):
            missing.append({"section": "premise", "message": "Premise is required"})
        if not bible.get("cast_members"):
            missing.append({"section": "cast_members", "message": "At least one character is required"})
        if not bible.get("plot_lines"):
            missing.append({"section": "plot_lines", "message": "At least one plot line is required"})
    return {"data": {"ready": not missing, "missing": missing}}
