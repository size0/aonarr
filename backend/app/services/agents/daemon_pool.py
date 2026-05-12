"""DaemonPool · Track F · Week 3 · Claude-C

进程内的 BookProductionDaemon 池：管理多本书的并发生命周期。

- 单例：``get_default_pool()`` 返回全局池（按需 lazy-init）
- 每本书最多 1 个 daemon；spawn 已存在的 book 会 raise
- 关闭：``shutdown()`` 优雅停止所有 daemon

注意：单进程内有效；多进程部署需要外部协调（v1 不实现）。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.services.agents.book_daemon import BookProductionDaemon, ChapterRunner
from app.services.agents.llm_quota import LLMQuotaScheduler

logger = logging.getLogger(__name__)


class DaemonPool:
    """多 daemon 管理器。

    Args:
        session_factory: 创建短生命周期 Session 的工厂
        quota:           全局 LLMQuotaScheduler；不传则按 default_capacity 创建
        event_store:     可选事件流；传入则所有 daemon 共享
        default_capacity:  默认 quota 容量（当 quota=None 时生效）
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        quota: LLMQuotaScheduler | None = None,
        event_store: Any | None = None,
        default_capacity: int = 4,
    ):
        self._session_factory = session_factory
        self._quota = quota or LLMQuotaScheduler(capacity=default_capacity)
        self._event_store = event_store
        self._daemons: dict[str, BookProductionDaemon] = {}
        self._lock = asyncio.Lock()

    @property
    def quota(self) -> LLMQuotaScheduler:
        return self._quota

    async def spawn(
        self,
        book_id: str,
        session_id: str,
        start_chapter: int,
        end_chapter: int,
        *,
        chapter_runner: ChapterRunner | None = None,
        priority: int = 5,
        heartbeat_interval: float = 5.0,
    ) -> BookProductionDaemon:
        """创建并启动一个 daemon。已存在则 raise。"""
        async with self._lock:
            if book_id in self._daemons:
                existing = self._daemons[book_id]
                if existing.state.value not in ("stopped", "failed", "idle"):
                    raise RuntimeError(
                        f"book {book_id} 已有 daemon (state={existing.state.value})"
                    )
                # 清理终态 daemon，允许重新 spawn
                self._daemons.pop(book_id, None)

            daemon = BookProductionDaemon(
                book_id=book_id,
                session_id=session_id,
                session_factory=self._session_factory,
                quota=self._quota,
                event_store=self._event_store,
                chapter_runner=chapter_runner,
                heartbeat_interval=heartbeat_interval,
                priority=priority,
            )
            self._daemons[book_id] = daemon

        # 在锁外启动，避免锁内 await 太久
        await daemon.start(start_chapter, end_chapter)
        logger.info("DaemonPool spawned book=%s", book_id)
        return daemon

    async def pause(self, book_id: str) -> None:
        d = self._require(book_id)
        await d.pause()

    async def resume(self, book_id: str) -> None:
        d = self._require(book_id)
        await d.resume()

    async def stop(self, book_id: str, wait: bool = True, timeout: float = 30.0) -> None:
        d = self._require(book_id)
        await d.stop()
        if wait:
            try:
                await d.wait(timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("daemon stop wait timeout book=%s", book_id)

    def get(self, book_id: str) -> BookProductionDaemon | None:
        return self._daemons.get(book_id)

    def list_states(self) -> list[dict[str, Any]]:
        return [d.status() for d in self._daemons.values()]

    def stats(self) -> dict[str, Any]:
        return {
            "daemon_count": len(self._daemons),
            "quota": self._quota.stats(),
            "books": [
                {"book_id": bid, "state": d.state.value}
                for bid, d in self._daemons.items()
            ],
        }

    async def shutdown(self, timeout: float = 30.0) -> None:
        """停止所有 daemon。用于 app shutdown。"""
        books = list(self._daemons.keys())
        for bid in books:
            try:
                await self.stop(bid, wait=False)
            except Exception as e:  # noqa: BLE001
                logger.warning("shutdown stop book=%s 失败: %s", bid, e)
        # 等所有 daemon 收尾
        tasks = []
        for d in self._daemons.values():
            if d._task is not None and not d._task.done():
                tasks.append(d._task)
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("DaemonPool shutdown 超时")
        self._daemons.clear()

    def _require(self, book_id: str) -> BookProductionDaemon:
        d = self._daemons.get(book_id)
        if d is None:
            raise KeyError(f"daemon for book {book_id} 不存在")
        return d


# ── 进程内单例 ─────────────────────────────────────────────

_default_pool: DaemonPool | None = None


def get_default_pool(
    session_factory: Callable[[], Session] | None = None,
    event_store: Any | None = None,
) -> DaemonPool:
    """获取/初始化全局默认 DaemonPool。

    首次调用必须传 session_factory；后续调用忽略入参，返回单例。
    在 FastAPI startup 中调用一次以预热。
    """
    global _default_pool
    if _default_pool is None:
        if session_factory is None:
            from app.db.connection import SessionLocal
            session_factory = SessionLocal
        _default_pool = DaemonPool(
            session_factory=session_factory,
            event_store=event_store,
        )
    return _default_pool


def reset_default_pool() -> None:
    """仅测试用：重置全局单例"""
    global _default_pool
    _default_pool = None
