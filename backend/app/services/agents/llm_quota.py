"""LLMQuotaScheduler · Track F · Week 3 · Claude-C

全局 LLM 配额管理：
- 总池容量 ``capacity`` 限制并发 LLM 请求数（防止单本书烧光配额）
- 按 priority（0=最高）排队
- 每本书可配 ``per_book_limit``（最多并发数），保护其他书不被饿死
- 同步使用 / async-with 双接口：

    async with scheduler.acquire("book_a", priority=1):
        ...  # 调 LLM

时间窗口配额（"每分钟 N 次"）通过 ``window_seconds`` + ``window_capacity`` 控制；
默认关闭（设为 0）。

线程安全：所有状态在 asyncio.Lock 下操作；不可跨进程共享。
多进程共享配额需要外部协调（如 Redis），不在 v1 范围。
"""
from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class LLMQuotaExhausted(Exception):
    """配额耗尽且 wait=False 时抛出"""


@dataclass(order=True)
class _PendingRequest:
    """等待队列条目：按 (priority, seq) 排序，priority 数字越小越优先。"""
    priority: int
    seq: int
    book_id: str = field(compare=False)
    future: asyncio.Future = field(compare=False)


class LLMQuotaLease:
    """acquire() 返回的"租约"对象，进入 async-with 后自动 release。

    手动用法::

        lease = await scheduler.acquire("book_a")
        try:
            await call_llm()
        finally:
            scheduler.release(lease)
    """

    def __init__(self, scheduler: "LLMQuotaScheduler", book_id: str):
        self._scheduler = scheduler
        self.book_id = book_id
        self._released = False

    async def __aenter__(self) -> "LLMQuotaLease":
        return self

    async def __aexit__(self, *exc) -> None:
        if not self._released:
            self._scheduler.release(self)
            self._released = True


