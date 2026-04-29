from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.deps import require_admin
from app.core.errors import api_error
from app.core.security import utc_now
from app.core.store import store
from app.models.schemas import ExportCreate

router = APIRouter(prefix="/projects/{project_id}/exports", tags=["exports"])


def ensure_project(project_id: str) -> dict:
    project = store.get_item("projects", project_id)
    if not project:
        raise api_error(404, "not_found", "Project not found")
    return project


def selected_drafts(project_id: str, payload: ExportCreate) -> list[dict]:
    drafts = [
        draft
        for draft in store.list_items("drafts")
        if draft["project_id"] == project_id and draft.get("status") == "accepted"
    ]
    if payload.chapter_from is not None:
        drafts = [draft for draft in drafts if draft["chapter_number"] >= payload.chapter_from]
    if payload.chapter_to is not None:
        drafts = [draft for draft in drafts if draft["chapter_number"] <= payload.chapter_to]
    return sorted(drafts, key=lambda item: (item["chapter_number"], item["version"]))


@router.post("", status_code=202)
def create_export(project_id: str, payload: ExportCreate, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    project = ensure_project(project_id)
    drafts = selected_drafts(project_id, payload)
    if not drafts:
        raise api_error(422, "export_no_chapters", "No accepted chapters are available for export")

    export_id = store.new_id("export")
    suffix = "md" if payload.format == "markdown" else "txt"
    file_path = store.export_dir / f"{export_id}.{suffix}"

    parts = [f"# {project['title']}", ""] if payload.format == "markdown" else [project["title"], ""]
    for draft in drafts:
        if payload.format == "markdown":
            parts.extend([f"## {draft['title']}", "", draft["body"], ""])
        else:
            parts.extend([draft["title"], "", draft["body"], ""])
    file_path.write_text("\n".join(parts), encoding="utf-8")

    now = utc_now()
    item = {
        "id": export_id,
        "project_id": project_id,
        "format": payload.format,
        "status": "succeeded",
        "file_ref": str(file_path),
        "failure_message": None,
        "created_at": now,
        "updated_at": now,
    }
    return {"data": store.create_item("exports", item)}


@router.get("/{export_id}")
def get_export(project_id: str, export_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    item = store.get_item("exports", export_id)
    if not item or item["project_id"] != project_id:
        raise api_error(404, "not_found", "Export not found")
    return {"data": item}


@router.get("/{export_id}/file")
def download_export(project_id: str, export_id: str, _: dict[str, str] = Depends(require_admin)) -> FileResponse:
    ensure_project(project_id)
    item = store.get_item("exports", export_id)
    if not item or item["project_id"] != project_id:
        raise api_error(404, "not_found", "Export not found")
    path = Path(item["file_ref"])
    if not path.exists():
        raise api_error(404, "not_found", "Export file not found")
    return FileResponse(path, filename=path.name)
