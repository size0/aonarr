from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.errors import api_error
from app.core.security import utc_now
from app.core.store import store
from app.models.schemas import ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(_: dict[str, str] = Depends(require_admin)) -> dict[str, list[dict]]:
    return {"data": store.list_items("projects")}


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    if payload.default_llm_profile_id and not store.get_item("llm_profiles", payload.default_llm_profile_id):
        raise api_error(422, "missing_llm_profile", "Default LLM profile does not exist")
    now = utc_now()
    project = payload.model_dump()
    project.update({"id": store.new_id("proj"), "status": "draft", "created_at": now, "updated_at": now})
    return {"data": store.create_item("projects", project)}


@router.get("/{project_id}")
def get_project(project_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    project = store.get_item("projects", project_id)
    if not project:
        raise api_error(404, "not_found", "Project not found")
    return {"data": project}


@router.patch("/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    patch = payload.model_dump(exclude_unset=True)
    if patch.get("default_llm_profile_id") and not store.get_item("llm_profiles", patch["default_llm_profile_id"]):
        raise api_error(422, "missing_llm_profile", "Default LLM profile does not exist")
    updated = store.update_item("projects", project_id, patch)
    if not updated:
        raise api_error(404, "not_found", "Project not found")
    return {"data": updated}


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, _: dict[str, str] = Depends(require_admin)) -> None:
    if not store.delete_item("projects", project_id):
        raise api_error(404, "not_found", "Project not found")
