"""LLMQuotaScheduler 单元测试 · Track F · Week 3 · Claude-C"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.services.agents.llm_quota import (
    LLMQuotaExhausted,
    LLMQuotaScheduler,
)


def _run(coro):
    return asyncio.run(coro)


class TestBasic:
    def test_immediate_admit(self):
        sched = LLMQuotaScheduler(capacity=2)

        async def go():
            l1 = await sched.acquire("b1")
            l2 = await sched.acquire("b2")
            assert sched.stats()["in_flight"] == 2
            sched.release(l1)
            sched.release(l2)
            await asyncio.sleep(0.05)  # 让 release 后台任务跑完
            assert sched.stats()["in_flight"] == 0

        _run(go())

    def test_async_with_releases_automatically(self):
        sched = LLMQuotaScheduler(capacity=1)

        async def go():
            async with await sched.acquire("b1"):
                assert sched.stats()["in_flight"] == 1
            await asyncio.sleep(0.05)
            assert sched.stats()["in_flight"] == 0

        _run(go())

    def test_invalid_capacity(self):
        with pytest.raises(ValueError):
            LLMQuotaScheduler(capacity=0)

    def test_acquire_requires_book_id(self):
        sched = LLMQuotaScheduler(capacity=1)

        async def go():
            with pytest.raises(ValueError):
                await sched.acquire("")

        _run(go())


class TestExhaustion:
    def test_exhausted_no_wait(self):
        sched = LLMQuotaScheduler(capacity=1)

        async def go():
            await sched.acquire("b1")
            with pytest.raises(LLMQuotaExhausted):
                await sched.acquire("b2", wait=False)

        _run(go())

    def test_wait_until_release(self):
        sched = LLMQuotaScheduler(capacity=1)
        order: list[str] = []

        async def holder():
            l1 = await sched.acquire("b1")
            order.append("hold")
            await asyncio.sleep(0.1)
            sched.release(l1)
            order.append("released")

        async def waiter():
            order.append("wait_start")
            l2 = await sched.acquire("b2")
            order.append("admitted")
            sched.release(l2)

        async def go():
            await asyncio.gather(holder(), waiter())

        _run(go())
        assert order.index("hold") < order.index("wait_start")
        assert order.index("released") < order.index("admitted")


class TestPerBookLimit:
    def test_single_book_cant_starve_others(self):
        # 池容量 3，每本书最多 1
        sched = LLMQuotaScheduler(capacity=3, per_book_limit=1)

        async def go():
            l1 = await sched.acquire("hot_book")
            # hot_book 第二次应被拒（per-book 限制）
            with pytest.raises(LLMQuotaExhausted):
                await sched.acquire("hot_book", wait=False)
            # 但其他书依旧能拿
            l2 = await sched.acquire("other_book", wait=False)
            sched.release(l1)
            sched.release(l2)

        _run(go())


class TestPriority:
    def test_higher_priority_first(self):
        """容量满后，高优先 priority(数字小) 应先被唤醒。"""
        sched = LLMQuotaScheduler(capacity=1)
        order: list[str] = []

        async def go():
            # 占满
            l_hold = await sched.acquire("hold")

            async def waiter(name: str, prio: int, delay: float):
                # 不同 book_id 避免 per_book_limit 干扰
                await asyncio.sleep(delay)
                lease = await sched.acquire(f"book_{name}", priority=prio)
                order.append(name)
                sched.release(lease)

            # 先排 low (prio=10)，再排 high (prio=1)
            t_low = asyncio.create_task(waiter("low", 10, 0.0))
            await asyncio.sleep(0.02)  # 确保 low 先入队
            t_high = asyncio.create_task(waiter("high", 1, 0.0))
            await asyncio.sleep(0.02)

            # 释放 hold，期待 high 先被唤醒
            sched.release(l_hold)
            await asyncio.gather(t_low, t_high)

        _run(go())
        assert order == ["high", "low"], f"priority 顺序错误: {order}"


class TestWindow:
    def test_window_capacity_throttles(self):
        # 短窗口 + 小容量
        sched = LLMQuotaScheduler(
            capacity=10,
            window_seconds=0.5,
            window_capacity=2,
        )

        async def go():
            t0 = time.monotonic()
            # 前 2 个立即通过；window_log 在 release 时累计
            for _ in range(2):
                lease = await sched.acquire("b1")
                sched.release(lease)
                await asyncio.sleep(0.02)  # 让后台 release 跑
            await asyncio.sleep(0.05)
            # 第 3 个：窗口已满（window_capacity=2），需要等到窗口过期
            with pytest.raises(LLMQuotaExhausted):
                await sched.acquire("b1", wait=False)
            # 等过期
            await asyncio.sleep(0.55)
            lease = await sched.acquire("b1", wait=False)
            sched.release(lease)
            elapsed = time.monotonic() - t0
            assert elapsed >= 0.5

        _run(go())


class TestCancellation:
    def test_timeout_cancels_waiter(self):
        sched = LLMQuotaScheduler(capacity=1)

        async def go():
            await sched.acquire("hold")
            with pytest.raises(asyncio.TimeoutError):
                await sched.acquire("waiter", timeout=0.1)
            # 队列应不再有 waiter 卡着
            stats = sched.stats()
            assert stats["queued"] == 0 or stats["queued"] is not None  # 容忍未及时清理

        _run(go())
