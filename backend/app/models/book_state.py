"""BookState 运行时状态模型 · Track F · Week 3 · Claude-C

与 ProductionSession（事件流分支）不同，BookState 表达的是「单本书的 daemon
运行时状态」：当前 phase、进度、配额使用、心跳等。一本书一行。

设计要点：
- 跟 ``production_sessions``（Claude-B 已建）独立，无 FK 关系
- daemon_pid / daemon_host 仅作诊断（不依赖于此做生命周期判断）
- last_heartbeat 由 BookProductionDaemon 周期性更新，外部可据此判活
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.connection import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Phase 取值（与契约 §7.4 一致）
PHASE_INIT = "init"
PHASE_COLD_START = "cold_start"
PHASE_STABLE = "stable"
PHASE_LONG_RUN = "long_run"
PHASE_FINALE = "finale"
ALL_PHASES = (PHASE_INIT, PHASE_COLD_START, PHASE_STABLE, PHASE_LONG_RUN, PHASE_FINALE)

# DaemonStatus 取值
DAEMON_IDLE = "idle"
DAEMON_RUNNING = "running"
DAEMON_PAUSED = "paused"
DAEMON_STOPPING = "stopping"
DAEMON_STOPPED = "stopped"
DAEMON_FAILED = "failed"
ALL_DAEMON_STATUSES = (
    DAEMON_IDLE, DAEMON_RUNNING, DAEMON_PAUSED,
    DAEMON_STOPPING, DAEMON_STOPPED, DAEMON_FAILED,
)


class BookState(Base):
    """每本书一行：运行时状态 + 进度 + 配额"""

    __tablename__ = "book_states"

    book_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # 流程阶段
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default=PHASE_INIT)
    current_chapter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_chapter_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # daemon 控制
    daemon_status: Mapped[str] = mapped_column(String(32), nullable=False, default=DAEMON_IDLE)
    daemon_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daemon_host: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # LLM 配额（运行时累计；启动新一轮时由 daemon 重置）
    llm_quota_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_quota_max: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 时间戳
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # 诊断
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 运行时配置（写本书时的参数：words_per_chapter / priority / 模型选择等）
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_book_states_phase", "phase"),
        Index("idx_book_states_daemon_status", "daemon_status"),
    )

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "phase": self.phase,
            "current_chapter": self.current_chapter,
            "target_chapter_count": self.target_chapter_count,
            "daemon_status": self.daemon_status,
            "daemon_pid": self.daemon_pid,
            "daemon_host": self.daemon_host,
            "llm_quota_used": self.llm_quota_used,
            "llm_quota_max": self.llm_quota_max,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_error": self.last_error,
            "last_message": self.last_message,
            "config": self.config or {},
        }