class LLMQuotaScheduler:
    """全局并发 + 窗口配额调度器。

    Args:
        capacity:        全局并发上限（同时只能有 N 个 LLM 调用在飞）
        per_book_limit:  单本书并发上限；0 表示不限
        window_seconds:  时间窗口大小（秒）；0 表示不启用窗口配额
        window_capacity: 窗口内最多请求数；只在 window_seconds > 0 时生效
    """

    def __init__(
        self,
        capacity: int = 4,
        per_book_limit: int = 0,
        window_seconds: float = 0.0,
        window_capacity: int = 0,
    ):
        if capacity <= 0:
            raise ValueError("capacity 必须 > 0")
        self.capacity = int(capacity)
        self.per_book_limit = max(0, int(per_book_limit))
        self.window_seconds = max(0.0, float(window_seconds))
        self.window_capacity = max(0, int(window_capacity))

        self._lock = asyncio.Lock()
        self._in_flight = 0
        self._per_book: dict[str, int] = {}
        self._window_log: list[float] = []  # 最近完成时间戳

        self._waiters: list[_PendingRequest] = []
        self._seq_counter = itertools.count()

    # ── public ──────────────────────────────────────────────

    async def acquire(
        self,
        book_id: str,
        priority: int = 5,
        wait: bool = True,
        timeout: float | None = None,
    ) -> LLMQuotaLease:
        """获取一个配额槽。

        - priority: 0=最高，数字越大越低；同 priority 内按到达顺序（FIFO）
        - wait=False: 当前无可用槽时立即 raise LLMQuotaExhausted
        - timeout: 等待超时（秒），超时 raise asyncio.TimeoutError
        """
        if not book_id:
            raise ValueError("acquire 需要 book_id")

        async with self._lock:
            if self._can_admit_locked(book_id):
                self._admit_locked(book_id)
                logger.debug("LLMQuota immediate admit book=%s in_flight=%d",
                             book_id, self._in_flight)
                return LLMQuotaLease(self, book_id)

            if not wait:
                raise LLMQuotaExhausted(
                    f"配额已满 (in_flight={self._in_flight}/{self.capacity}, "
                    f"book={book_id})"
                )

            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            req = _PendingRequest(
                priority=int(priority),
                seq=next(self._seq_counter),
                book_id=book_id,
                future=fut,
            )
            heapq.heappush(self._waiters, req)
            logger.debug(
                "LLMQuota queued book=%s prio=%d (in_flight=%d/%d, queue=%d)",
                book_id, priority, self._in_flight, self.capacity, len(self._waiters),
            )

        # 已 await 的 fut，超时由调用方处理
        try:
            if timeout is not None:
                await asyncio.wait_for(fut, timeout=timeout)
            else:
                await fut
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # 取消时若 future 还在等待队列，标记取消并尝试唤醒下一个
            await self._cancel_waiter(req)
            raise

        return LLMQuotaLease(self, book_id)

    def release(self, lease: LLMQuotaLease) -> None:
        """释放租约（同步），唤醒下一个等待者"""
        async def _do():
            async with self._lock:
                self._release_locked(lease.book_id)
                self._wake_next_locked()

        # 创建后台任务执行；调用方不需要 await
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_do())
        except RuntimeError:
            # 没有运行中的 loop —— 通常是测试 cleanup，直接同步降回
            self._sync_release_unsafe(lease.book_id)

    def stats(self) -> dict[str, Any]:
        return {
            "capacity": self.capacity,
            "in_flight": self._in_flight,
            "queued": len(self._waiters),
            "per_book": dict(self._per_book),
            "window_seconds": self.window_seconds,
            "window_used": len(self._window_log),
        }

    # ── internal ────────────────────────────────────────────

    def _can_admit_locked(self, book_id: str) -> bool:
        if self._in_flight >= self.capacity:
            return False
        if self.per_book_limit and self._per_book.get(book_id, 0) >= self.per_book_limit:
            return False
        if self.window_seconds > 0 and self.window_capacity > 0:
            self._purge_window_locked()
            if len(self._window_log) >= self.window_capacity:
                return False
        return True

    def _admit_locked(self, book_id: str) -> None:
        self._in_flight += 1
        self._per_book[book_id] = self._per_book.get(book_id, 0) + 1

    def _release_locked(self, book_id: str) -> None:
        self._in_flight = max(0, self._in_flight - 1)
        cur = self._per_book.get(book_id, 0)
        if cur <= 1:
            self._per_book.pop(book_id, None)
        else:
            self._per_book[book_id] = cur - 1
        if self.window_seconds > 0:
            self._window_log.append(time.monotonic())
            self._purge_window_locked()

    def _purge_window_locked(self) -> None:
        if self.window_seconds <= 0:
            return
        cutoff = time.monotonic() - self.window_seconds
        # 保留窗口内的；列表通常很短，简单线性扫描
        self._window_log = [t for t in self._window_log if t >= cutoff]

    def _wake_next_locked(self) -> None:
        # 不断尝试唤醒队首；遇到不能 admit 的 book 就停（避免乱序）
        while self._waiters:
            head = self._waiters[0]
            if head.future.cancelled() or head.future.done():
                heapq.heappop(self._waiters)
                continue
            if not self._can_admit_locked(head.book_id):
                break
            heapq.heappop(self._waiters)
            self._admit_locked(head.book_id)
            head.future.set_result(None)

    async def _cancel_waiter(self, req: _PendingRequest) -> None:
        async with self._lock:
            if not req.future.done():
                req.future.cancel()

    def _sync_release_unsafe(self, book_id: str) -> None:
        """无 loop 时的降级路径（测试 teardown）—— 不唤醒等待者"""
        self._in_flight = max(0, self._in_flight - 1)
        cur = self._per_book.get(book_id, 0)
        if cur <= 1:
            self._per_book.pop(book_id, None)
        else:
            self._per_book[book_id] = cur - 1
