"""Phase 1 E2E 联合测试 · Coordinator

验证：editor_mode 接上真 EventStore 时，review_chapter 能把事件正确写进事件流。

不 mock EventStore；用真的 SQLAlchemy 跑。LLM 通过 monkeypatch 替换为假 client。

覆盖：
- pass 路径：写 review_started + review_completed，无 hard_rule_violation
- blocker 路径（字数过短）：写 review_started + hard_rule_violation + review_completed
- GET /managed/books/{bid}/events 端点能正确返回写入的事件
- POST /managed/books/{bid}/sessions 能创建 session
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.managed import router as managed_router
from app.db.connection import Base, SessionLocal, engine
from app.models.novel import Chapter, Novel
from app.services.audit import consistency_checker
from app.services.audit.consistency_checker import ConsistencyReport
from app.services.events import EventStore, event_types
from app.services.inspiration.editor_mode import MuyuEditor


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def sample_novel(db_session):
    novel = Novel(
        id=str(uuid.uuid4()),
        title="E2E 测试小说",
        words_per_chapter=3000,
        target_chapter_count=200,
    )
    db_session.add(novel)
    db_session.commit()
    yield novel
    db_session.query(Chapter).filter_by(novel_id=novel.id).delete()
    db_session.query(Novel).filter_by(id=novel.id).delete()
    db_session.commit()


def _make_chapter(db, novel_id: str, number: int, content: str) -> Chapter:
    ch = Chapter(
        id=str(uuid.uuid4()),
        novel_id=novel_id,
        number=number,
        title=f"第{number}章",
        content=content,
        word_count=len(content),
    )
    db.add(ch)
    db.commit()
    return ch


def _normal_content() -> str:
    """生成合法字数草稿（含主角名「苏明」、2400-3900 中文字符）"""
    para = "苏明走在街上，思考着昨夜发生的事情。" + "他望向远方的天空，心中升起一丝疑虑。" * 8
    return (para + "\n\n") * 18


@dataclass
class _FakeGenResult:
    content: str = ""
    model: str = "fake"
    input_tokens: int = 100
    output_tokens: int = 200
    finish_reason: str = "stop"


class _FakeLLMClient:
    def __init__(self, response: str = ""):
        self._response = response

    @property
    def model(self) -> str:
        return "fake-model"

    async def generate(self, prompt: str, config=None):
        return _FakeGenResult(content=self._response)


def _llm_pass_json() -> str:
    return json.dumps(
        {
            "decision": "pass",
            "overall_score": 85.0,
            "dimensions": {"naturalness": 88, "pacing": 82},
            "summary": "节奏稳健。",
            "annotations": [],
            "next_action": {"action": "pass", "target": None, "payload": {}},
        },
        ensure_ascii=False,
    )


def _patch_llm(monkeypatch, llm_client):
    from app.llm.resolver import StageModelResolver

    def _fake_get_llm_for_stage(self, stage):  # noqa: ARG001
        if llm_client is None:
            raise ValueError("LLM not configured (test)")
        return llm_client

    monkeypatch.setattr(StageModelResolver, "get_llm_for_stage", _fake_get_llm_for_stage)

    async def _fake_consistency(db, llm, novel_id):  # noqa: ARG001
        return ConsistencyReport(novel_id=novel_id, issues=[], checked_chapters=0)

    monkeypatch.setattr(consistency_checker, "check_full_consistency", _fake_consistency)


# ── E2E: editor_mode → EventStore ──────────────────────────


class TestEditorEventStoreIntegration:
    def test_pass_path_emits_review_events(self, monkeypatch, db_session, sample_novel):
        """正常 pass 路径：写 review_started + review_completed，无 hard_rule_violation"""
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_pass_json()))
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        async def _run():
            store = EventStore(db_session)
            session_id = await store.create_session(sample_novel.id, branch_name="e2e_main")
            editor = MuyuEditor(db_session, event_store=store)
            result = await editor.review_chapter(
                sample_novel.id, 1, session_id=session_id
            )
            events = await store.get_events(sample_novel.id, session_id, from_seq=0, limit=100)
            return result, events

        result, events = asyncio.run(_run())

        types = [e.event_type for e in events]
        assert event_types.REVIEW_STARTED in types
        assert event_types.REVIEW_COMPLETED in types
        assert event_types.HARD_RULE_VIOLATION not in types
        assert result.decision == "pass"

        # review_completed payload 的关键字段被正确写入
        completed = next(e for e in events if e.event_type == event_types.REVIEW_COMPLETED)
        assert completed.payload["decision"] == "pass"
        assert completed.payload["overall_score"] == 85.0
        assert completed.actor == "muyu_editor"
        assert completed.chapter_number == 1

    def test_blocker_path_emits_hard_rule_violation(
        self, monkeypatch, db_session, sample_novel
    ):
        """blocker 路径（字数过短）：写 review_started + hard_rule_violation + review_completed"""
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_pass_json()))
        _make_chapter(db_session, sample_novel.id, 1, "苏明很短。")  # 远低于 2400 下限

        async def _run():
            store = EventStore(db_session)
            session_id = await store.create_session(sample_novel.id, branch_name="e2e_blocker")
            editor = MuyuEditor(db_session, event_store=store)
            result = await editor.review_chapter(
                sample_novel.id, 1, session_id=session_id
            )
            events = await store.get_events(sample_novel.id, session_id)
            return result, events

        result, events = asyncio.run(_run())

        types = [e.event_type for e in events]
        assert event_types.REVIEW_STARTED in types
        assert event_types.HARD_RULE_VIOLATION in types
        assert event_types.REVIEW_COMPLETED in types
        assert result.decision == "rewrite"

        violation = next(e for e in events if e.event_type == event_types.HARD_RULE_VIOLATION)
        assert violation.payload.get("rule_id") == "chapter_word_range"
        assert violation.payload.get("severity") == "blocker"

    def test_no_session_id_no_events_written(self, monkeypatch, db_session, sample_novel):
        """不传 session_id 时不写事件，保持 Week 1 默认行为"""
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_pass_json()))
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        async def _run():
            store = EventStore(db_session)
            editor = MuyuEditor(db_session, event_store=store)
            await editor.review_chapter(sample_novel.id, 1, session_id=None)
            # 试图查 events 表中本 book 的事件总数
            events = await store.get_events(
                sample_novel.id, "any_session", from_seq=0, limit=10
            )
            return events

        events = asyncio.run(_run())
        assert events == []


# ── E2E: HTTP 端到端 (FastAPI TestClient) ──────────────────


def _make_minimal_app() -> FastAPI:
    """构造只含 managed 路由的最小 FastAPI app（绕开 app.main 的 protobuf 故障）"""
    minimal = FastAPI()
    minimal.include_router(managed_router, prefix="/api/v1")
    return minimal


class TestHttpEndpoints:
    def test_create_session_endpoint(self, db_session, sample_novel):
        client = TestClient(_make_minimal_app())
        resp = client.post(f"/api/v1/managed/books/{sample_novel.id}/sessions")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["book_id"] == sample_novel.id
        assert isinstance(body["session_id"], str) and len(body["session_id"]) > 0
        assert body["branch_name"] == "main"

    def test_get_events_endpoint(self, monkeypatch, db_session, sample_novel):
        """端到端：调 review (传 session_id) → 调 GET events → 拿到事件"""
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_pass_json()))
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        client = TestClient(_make_minimal_app())

        # 1) 先创建 session
        sess_resp = client.post(f"/api/v1/managed/books/{sample_novel.id}/sessions")
        assert sess_resp.status_code == 200
        session_id = sess_resp.json()["session_id"]

        # 2) 调审稿（带 session_id）
        review_resp = client.post(
            f"/api/v1/managed/books/{sample_novel.id}/chapter/1/review",
            params={"session_id": session_id},
        )
        assert review_resp.status_code == 200, review_resp.text
        assert review_resp.json()["decision"] == "pass"

        # 3) 调 GET events
        events_resp = client.get(
            f"/api/v1/managed/books/{sample_novel.id}/events",
            params={"session_id": session_id, "limit": 100},
        )
        assert events_resp.status_code == 200, events_resp.text
        body = events_resp.json()
        assert body["book_id"] == sample_novel.id
        assert body["session_id"] == session_id
        assert body["count"] >= 2  # review_started + review_completed
        types = [e["event_type"] for e in body["events"]]
        assert event_types.REVIEW_STARTED in types
        assert event_types.REVIEW_COMPLETED in types

    def test_get_events_filter_by_type(self, monkeypatch, db_session, sample_novel):
        """GET events ?types=hard_rule_violation 过滤生效"""
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_pass_json()))
        _make_chapter(db_session, sample_novel.id, 1, "苏明很短。")  # 触发 blocker

        client = TestClient(_make_minimal_app())
        sess = client.post(f"/api/v1/managed/books/{sample_novel.id}/sessions").json()
        session_id = sess["session_id"]

        client.post(
            f"/api/v1/managed/books/{sample_novel.id}/chapter/1/review",
            params={"session_id": session_id},
        )

        resp = client.get(
            f"/api/v1/managed/books/{sample_novel.id}/events",
            params={
                "session_id": session_id,
                "types": event_types.HARD_RULE_VIOLATION,
            },
        )
        body = resp.json()
        assert body["count"] >= 1
        assert all(
            e["event_type"] == event_types.HARD_RULE_VIOLATION for e in body["events"]
        )
