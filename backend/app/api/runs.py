import json
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import require_admin, require_sse_admin
from app.core.errors import api_error
from app.core.security import utc_now
from app.core.store import store
from app.models.schemas import SerialRunCreate
from app.services.serial_engine import emit, start_run_worker

router = APIRouter(prefix="/projects/{project_id}/runs", tags=["serial-runs"])


def ensure_project(project_id: str) -> dict:
    project = store.get_item("projects", project_id)
    if not project:
        raise api_error(404, "not_found", "Project not found")
    return project


def assert_ready(project: dict) -> None:
    if not project.get("default_llm_profile_id"):
        raise api_error(422, "missing_llm_profile", "Default LLM profile is required")
    bible = store.get_bible(project["id"])
    if not bible or not bible.get("premise") or not bible.get("cast_members") or not bible.get("plot_lines"):
        raise api_error(422, "bible_not_ready", "Story bible is incomplete")


@router.get("")
def list_runs(project_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, list[dict]]:
    ensure_project(project_id)
    runs = [run for run in store.list_items("runs") if run["project_id"] == project_id]
    return {"data": sorted(runs, key=lambda item: item["created_at"], reverse=True)}


@router.post("", status_code=201)
def create_run(project_id: str, payload: SerialRunCreate, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    project = ensure_project(project_id)
    assert_ready(project)
    if store.active_run_for_project(project_id):
        raise api_error(409, "run_already_active", "Project already has an active serial run")
    llm_profile_id = payload.llm_profile_id or project.get("default_llm_profile_id")
    if not llm_profile_id or not store.get_item("llm_profiles", llm_profile_id):
        raise api_error(422, "missing_llm_profile", "LLM profile does not exist")
    now = utc_now()
    run = payload.model_dump()
    run.update(
        {
            "id": store.new_id("run"),
            "project_id": project_id,
            "llm_profile_id": llm_profile_id,
            "status": "queued",
            "completed_chapter_count": 0,
            "estimated_cost": 0,
            "failure_code": None,
            "failure_message": None,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
        }
    )
    saved = store.create_item("runs", run)
    emit(saved, "info", "run_queued", "Serial run queued")
    start_run_worker(saved["id"])
    return {"data": saved}


@router.get("/{run_id}")
def get_run(project_id: str, run_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    run = store.get_item("runs", run_id)
    if not run or run["project_id"] != project_id:
        raise api_error(404, "not_found", "Serial run not found")
    return {"data": run}


@router.post("/{run_id}/pause")
def pause_run(project_id: str, run_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    run = store.get_item("runs", run_id)
    if not run or run["project_id"] != project_id:
        raise api_error(404, "not_found", "Serial run not found")
    if run["status"] in {"succeeded", "failed", "cancelled"}:
        raise api_error(409, "invalid_run_state", "Terminal run cannot be paused")
    updated = store.update_item("runs", run_id, {"status": "paused", "failure_code": "user_paused", "failure_message": "Paused by user"})
    emit(updated, "warn", "run_paused", "Run paused by user")
    return {"data": updated}


@router.post("/{run_id}/resume")
def resume_run(project_id: str, run_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    run = store.get_item("runs", run_id)
    if not run or run["project_id"] != project_id:
        raise api_error(404, "not_found", "Serial run not found")
    if run["status"] != "paused":
        raise api_error(409, "invalid_run_state", "Only paused runs can be resumed")
    updated = store.update_item("runs", run_id, {"status": "queued", "failure_code": None, "failure_message": None})
    emit(updated, "info", "run_resumed", "Run resumed by user")
    start_run_worker(run_id)
    return {"data": updated}


@router.post("/{run_id}/cancel")
def cancel_run(project_id: str, run_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    run = store.get_item("runs", run_id)
    if not run or run["project_id"] != project_id:
        raise api_error(404, "not_found", "Serial run not found")
    if run["status"] in {"succeeded", "failed", "cancelled"}:
        raise api_error(409, "invalid_run_state", "Terminal run cannot be cancelled")
    updated = store.update_item("runs", run_id, {"status": "cancelled", "finished_at": utc_now()})
    emit(updated, "warn", "run_cancelled", "Run cancelled by user")
    return {"data": updated}


@router.get("/{run_id}/events")
def list_events(project_id: str, run_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, list[dict]]:
    ensure_project(project_id)
    run = store.get_item("runs", run_id)
    if not run or run["project_id"] != project_id:
        raise api_error(404, "not_found", "Serial run not found")
    return {"data": store.list_run_events(run_id)}


@router.get("/{run_id}/events/stream")
def stream_events(project_id: str, run_id: str, _: dict[str, str] = Depends(require_sse_admin)) -> StreamingResponse:
    ensure_project(project_id)
    run = store.get_item("runs", run_id)
    if not run or run["project_id"] != project_id:
        raise api_error(404, "not_found", "Serial run not found")

    def event_generator():
        sent: set[str] = set()
        heartbeat_counter = 0
        while True:
            events = store.list_run_events(run_id)
            for event in events:
                if event["id"] in sent:
                    continue
                sent.add(event["id"])
                yield f"event: run_event\nid: {event['id']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            heartbeat_counter += 1
            if heartbeat_counter >= 10:
                heartbeat_counter = 0
                yield f"event: heartbeat\ndata: {json.dumps({'ts': utc_now()})}\n\n"
            current = store.get_item("runs", run_id)
            if current and current["status"] in {"succeeded", "failed", "cancelled"} and len(sent) >= len(store.list_run_events(run_id)):
                break
            time.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
