import json
import threading
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.security import utc_now


DEFAULT_DATA: dict[str, Any] = {
    "sessions": {},
    "llm_profiles": [],
    "projects": [],
    "bibles": {},
    "runs": [],
    "events": [],
    "plans": [],
    "drafts": [],
    "exports": [],
    "prompt_templates": [],
}


class JsonStore:
    def __init__(self) -> None:
        settings = get_settings()
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir = self.data_dir / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "app-data.json"
        self.lock = threading.RLock()
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.path.write_text(json.dumps(DEFAULT_DATA, indent=2), encoding="utf-8")
            return deepcopy(DEFAULT_DATA)
        loaded = json.loads(self.path.read_text(encoding="utf-8"))
        data = deepcopy(DEFAULT_DATA)
        data.update(loaded)
        return data

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    def create_session(self, token: str, username: str, expires_at: str, token_type: str = "bearer") -> None:
        with self.lock:
            self.data["sessions"][token] = {
                "username": username,
                "token_type": token_type,
                "created_at": utc_now(),
                "expires_at": expires_at,
            }
            self._save()

    def delete_session(self, token: str) -> None:
        with self.lock:
            self.data["sessions"].pop(token, None)
            self._save()

    def get_session(self, token: str) -> dict[str, Any] | None:
        with self.lock:
            session = self.data["sessions"].get(token)
            if not session:
                return None
            expires_at = session.get("expires_at")
            if not expires_at:
                self.data["sessions"].pop(token, None)
                self._save()
                return None
            try:
                expires_at_dt = datetime.fromisoformat(expires_at)
            except ValueError:
                self.data["sessions"].pop(token, None)
                self._save()
                return None
            if expires_at_dt.tzinfo is None:
                expires_at_dt = expires_at_dt.replace(tzinfo=UTC)
            if expires_at_dt <= datetime.now(UTC):
                self.data["sessions"].pop(token, None)
                self._save()
                return None
            return deepcopy(session)

    def list_items(self, collection: str) -> list[dict[str, Any]]:
        with self.lock:
            return deepcopy(self.data[collection])

    def get_item(self, collection: str, item_id: str) -> dict[str, Any] | None:
        with self.lock:
            for item in self.data[collection]:
                if item["id"] == item_id:
                    return deepcopy(item)
            return None

    def create_item(self, collection: str, item: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.data[collection].append(deepcopy(item))
            self._save()
            return deepcopy(item)

    def update_item(self, collection: str, item_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self.lock:
            for index, item in enumerate(self.data[collection]):
                if item["id"] == item_id:
                    updated = {**item, **patch, "updated_at": utc_now()}
                    self.data[collection][index] = updated
                    self._save()
                    return deepcopy(updated)
            return None

    def delete_item(self, collection: str, item_id: str) -> bool:
        with self.lock:
            before = len(self.data[collection])
            self.data[collection] = [item for item in self.data[collection] if item["id"] != item_id]
            changed = len(self.data[collection]) != before
            if changed:
                self._save()
            return changed

    def get_bible(self, project_id: str) -> dict[str, Any] | None:
        with self.lock:
            bible = self.data["bibles"].get(project_id)
            return deepcopy(bible) if bible else None

    def put_bible(self, project_id: str, bible: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            current = self.data["bibles"].get(project_id)
            version = int(current.get("version", 0)) + 1 if current else 1
            saved = {
                **bible,
                "id": current.get("id") if current else self.new_id("bible"),
                "project_id": project_id,
                "version": version,
                "created_at": current.get("created_at") if current else utc_now(),
                "updated_at": utc_now(),
            }
            self.data["bibles"][project_id] = saved
            self._save()
            return deepcopy(saved)

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            saved = {
                "id": self.new_id("evt"),
                "created_at": utc_now(),
                **event,
            }
            self.data["events"].append(saved)
            self._save()
            return deepcopy(saved)

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        with self.lock:
            return deepcopy([event for event in self.data["events"] if event["serial_run_id"] == run_id])

    def active_run_for_project(self, project_id: str) -> dict[str, Any] | None:
        active_statuses = {"queued", "planning", "drafting", "reviewing"}
        with self.lock:
            for run in self.data["runs"]:
                if run["project_id"] == project_id and run["status"] in active_statuses:
                    return deepcopy(run)
            return None


store = JsonStore()
