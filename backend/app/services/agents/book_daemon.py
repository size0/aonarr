"""BookProductionDaemon · Track F · Week 3 · Claude-C

每本书一个 asyncio Task，循环跑「生产单章 → 写事件 → 心跳 → 下一章」。

关键设计：
- 不直接耦合 `creation/autopilot.py`：通过 ``chapter_runner`` 注入产章动作。
  默认 stub 让 daemon 自身可独立测试；Phase 3 / ManagingEditor 落地后再
  替换为真实 runner。
- 所有事件经 EventStore 写入（chapter_started / writer_progress /
  draft_completed / book_phase_changed 等）。
- pause/resume/stop 控制信号合作式（章末检查），保持现有 autopilot 同款语义。
- DB BookState 行作为持久状态来源；进程内 cache 仅做加速。

EventStore 是可选依赖：传入 None 时不写事件（便于离线测试 / 极简场景）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models.book_state import (
    DAEMON_FAILED,
    DAEMON_IDLE,
    DAEMON_PAUSED,
    DAEMON_RUNNING,
    DAEMON_STOPPED,
    DAEMON_STOPPING,
    PHASE_COLD_START,
    PHASE_INIT,
    BookState,
)
from app.services.agents.llm_quota import LLMQuotaScheduler

logger = logging.getLogger(__name__)


class DaemonState(str, Enum):
    IDLE = DAEMON_IDLE
    RUNNING = DAEMON_RUNNING
    PAUSED = DAEMON_PAUSED
    STOPPING = DAEMON_STOPPING
    STOPPED = DAEMON_STOPPED
    FAILED = DAEMON_FAILED


@dataclass
class ChapterRunResult:
    """chapter_runner 必须返回的结构"""
    chapter_number: int
    word_count: int = 0
    elapsed_ms: int = 0
    extra: dict[str, Any] | None = None


# 类型别名：(book_id, chapter_number) -> ChapterRunResult
ChapterRunner = Callable[[str, int], Awaitable[ChapterRunResult]]


async def _stub_chapter_runner(book_id: str, chapter_number: int) -> ChapterRunResult:
    """默认 stub —— 不做实事，仅短暂 sleep，便于 daemon 自身测试"""
    await asyncio.sleep(0.01)
    return ChapterRunResult(
        chapter_number=chapter_number,
        word_count=0,
        elapsed_ms=10,
        extra={"runner": "stub", "book_id": book_id},
    )


class BookProductionDaemon:
    """单本书的生产 daemon。

    生命周期：
        idle → running → (paused ↔ running)* → stopping → stopped
                                              ↓
                                            failed (异常)

    用法::

        daemon = BookProductionDaemon(
            book_id="b1",
            session_id="s1",
            session_factory=SessionLocal,
            quota=quota_scheduler,
            event_store=store,                # optional
            chapter_runner=my_runner,         # optional
        )
        await daemon.start(start_chapter=1, end_chapter=10)
        # ... 后续:
        await daemon.pause()
        await daemon.resume()
        await daemon.stop()
        await daemon.wait()
    """

    def __init__(
        self,
        book_id: str,
        session_id: str,
        session_factory: Callable[[], Session],
        quota: LLMQuotaScheduler,
        event_store: Any | None = None,
        chapter_runner: ChapterRunner | None = None,
        heartbeat_interval: float = 5.0,
        priority: int = 5,
    ):
        if not book_id:
            raise ValueError("book_id 必填")
        self.book_id = book_id
        self.session_id = session_id
        self._session_factory = session_factory
        self._quota = quota
        self._event_store = event_store
        self._runner = chapter_runner or _stub_chapter_runner
        self._heartbeat_interval = max(1.0, float(heartbeat_interval))
        self._priority = int(priority)

        self.state: DaemonState = DaemonState.IDLE
        self._task: asyncio.Task | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 默认非暂停
        self._stop_event = asyncio.Event()
        self._last_error: str | None = None
        self._last_message: str | None = None
        self._chapters_completed: int = 0
        self._words_written: int = 0

    # ── public 控制接口 ─────────────────────────────────────

    async def start(self, start_chapter: int, end_chapter: int) -> None:
        """启动生产循环（异步任务，不阻塞）"""
        if self._task is not None and not self._task.done():
            raise RuntimeError(f"daemon for {self.book_id} 已在运行")
        if start_chapter < 1 or end_chapter < start_chapter:
            raise ValueError("章节范围非法")

        self.state = DaemonState.RUNNING
        self._stop_event.clear()
        self._pause_event.set()
        self._last_error = None
        self._chapters_completed = 0
        self._words_written = 0

        self._upsert_state(
            phase=PHASE_COLD_START,
            current_chapter=start_chapter,
            target_chapter_count=end_chapter,
            daemon_status=DaemonState.RUNNING.value,
            started_at=_utcnow(),
            last_message=f"daemon 启动: {start_chapter}-{end_chapter}",
        )
        await self._emit("book_phase_changed", {
            "from_phase": PHASE_INIT,
            "to_phase": PHASE_COLD_START,
            "at_chapter": start_chapter,
        })

        self._task = asyncio.create_task(self._run_loop(start_chapter, end_chapter))
        logger.info("BookDaemon started book=%s [%d, %d]", self.book_id, start_chapter, end_chapter)

    async def pause(self) -> None:
        if self.state != DaemonState.RUNNING:
            raise RuntimeError(f"只有 RUNNING 才能 pause（当前 {self.state}）")
        self.state = DaemonState.PAUSED
        self._pause_event.clear()
        self._upsert_state(daemon_status=DaemonState.PAUSED.value, last_message="已暂停")

    async def resume(self) -> None:
        if self.state != DaemonState.PAUSED:
            raise RuntimeError(f"只有 PAUSED 才能 resume（当前 {self.state}）")
        self.state = DaemonState.RUNNING
        self._pause_event.set()
        self._upsert_state(daemon_status=DaemonState.RUNNING.value, last_message="已恢复")

    async def stop(self) -> None:
        if self.state in (DaemonState.STOPPED, DaemonState.IDLE):
            return
        self.state = DaemonState.STOPPING
        self._stop_event.set()
        self._pause_event.set()  # 防止卡在 pause
        self._upsert_state(daemon_status=DaemonState.STOPPING.value, last_message="正在停止")

    async def wait(self, timeout: float | None = None) -> None:
        """等待 daemon 任务结束（用于测试和优雅关闭）"""
        if self._task is None:
            return
        if timeout is not None:
            await asyncio.wait_for(self._task, timeout=timeout)
        else:
            await self._task

    def status(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "session_id": self.session_id,
            "state": self.state.value,
            "chapters_completed": self._chapters_completed,
            "words_written": self._words_written,
            "last_error": self._last_error,
            "last_message": self._last_message,
        }

    # ── 主循环 ──────────────────────────────────────────────

    async def _run_loop(self, start_chapter: int, end_chapter: int) -> None:
        try:
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            try:
                for ch in range(start_chapter, end_chapter + 1):
                    if self._stop_event.is_set():
                        break

                    # 等待 pause 解除（合作式暂停）
                    await self._pause_event.wait()
                    if self._stop_event.is_set():
                        break

                    await self._produce_chapter(ch)

                # 正常结束
                if self._stop_event.is_set():
                    final_status = DaemonState.STOPPED
                    msg = f"已停止，完成至第 {self._chapters_completed} 章"
                else:
                    final_status = DaemonState.STOPPED
                    msg = f"全部完成，{self._chapters_completed} 章 / {self._words_written} 字"

                self.state = final_status
                self._upsert_state(
                    daemon_status=final_status.value,
                    completed_at=_utcnow(),
                    last_message=msg,
                )
                await self._emit("book_phase_changed", {
                    "from_phase": PHASE_COLD_START,
                    "to_phase": "stable",  # 简化：不区分 finale
                    "at_chapter": start_chapter + self._chapters_completed,
                })
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except (asyncio.CancelledError, Exception):
                    pass
        except Exception as e:  # noqa: BLE001
            self.state = DaemonState.FAILED
            self._last_error = f"{type(e).__name__}: {e}"
            logger.exception("BookDaemon failed book=%s", self.book_id)
            self._upsert_state(
                daemon_status=DaemonState.FAILED.value,
                last_error=self._last_error[:512],
                last_message="daemon 异常退出",
            )

    async def _produce_chapter(self, ch: int) -> None:
        # 章前事件
        await self._emit("chapter_started", {
            "chapter_number": ch,
            "target_words": 0,  # 不知道；让 runner 自己上报
            "triggered_by": "autopilot",
        }, chapter_number=ch)
        self._upsert_state(current_chapter=ch, last_message=f"正在写第 {ch} 章")

        # 拿配额跑 chapter_runner
        try:
            async with await self._quota.acquire(self.book_id, priority=self._priority):
                result = await self._runner(self.book_id, ch)
        except Exception as e:  # noqa: BLE001
            self._last_error = f"{type(e).__name__}: {e}"
            logger.exception("chapter_runner 失败 book=%s ch=%d", self.book_id, ch)
            await self._emit("early_stop_triggered", {
                "chapter_number": ch,
                "reason": self._last_error,
            }, chapter_number=ch)
            raise

        # 章后事件
        self._chapters_completed += 1
        self._words_written += int(result.word_count or 0)
        await self._emit("draft_completed", {
            "chapter_number": ch,
            "word_count": int(result.word_count or 0),
            "draft_text": "",  # daemon 不复制正文，由 runner 自己写到 DB
            "elapsed_ms": int(result.elapsed_ms or 0),
        }, chapter_number=ch)

        self._upsert_state(
            current_chapter=ch,
            last_message=f"第 {ch} 章完成 ({result.word_count} 字)",
            llm_quota_used_inc=1,
        )

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            self._upsert_state(last_heartbeat=_utcnow())

    # ── DB & 事件辅助 ──────────────────────────────────────

    def _upsert_state(self, *, llm_quota_used_inc: int = 0, **fields: Any) -> None:
        """同步写入 BookState 行（被 _heartbeat_loop / 主循环调用）"""
        db = self._session_factory()
        try:
            row = db.query(BookState).filter_by(book_id=self.book_id).first()
            if row is None:
                row = BookState(
                    book_id=self.book_id,
                    daemon_pid=os.getpid(),
                    daemon_host=socket.gethostname(),
                )
                db.add(row)
            for k, v in fields.items():
                setattr(row, k, v)
            if llm_quota_used_inc:
                row.llm_quota_used = (row.llm_quota_used or 0) + int(llm_quota_used_inc)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning("upsert BookState 失败 book=%s: %s", self.book_id, e)
        finally:
            db.close()

    async def _emit(
        self,
        event_type: str,
        payload: dict,
        chapter_number: int | None = None,
    ) -> None:
        if self._event_store is None or not self.session_id:
            return
        try:
            await self._event_store.append(
                book_id=self.book_id,
                session_id=self.session_id,
                event_type=event_type,
                actor="book_daemon",
                payload=payload,
                chapter_number=chapter_number,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("emit event 失败 book=%s type=%s: %s", self.book_id, event_type, e)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
