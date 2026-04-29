from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.errors import api_error
from app.core.security import utc_now
from app.core.store import store
from app.models.schemas import ChapterDraftUpdate, ChapterPlanUpdate
from app.services.serial_engine import emit

router = APIRouter(prefix="/projects/{project_id}", tags=["chapters"])


def ensure_project(project_id: str) -> None:
    if not store.get_item("projects", project_id):
        raise api_error(404, "not_found", "Project not found")


@router.get("/plans")
def list_plans(project_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, list[dict]]:
    ensure_project(project_id)
    plans = [plan for plan in store.list_items("plans") if plan["project_id"] == project_id]
    return {"data": sorted(plans, key=lambda item: item["chapter_number"])}


@router.get("/plans/{plan_id}")
def get_plan(project_id: str, plan_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    plan = store.get_item("plans", plan_id)
    if not plan or plan["project_id"] != project_id:
        raise api_error(404, "not_found", "Chapter plan not found")
    return {"data": plan}


@router.patch("/plans/{plan_id}")
def update_plan(project_id: str, plan_id: str, payload: ChapterPlanUpdate, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    plan = store.get_item("plans", plan_id)
    if not plan or plan["project_id"] != project_id:
        raise api_error(404, "not_found", "Chapter plan not found")
    updated = store.update_item("plans", plan_id, payload.model_dump(exclude_unset=True))
    return {"data": updated}


@router.get("/drafts")
def list_drafts(project_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, list[dict]]:
    ensure_project(project_id)
    drafts = [draft for draft in store.list_items("drafts") if draft["project_id"] == project_id]
    return {"data": sorted(drafts, key=lambda item: (item["chapter_number"], item["version"]))}


@router.get("/drafts/{draft_id}")
def get_draft(project_id: str, draft_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    draft = store.get_item("drafts", draft_id)
    if not draft or draft["project_id"] != project_id:
        raise api_error(404, "not_found", "Chapter draft not found")
    return {"data": draft}


@router.patch("/drafts/{draft_id}")
def update_draft(project_id: str, draft_id: str, payload: ChapterDraftUpdate, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    draft = store.get_item("drafts", draft_id)
    if not draft or draft["project_id"] != project_id:
        raise api_error(404, "not_found", "Chapter draft not found")
    patch = payload.model_dump(exclude_unset=True)
    if "body" in patch:
        patch["word_count"] = len(patch["body"])
    updated = store.update_item("drafts", draft_id, patch)
    return {"data": updated}


@router.post("/drafts/{draft_id}/accept")
def accept_draft(project_id: str, draft_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    draft = store.get_item("drafts", draft_id)
    if not draft or draft["project_id"] != project_id:
        raise api_error(404, "not_found", "Chapter draft not found")
    updated_draft = store.update_item(
        "drafts",
        draft_id,
        {
            "status": "accepted",
            "review_summary": "Accepted by user after manual review.",
            "quality_score": draft.get("quality_score") or 7.0,
        },
    )
    run = store.get_item("runs", draft["serial_run_id"])
    if run and run["project_id"] == project_id and run.get("failure_code") == "quality_gate_needs_revision":
        expected_chapter = int(run["start_chapter_number"]) + int(run.get("completed_chapter_count") or 0)
        patch = {
            "failure_code": None,
            "failure_message": None,
        }
        if int(draft["chapter_number"]) == expected_chapter:
            patch["completed_chapter_count"] = int(run.get("completed_chapter_count") or 0) + 1
        if int(patch.get("completed_chapter_count", run.get("completed_chapter_count") or 0)) >= int(run["target_chapter_count"]):
            patch["status"] = "succeeded"
            patch["finished_at"] = utc_now()
        advanced = store.update_item("runs", run["id"], patch)
        emit(advanced, "info", "draft_manually_accepted", f"Chapter {draft['chapter_number']} accepted by user", step="reviewing", chapter_number=draft["chapter_number"])
    return {"data": updated_draft}


@router.get("/chapters/{chapter_number}/versions")
def chapter_versions(project_id: str, chapter_number: int, _: dict[str, str] = Depends(require_admin)) -> dict[str, list[dict]]:
    ensure_project(project_id)
    drafts = [
        draft
        for draft in store.list_items("drafts")
        if draft["project_id"] == project_id and draft["chapter_number"] == chapter_number
    ]
    return {"data": sorted(drafts, key=lambda item: item["version"])}
