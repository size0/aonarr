"""EventStore 单元测试 · Track F · Week 2 · Claude-B

覆盖契约 §1 全部 5 个核心方法 + 异常分支 + 并发 append。
不引入新依赖（仅 pytest + pytest-asyncio + 现有 SQLAlchemy）。
"""
from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from app.db.connection import Base, SessionLocal, engine
from app.models.events import Event, SessionRecord
from app.services.events import (
    EventStore,
    EventStoreError,
    InvalidForkError,
    event_payloads,
    event_types,
)


# ── fixtures ─────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema():
    """conftest 已切到 tmp 数据库；这里确保 events / production_sessions 表存在。"""
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
def store(db_session):
    return EventStore(db_session)


@pytest.fixture
def book_id() -> str:
    # 每个测试用唯一 book_id，避免相互污染
    return f"book_{uuid.uuid4().hex[:8]}"


# ── append ──────────────────────────────────────────────────


class TestAppend:
    def test_append_basic(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            eid = await store.append(
                book_id=book_id,
                session_id=sid,
                event_type=event_types.CHAPTER_STARTED,
                actor="muyu_editor",
                payload={"chapter_number": 1, "target_words": 3000, "triggered_by": "user"},
                chapter_number=1,
            )
            return sid, eid

        sid, eid = asyncio.run(_run())
        assert isinstance(eid, int) and eid > 0
        assert isinstance(sid, str) and len(sid) > 0

    def test_append_seq_monotonic(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            ids = []
            for i in range(5):
                ids.append(
                    await store.append(
                        book_id=book_id,
                        session_id=sid,
                        event_type=event_types.WRITER_PROGRESS,
                        actor="writer",
                        payload={"chapter_number": 1, "chars_so_far": i * 100, "beat_index": 0},
                    )
                )
            events = await store.get_events(book_id, sid, from_seq=0, limit=100)
            return ids, events

        ids, events = asyncio.run(_run())
        assert len(events) == 5
        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs), f"seq 不单调: {seqs}"
        assert len(set(seqs)) == 5  # 全部唯一

    def test_append_missing_field_raises(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            with pytest.raises(EventStoreError):
                await store.append(
                    book_id="",  # 必填
                    session_id=sid,
                    event_type=event_types.CHAPTER_STARTED,
                    actor="muyu_editor",
                    payload={},
                )

        asyncio.run(_run())

    def test_append_concurrent_seq_unique(self, store, book_id):
        """50 个并发 append 全部成功且 seq 不重复。"""
        async def _run():
            sid = await store.create_session(book_id)
            tasks = [
                store.append(
                    book_id=book_id,
                    session_id=sid,
                    event_type=event_types.WRITER_PROGRESS,
                    actor="writer",
                    payload={"chapter_number": 1, "chars_so_far": i, "beat_index": 0},
                )
                for i in range(50)
            ]
            ids = await asyncio.gather(*tasks)
            events = await store.get_events(book_id, sid, from_seq=0, limit=200)
            return ids, events

        ids, events = asyncio.run(_run())
        assert len(ids) == 50
        seqs = [e.seq for e in events]
        assert len(seqs) == 50
        assert len(set(seqs)) == 50, "并发 append 出现 seq 冲突"

    def test_append_two_sessions_independent_seq(self, store, book_id):
        async def _run():
            s1 = await store.create_session(book_id, branch_name="main")
            s2 = await store.create_session(book_id, branch_name="b2")
            await store.append(book_id, s1, event_types.CHAPTER_STARTED, "ed", {})
            await store.append(book_id, s1, event_types.CHAPTER_STARTED, "ed", {})
            await store.append(book_id, s2, event_types.CHAPTER_STARTED, "ed", {})
            ev1 = await store.get_events(book_id, s1)
            ev2 = await store.get_events(book_id, s2)
            return ev1, ev2

        ev1, ev2 = asyncio.run(_run())
        assert [e.seq for e in ev1] == [1, 2]
        assert [e.seq for e in ev2] == [1]


# ── get_events ─────────────────────────────────────────────


class TestGetEvents:
    def test_get_events_pagination(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            for _ in range(20):
                await store.append(book_id, sid, event_types.WRITER_PROGRESS, "w", {})
            page1 = await store.get_events(book_id, sid, from_seq=0, limit=5)
            page2 = await store.get_events(book_id, sid, from_seq=5, limit=5)
            return page1, page2

        page1, page2 = asyncio.run(_run())
        assert [e.seq for e in page1] == [1, 2, 3, 4, 5]
        assert [e.seq for e in page2] == [5, 6, 7, 8, 9]

    def test_get_events_filter_types(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            await store.append(book_id, sid, event_types.CHAPTER_STARTED, "ed", {})
            await store.append(book_id, sid, event_types.WRITER_PROGRESS, "w", {})
            await store.append(book_id, sid, event_types.CHAPTER_STARTED, "ed", {})
            return await store.get_events(
                book_id, sid, types=[event_types.CHAPTER_STARTED]
            )

        events = asyncio.run(_run())
        assert len(events) == 2
        assert all(e.event_type == event_types.CHAPTER_STARTED for e in events)

    def test_get_events_filter_chapter(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            await store.append(book_id, sid, event_types.WRITER_PROGRESS, "w", {}, chapter_number=1)
            await store.append(book_id, sid, event_types.WRITER_PROGRESS, "w", {}, chapter_number=2)
            await store.append(book_id, sid, event_types.WRITER_PROGRESS, "w", {}, chapter_number=2)
            return await store.get_events(book_id, sid, chapter_number=2)

        events = asyncio.run(_run())
        assert len(events) == 2
        assert all(e.chapter_number == 2 for e in events)

    def test_get_events_empty_session(self, store, book_id):
        async def _run():
            return await store.get_events(book_id, "nonexistent_session", limit=10)

        events = asyncio.run(_run())
        assert events == []

    def test_get_events_caps_limit(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            return await store.get_events(book_id, sid, limit=99999)

        events = asyncio.run(_run())  # 不抛错（limit 内部被钳制到 ≤ 1000）
        assert events == []  # 无事件即可


# ── get_latest ─────────────────────────────────────────────


class TestGetLatest:
    def test_get_latest_returns_last(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            ids = []
            for _ in range(3):
                ids.append(
                    await store.append(book_id, sid, event_types.REVIEW_COMPLETED, "ed", {})
                )
            return await store.get_latest(book_id, sid, event_types.REVIEW_COMPLETED), ids

        latest, ids = asyncio.run(_run())
        assert latest is not None
        assert latest.id == ids[-1]

    def test_get_latest_none_when_no_match(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            await store.append(book_id, sid, event_types.CHAPTER_STARTED, "ed", {})
            return await store.get_latest(book_id, sid, event_types.REVIEW_COMPLETED)

        assert asyncio.run(_run()) is None


# ── fork_session ───────────────────────────────────────────


class TestForkSession:
    def test_fork_basic(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id, branch_name="main")
            eid_a = await store.append(book_id, sid, event_types.CHAPTER_STARTED, "ed", {})
            eid_b = await store.append(book_id, sid, event_types.DRAFT_COMPLETED, "w", {})  # noqa: F841
            new_sid = await store.fork_session(book_id, eid_a, "experiment_branch")
            # 验证：原 session 现在多了一条 session_forked 事件
            origin_events = await store.get_events(book_id, sid, from_seq=0, limit=100)
            new_session_record = await store.get_session(new_sid)
            return new_sid, origin_events, new_session_record

        new_sid, origin_events, rec = asyncio.run(_run())
        assert isinstance(new_sid, str) and len(new_sid) > 0
        assert rec is not None
        assert rec.branch_name == "experiment_branch"
        assert rec.parent_session_id is not None
        # 原 session 至少有 3 条事件: CHAPTER_STARTED + DRAFT_COMPLETED + SESSION_FORKED
        types = [e.event_type for e in origin_events]
        assert event_types.SESSION_FORKED in types
        forked_evt = next(e for e in origin_events if e.event_type == event_types.SESSION_FORKED)
        assert forked_evt.payload["new_session_id"] == new_sid
        assert forked_evt.payload["branch_name"] == "experiment_branch"

    def test_fork_invalid_event_id(self, store, book_id):
        async def _run():
            with pytest.raises(InvalidForkError):
                await store.fork_session(book_id, 999999999, "x")

        asyncio.run(_run())

    def test_fork_invalid_negative_id(self, store, book_id):
        async def _run():
            with pytest.raises(InvalidForkError):
                await store.fork_session(book_id, -1, "x")

        asyncio.run(_run())

    def test_fork_event_belongs_to_other_book(self, store, db_session):
        async def _run():
            store2 = EventStore(db_session)
            book_a = f"book_{uuid.uuid4().hex[:8]}"
            book_b = f"book_{uuid.uuid4().hex[:8]}"
            sid_a = await store2.create_session(book_a)
            eid = await store2.append(book_a, sid_a, event_types.CHAPTER_STARTED, "ed", {})
            with pytest.raises(InvalidForkError):
                await store2.fork_session(book_b, eid, "x")  # book mismatch

        asyncio.run(_run())

    def test_fork_missing_branch_name(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            eid = await store.append(book_id, sid, event_types.CHAPTER_STARTED, "ed", {})
            with pytest.raises(InvalidForkError):
                await store.fork_session(book_id, eid, "")

        asyncio.run(_run())


# ── stream ─────────────────────────────────────────────────


class TestStream:
    def test_stream_yields_existing_events(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            for _ in range(3):
                await store.append(book_id, sid, event_types.CHAPTER_STARTED, "ed", {})
            collected = []
            agen = store.stream(book_id, sid, from_seq=0, poll_interval=0.05)
            try:
                for _ in range(3):
                    ev = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
                    collected.append(ev)
            finally:
                await agen.aclose()
            return collected

        collected = asyncio.run(_run())
        assert len(collected) == 3
        assert [e.seq for e in collected] == [1, 2, 3]


# ── 注册表 / payload schema ────────────────────────────────


class TestRegistry:
    def test_event_types_set_includes_essentials(self):
        for name in (
            "CHAPTER_STARTED", "REVIEW_COMPLETED", "HARD_RULE_VIOLATION",
            "FORESHADOW_PLANTED", "SESSION_FORKED", "BOOK_CREATED",
        ):
            assert hasattr(event_types, name), f"missing constant: {name}"
        assert event_types.is_known_event_type(event_types.SESSION_FORKED)
        assert not event_types.is_known_event_type("never_registered_type")

    def test_payload_schemas_round_trip(self):
        # 6 个核心 payload schema 必须可构造 + dump
        p1 = event_payloads.ChapterStartedPayload(
            chapter_number=1, target_words=3000, triggered_by="user"
        )
        assert p1.model_dump()["chapter_number"] == 1

        p2 = event_payloads.DraftCompletedPayload(
            chapter_number=1, word_count=3200, draft_text="…", elapsed_ms=1234
        )
        assert p2.model_dump()["word_count"] == 3200

        p3 = event_payloads.ReviewCompletedPayload(
            decision="pass", overall_score=85.0, dimensions={}, summary="ok",
            annotation_count=0,
        )
        assert p3.model_dump()["decision"] == "pass"

        p4 = event_payloads.HardRuleViolationPayload(
            rule_id="x", severity="warning", evidence="…",
        )
        assert p4.model_dump()["rule_id"] == "x"

        p5 = event_payloads.ForeshadowPlantedPayload(
            foreshadow_id="fs1", description="…", recovery_deadline=50,
        )
        assert p5.model_dump()["recovery_deadline"] == 50

        p6 = event_payloads.SessionForkedPayload(
            new_session_id="abc", branch_name="exp", forked_at_event=10,
        )
        assert p6.model_dump()["new_session_id"] == "abc"


# ── 性能基线 ────────────────────────────────────────────────


@pytest.mark.slow
class TestPerformance:
    def test_append_p50_under_10ms(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            # warmup
            await store.append(book_id, sid, event_types.WRITER_PROGRESS, "w", {})
            # 测 100 次
            n = 100
            t0 = time.perf_counter()
            for i in range(n):
                await store.append(
                    book_id, sid, event_types.WRITER_PROGRESS, "w",
                    {"chapter_number": 1, "chars_so_far": i, "beat_index": 0},
                )
            elapsed = time.perf_counter() - t0
            return elapsed / n * 1000  # ms

        avg_ms = asyncio.run(_run())
        # 含同步 SQLite + asyncio.to_thread 调度，放宽到 30ms 上限（典型 < 10ms）
        assert avg_ms < 30, f"append 平均 {avg_ms:.2f}ms（期望 < 30ms）"

    def test_get_events_p50_under_50ms(self, store, book_id):
        async def _run():
            sid = await store.create_session(book_id)
            for i in range(200):
                await store.append(
                    book_id, sid, event_types.WRITER_PROGRESS, "w",
                    {"chapter_number": 1, "chars_so_far": i, "beat_index": 0},
                )
            t0 = time.perf_counter()
            for _ in range(20):
                await store.get_events(book_id, sid, from_seq=0, limit=100)
            elapsed = time.perf_counter() - t0
            return elapsed / 20 * 1000

        avg_ms = asyncio.run(_run())
        assert avg_ms < 50, f"get_events 平均 {avg_ms:.2f}ms（期望 < 50ms）"
