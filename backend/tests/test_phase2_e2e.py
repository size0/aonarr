"""Phase 2 HTTP E2E · Track F · Week 3 · Claude-C

通过 TestClient + 最小 FastAPI app 验证 daemon 控制端点路由 wiring。

设计说明：
- TestClient 在 anyio portal 下跑 ASGI；endpoint 里 ``asyncio.create_task``
  会被结构化并发当作子任务，请求结束时会被取消。这是 TestClient 限制
  （生产 uvicorn 下不会有此问题）。
- 因此 HTTP 测试用 ``StubPool`` 替换真 ``DaemonPool``，只验证路由 →
  pool 方法调用 → 异常映射；daemon 实际生命周期的并发/事件/恢复语义
  已在 test_book_daemon.py / test_llm_quota.py 中完整覆盖。
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.managed import _get_pool, router as managed_router
from app.db.connection import Base, SessionLocal, engine
from app.models.book_state import BookState
from app.services.agents.daemon_pool import reset_default_pool


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_default_pool()
    yield
    reset_default_pool()


class _StubDaemon:
    def __init__(self, book_id: str, state: str = "running"):
        self.book_id = book_id
        self.state = type("S", (), {"value": state})()
        self._info: dict[str, Any] = {
            "book_id": book_id,
            "session_id": "stub",
            "state": state,
            "chapters_completed": 0,
            "words_written": 0,
            "last_error": None,
            "last_message": None,
        }

    def status(self) -> dict[str, Any]:
        self._info["state"] = self.state.value
        return self._info


class _StubPool:
    """记录调用 + 可控错误注入的假 DaemonPool。"""

    def __init__(self):
        self._daemons: dict[str, _StubDaemon] = {}
        self.calls: list[tuple[str, str]] = []  # [(method, book_id), ...]
        # 行为开关
        self.raise_on_spawn: Exception | None = None
        self.raise_on_pause: Exception | None = None
        self.raise_on_stop: Exception | None = None

    async def spawn(self, book_id, session_id, start_chapter, end_chapter, **kw):
        self.calls.append(("spawn", book_id))
        if self.raise_on_spawn:
            raise self.raise_on_spawn
        if book_id in self._daemons:
            raise RuntimeError(f"book {book_id} 已有 daemon")
        d = _StubDaemon(book_id, "running")
        self._daemons[book_id] = d
        return d

    async def pause(self, book_id):
        self.calls.append(("pause", book_id))
        if self.raise_on_pause:
            raise self.raise_on_pause
        if book_id not in self._daemons:
            raise KeyError(book_id)
        self._daemons[book_id].state.value = "paused"

    async def resume(self, book_id):
        self.calls.append(("resume", book_id))
        if book_id not in self._daemons:
            raise KeyError(book_id)
        self._daemons[book_id].state.value = "running"

    async def stop(self, book_id, wait=True, timeout=30.0):
        self.calls.append(("stop", book_id))
        if self.raise_on_stop:
            raise self.raise_on_stop
        if book_id not in self._daemons:
            raise KeyError(book_id)
        self._daemons[book_id].state.value = "stopped"

    def get(self, book_id):
        return self._daemons.get(book_id)

    def list_states(self):
        return [d.status() for d in self._daemons.values()]

    def stats(self):
        return {
            "daemon_count": len(self._daemons),
            "quota": {"capacity": 4, "in_flight": 0, "queued": 0,
                      "per_book": {}, "window_seconds": 0, "window_used": 0},
            "books": [{"book_id": b, "state": d.state.value}
                      for b, d in self._daemons.items()],
        }


def _make_app(stub_pool: _StubPool | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(managed_router, prefix="/api/v1")
    if stub_pool is not None:
        app.dependency_overrides[_get_pool] = lambda: stub_pool
    return app


def _bid() -> str:
    return f"book_{uuid.uuid4().hex[:8]}"


class TestDaemonHttpEndpoints:
    """HTTP 路由 + 入参校验 + 异常映射；用 StubPool 隔离 asyncio 生命周期。"""

    def test_start_returns_200_and_status(self):
        pool = _StubPool()
        client = TestClient(_make_app(pool))
        book_id = _bid()
        r = client.post(
            f"/api/v1/managed/books/{book_id}/daemon/start",
            json={
                "session_id": "sess",
                "start_chapter": 1,
                "end_chapter": 5,
                "priority": 3,
                "heartbeat_interval": 5.0,
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "running"
        assert ("spawn", book_id) in pool.calls

    def test_start_invalid_body_returns_422(self):
        client = TestClient(_make_app(_StubPool()))
        r = client.post(
            "/api/v1/managed/books/b1/daemon/start",
            json={"session_id": "x"},  # 缺 start/end_chapter
        )
        assert r.status_code == 422

    def test_start_value_error_returns_400(self):
        pool = _StubPool()
        pool.raise_on_spawn = ValueError("章节范围非法")
        client = TestClient(_make_app(pool))
        r = client.post(
            "/api/v1/managed/books/b1/daemon/start",
            json={"session_id": "x", "start_chapter": 0, "end_chapter": 5},
        )
        assert r.status_code == 400

    def test_start_double_returns_409(self):
        pool = _StubPool()
        client = TestClient(_make_app(pool))
        book_id = _bid()
        body = {"session_id": "s", "start_chapter": 1, "end_chapter": 5}
        r1 = client.post(f"/api/v1/managed/books/{book_id}/daemon/start", json=body)
        assert r1.status_code == 200
        r2 = client.post(f"/api/v1/managed/books/{book_id}/daemon/start", json=body)
        assert r2.status_code == 409

    def test_pause_resume_stop_chain(self):
        pool = _StubPool()
        client = TestClient(_make_app(pool))
        book_id = _bid()
        # 先 start 一次（StubPool 直接登记）
        client.post(
            f"/api/v1/managed/books/{book_id}/daemon/start",
            json={"session_id": "s", "start_chapter": 1, "end_chapter": 5},
        )

        r = client.post(f"/api/v1/managed/books/{book_id}/daemon/pause")
        assert r.status_code == 200
        assert r.json()["state"] == "paused"

        r = client.post(f"/api/v1/managed/books/{book_id}/daemon/resume")
        assert r.status_code == 200
        assert r.json()["state"] == "running"

        r = client.post(
            f"/api/v1/managed/books/{book_id}/daemon/stop",
            params={"wait": False, "timeout": 1.0},
        )
        assert r.status_code == 200
        assert r.json()["state"] == "stopped"

        assert [c[0] for c in pool.calls] == ["spawn", "pause", "resume", "stop"]

    def test_pause_unknown_returns_404(self):
        client = TestClient(_make_app(_StubPool()))
        r = client.post("/api/v1/managed/books/never_started/daemon/pause")
        assert r.status_code == 404

    def test_pause_runtime_error_returns_409(self):
        pool = _StubPool()
        # 先 spawn 让 daemon 存在
        body = {"session_id": "s", "start_chapter": 1, "end_chapter": 2}
        client = TestClient(_make_app(pool))
        client.post("/api/v1/managed/books/b1/daemon/start", json=body)
        pool.raise_on_pause = RuntimeError("只有 RUNNING 才能 pause")
        r = client.post("/api/v1/managed/books/b1/daemon/pause")
        assert r.status_code == 409

    def test_stop_unknown_returns_404(self):
        client = TestClient(_make_app(_StubPool()))
        r = client.post("/api/v1/managed/books/never_started/daemon/stop")
        assert r.status_code == 404

    def test_get_state_unknown_returns_404(self):
        # 不需要 StubPool —— get_state 走真实 DB
        client = TestClient(_make_app(_StubPool()))
        r = client.get("/api/v1/managed/books/no_such_book/state")
        assert r.status_code == 404

    def test_get_state_returns_row_when_exists(self):
        from datetime import datetime, timezone
        from app.models.book_state import (
            DAEMON_RUNNING, PHASE_COLD_START,
        )

        client = TestClient(_make_app(_StubPool()))
        book_id = _bid()
        # 手动写一行 BookState
        db = SessionLocal()
        try:
            row = BookState(
                book_id=book_id,
                phase=PHASE_COLD_START,
                current_chapter=3,
                target_chapter_count=10,
                daemon_status=DAEMON_RUNNING,
                llm_quota_used=5,
                llm_quota_max=100,
                updated_at=datetime.now(timezone.utc),
            )
            db.add(row)
            db.commit()
        finally:
            db.close()

        try:
            r = client.get(f"/api/v1/managed/books/{book_id}/state")
            assert r.status_code == 200
            body = r.json()
            assert body["book_id"] == book_id
            assert body["current_chapter"] == 3
            assert body["daemon_status"] == DAEMON_RUNNING
            assert body["llm_quota_used"] == 5
        finally:
            _cleanup_book_state(book_id)

    def test_list_daemons_endpoint(self):
        pool = _StubPool()
        client = TestClient(_make_app(pool))
        body = {"session_id": "s", "start_chapter": 1, "end_chapter": 5}
        b1, b2 = _bid(), _bid()
        client.post(f"/api/v1/managed/books/{b1}/daemon/start", json=body)
        client.post(f"/api/v1/managed/books/{b2}/daemon/start", json=body)

        r = client.get("/api/v1/managed/daemons")
        assert r.status_code == 200
        data = r.json()
        assert data["stats"]["daemon_count"] == 2
        book_ids = {d["book_id"] for d in data["daemons"]}
        assert book_ids == {b1, b2}


def _cleanup_book_state(book_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(BookState).filter_by(book_id=book_id).delete()
        db.commit()
    finally:
        db.close()
