from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.errors import api_error
from app.core.store import store

router = APIRouter(prefix="/projects/{project_id}", tags=["costs"])


def ensure_project(project_id: str) -> dict:
    project = store.get_item("projects", project_id)
    if not project:
        raise api_error(404, "not_found", "Project not found")
    return project


@router.get("/cost-summary")
def project_cost_summary(project_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    project = ensure_project(project_id)
    runs = [run for run in store.list_items("runs") if run["project_id"] == project_id]
    drafts = [draft for draft in store.list_items("drafts") if draft["project_id"] == project_id]
    total_cost = round(sum(float(run.get("estimated_cost") or 0) for run in runs), 4)
    return {
        "data": {
            "project_id": project_id,
            "estimated_total_cost": total_cost,
            "cost_limit_total": project.get("cost_limit_total"),
            "remaining": None if project.get("cost_limit_total") is None else round(float(project["cost_limit_total"]) - total_cost, 4),
            "run_count": len(runs),
            "chapter_count": len({draft["chapter_number"] for draft in drafts}),
            "breakdown_by_run": [
                {
                    "serial_run_id": run["id"],
                    "estimated_cost": run.get("estimated_cost", 0),
                    "completed_chapter_count": run.get("completed_chapter_count", 0),
                    "status": run.get("status"),
                }
                for run in runs
            ],
        }
    }


@router.get("/runs/{run_id}/cost-summary")
def run_cost_summary(project_id: str, run_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    ensure_project(project_id)
    run = store.get_item("runs", run_id)
    if not run or run["project_id"] != project_id:
        raise api_error(404, "not_found", "Serial run not found")
    events = store.list_run_events(run_id)
    return {
        "data": {
            "project_id": project_id,
            "serial_run_id": run_id,
            "estimated_cost": run.get("estimated_cost", 0),
            "cost_limit": run.get("cost_limit"),
            "completed_chapter_count": run.get("completed_chapter_count", 0),
            "token_input": sum(int(event.get("token_input") or 0) for event in events),
            "token_output": sum(int(event.get("token_output") or 0) for event in events),
        }
    }
