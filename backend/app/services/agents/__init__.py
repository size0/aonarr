"""Track F · Phase 2 · Agents 子包

公开符号：
- LLMQuotaScheduler          全局 LLM 配额管理器
- BookProductionDaemon       单本书生产 daemon
- DaemonPool                 多 daemon 池
"""
from __future__ import annotations

from app.services.agents.book_daemon import BookProductionDaemon, DaemonState
from app.services.agents.daemon_pool import DaemonPool, get_default_pool
from app.services.agents.llm_quota import (
    LLMQuotaExhausted,
    LLMQuotaLease,
    LLMQuotaScheduler,
)

__all__ = [
    "LLMQuotaScheduler",
    "LLMQuotaLease",
    "LLMQuotaExhausted",
    "BookProductionDaemon",
    "DaemonState",
    "DaemonPool",
    "get_default_pool",
]
