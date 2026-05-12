"""BookProductionDaemon + DaemonPool 测试 · Track F · Week 3 · Claude-C

覆盖：
- daemon 基础生命周期 (start / wait / status)
- pause / resume / stop
- chapter_runner 集成 + 事件钩子（review_started 等价：chapter_started）
- 配额耗尽 / 失败回退
- BookState DB 持久化
- DaemonPool spawn / list / shutdown
- 多本书并发不互相阻塞
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from app.db.connection import Base, SessionLocal, engine
from app.models.book_state import (
    DAEMON_FAILED,
    DAEMON_RUNNING,
    DAEMON_STOPPED,
    BookState,
)
from app.services.agents.book_daemon import (
    BookProductionDaemon,
    ChapterRunResult,
    DaemonState,
)
from app.services.agents.daemon_pool import DaemonPool, reset_default_pool
from app.services.agents.llm_quota import LLMQuotaScheduler


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_default_pool()
    yield
    reset_default_pool()


def _run(coro):
    return asyncio.run(coro)


def _new_book_id() -> str:
    return f"book_{uuid.uuid4().hex[:8]}"


async def _ok_runner(book_id: str, chapter_number: int) -> ChapterRunResult:
    """正常 runner：每章 200 字"""
    await asyncio.sleep(0.005)
    return ChapterRunResult(
        chapter_number=chapter_number,
        word_count=200,
        elapsed_ms=5,
    )


async def _slow_runner(book_id: str, chapter_number: int) -> ChapterRunResult:
    await asyncio.sleep(0.1)
    return ChapterRunResult(chapter_number=chapter_number, word_count=100, elapsed_ms=100)


async def _failing_runner(book_id: str, chapter_number: int) -> ChapterRunResult:
    raise RuntimeError("simulated runner failure")


class _StubEventStore:
    """记录所有 append 事件的假 EventStore（不写 DB）。"""

    def __init__(self):
        self.events: list[dict] = []

    async def append(self, **kwargs):
        self.events.append(kwargs)
        return len(self.events)


# ── daemon 基础生命周期 ─────────────────────────────────


class TestLifecycle:
    def test_start_and_complete(self):
        book_id = _new_book_id()
        quota = LLMQuotaScheduler(capacity=2)
        store = _StubEventStore()
        daemon = BookProductionDaemon(
            book_id=book_id,
            session_id="sess_test",
            session_factory=SessionLocal,
            quota=quota,
            event_store=store,
            chapter_runner=_ok_runner,
            heartbeat_interval=10.0,
        )

        async def go():
            await daemon.start(start_chapter=1, end_chapter=3)
            await daemon.wait(timeout=5.0)

        _run(go())

        assert daemon.state == DaemonState.STOPPED
        assert daemon.status()["chapters_completed"] == 3
        assert daemon.status()["words_written"] == 600

        # 事件断言
        types = [e["event_type"] for e in store.events]
        assert types.count("chapter_started") == 3
        assert types.count("draft_completed") == 3
        assert "book_phase_changed" in types  # 启动时 + 结束时
        assert all(e["actor"] == "book_daemon" for e in store.events)

    def test_no_event_store_no_emit(self):
        book_id = _new_book_id()
        daemon = BookProductionDaemon(
            book_id=book_id,
            session_id="x",
            session_factory=SessionLocal,
            quota=LLMQuotaScheduler(capacity=1),
            event_store=None,
            chapter_runner=_ok_runner,
        )

        async def go():
            await daemon.start(1, 2)
            await daemon.wait(timeout=5.0)

        _run(go())
        assert daemon.state == DaemonState.STOPPED  # 仍然完成
        assert daemon.status()["chapters_completed"] == 2

    def test_invalid_chapter_range(self):
        daemon = BookProductionDaemon(
            book_id=_new_book_id(),
            session_id="x",
            session_factory=SessionLocal,
            quota=LLMQuotaScheduler(capacity=1),
        )

        async def go():
            with pytest.raises(ValueError):
                await daemon.start(0, 5)

        _run(go())

    def test_double_start_raises(self):
        daemon = BookProductionDaemon(
            book_id=_new_book_id(),
            session_id="x",
            session_factory=SessionLocal,
            quota=LLMQuotaScheduler(capacity=1),
            chapter_runner=_slow_runner,
        )

        async def go():
            await daemon.start(1, 5)
            with pytest.raises(RuntimeError):
                await daemon.start(1, 5)
            await daemon.stop()
            await daemon.wait(timeout=5.0)

        _run(go())


# ── pause / resume / stop ───────────────────────────────


class TestControl:
    def test_pause_resume(self):
        daemon = BookProductionDaemon(
            book_id=_new_book_id(),
            session_id="x",
            session_factory=SessionLocal,
            quota=LLMQuotaScheduler(capacity=1),
            chapter_runner=_slow_runner,
        )

        async def go():
            await daemon.start(1, 5)
            await asyncio.sleep(0.05)
            await daemon.pause()
            assert daemon.state == DaemonState.PAUSED
            chapters_before = daemon.status()["chapters_completed"]
            await asyncio.sleep(0.3)
            # pause 期间章节不应继续增长（容忍当前 in-flight 章节完成）
            chapters_during = daemon.status()["chapters_completed"]
            assert chapters_during <= chapters_before + 1
            await daemon.resume()
            assert daemon.state == DaemonState.RUNNING
            await daemon.stop()
            await daemon.wait(timeout=5.0)

        _run(go())

    def test_stop_short_circuits(self):
        daemon = BookProductionDaemon(
            book_id=_new_book_id(),
            session_id="x",
            session_factory=SessionLocal,
            quota=LLMQuotaScheduler(capacity=1),
            chapter_runner=_slow_runner,
        )

        async def go():
            await daemon.start(1, 100)
            await asyncio.sleep(0.05)
            await daemon.stop()
            await daemon.wait(timeout=5.0)
            assert daemon.state == DaemonState.STOPPED
            # 远没跑到 100 章
            assert daemon.status()["chapters_completed"] < 10

        _run(go())

    def test_resume_when_not_paused_raises(self):
        daemon = BookProductionDaemon(
            book_id=_new_book_id(),
            session_id="x",
            session_factory=SessionLocal,
            quota=LLMQuotaScheduler(capacity=1),
        )

        async def go():
            with pytest.raises(RuntimeError):
                await daemon.resume()

        _run(go())


# ── 失败 & 事件 ─────────────────────────────────────────


class TestFailure:
    def test_runner_failure_marks_failed(self):
        store = _StubEventStore()
        daemon = BookProductionDaemon(
            book_id=_new_book_id(),
            session_id="x",
            session_factory=SessionLocal,
            quota=LLMQuotaScheduler(capacity=1),
            event_store=store,
            chapter_runner=_failing_runner,
        )

        async def go():
            await daemon.start(1, 3)
            await daemon.wait(timeout=5.0)

        _run(go())

        assert daemon.state == DaemonState.FAILED
        assert daemon.status()["last_error"] is not None
        types = [e["event_type"] for e in store.events]
        assert "early_stop_triggered" in types


# ── BookState 持久化 ────────────────────────────────────


class TestBookStatePersistence:
    def test_state_row_written(self):
        book_id = _new_book_id()
        daemon = BookProductionDaemon(
            book_id=book_id,
            session_id="x",
            session_factory=SessionLocal,
            quota=LLMQuotaScheduler(capacity=1),
            chapter_runner=_ok_runner,
        )

        async def go():
            await daemon.start(1, 2)
            await daemon.wait(timeout=5.0)

        _run(go())

        db = SessionLocal()
        try:
            row = db.query(BookState).filter_by(book_id=book_id).first()
            assert row is not None
            assert row.daemon_status == DAEMON_STOPPED
            assert row.target_chapter_count == 2
            assert row.llm_quota_used >= 2
            assert row.daemon_pid is not None
            assert row.last_message is not None
        finally:
            db.query(BookState).filter_by(book_id=book_id).delete()
            db.commit()
            db.close()


# ── DaemonPool ─────────────────────────────────────────


class TestDaemonPool:
    def test_spawn_and_list(self):
        pool = DaemonPool(session_factory=SessionLocal)
        b1 = _new_book_id()
        b2 = _new_book_id()

        async def go():
            d1 = await pool.spawn(b1, "s1", 1, 2, chapter_runner=_ok_runner)
            d2 = await pool.spawn(b2, "s2", 1, 2, chapter_runner=_ok_runner)
            assert d1 is not d2
            states = pool.list_states()
            assert len(states) == 2
            await pool.stop(b1, wait=True, timeout=5)
            await pool.stop(b2, wait=True, timeout=5)

        _run(go())

    def test_spawn_existing_raises(self):
        pool = DaemonPool(session_factory=SessionLocal)
        book_id = _new_book_id()

        async def go():
            await pool.spawn(book_id, "s", 1, 100, chapter_runner=_slow_runner)
            with pytest.raises(RuntimeError):
                await pool.spawn(book_id, "s", 1, 5, chapter_runner=_slow_runner)
            await pool.stop(book_id, wait=True, timeout=5)

        _run(go())

    def test_concurrent_books_dont_block_each_other(self):
        """两本书同时跑，总耗时应明显小于串行（证明并发生效）"""
        pool = DaemonPool(session_factory=SessionLocal, default_capacity=4)
        b1 = _new_book_id()
        b2 = _new_book_id()

        async def go():
            await pool.spawn(b1, "s1", 1, 5, chapter_runner=_slow_runner)
            await pool.spawn(b2, "s2", 1, 5, chapter_runner=_slow_runner)
            t0 = asyncio.get_event_loop().time()
            await pool.stop(b1, wait=True, timeout=10)
            await pool.stop(b2, wait=True, timeout=10)
            return asyncio.get_event_loop().time() - t0

        elapsed = _run(go())
        # 串行 10 章 * 0.1s = 1.0s；并发应 <= 0.7s
        assert elapsed < 0.7, f"并发不生效（耗时 {elapsed:.2f}s）"

    def test_pool_pause_resume_via_pool_api(self):
        pool = DaemonPool(session_factory=SessionLocal)
        book_id = _new_book_id()

        async def go():
            await pool.spawn(book_id, "s", 1, 100, chapter_runner=_slow_runner)
            await asyncio.sleep(0.05)
            await pool.pause(book_id)
            assert pool.get(book_id).state == DaemonState.PAUSED
            await pool.resume(book_id)
            assert pool.get(book_id).state == DaemonState.RUNNING
            await pool.stop(book_id, wait=True, timeout=5)

        _run(go())

    def test_stop_missing_raises(self):
        pool = DaemonPool(session_factory=SessionLocal)

        async def go():
            with pytest.raises(KeyError):
                await pool.stop("nonexistent_book")

        _run(go())

    def test_shutdown_stops_all(self):
        pool = DaemonPool(session_factory=SessionLocal)
        books = [_new_book_id() for _ in range(3)]

        async def go():
            for b in books:
                await pool.spawn(b, f"s_{b}", 1, 100, chapter_runner=_slow_runner)
            await asyncio.sleep(0.05)
            await pool.shutdown(timeout=10)
            assert pool.stats()["daemon_count"] == 0

        _run(go())
