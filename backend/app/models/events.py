"""Event Stream 数据模型 · Track F · Week 2 · Claude-B

按契约 §1.1 定义两张表：
- events: append-only 事件流
- production_sessions: 生产 session 管理（命名避免与 SQLAlchemy `Session` 类冲突；ORM 类名 `SessionRecord`）

设计要点：
- 全部走 SQLite 兼容路径（不使用 PostgreSQL 特有类型）
- payload 使用 SQLAlchemy 通用 JSON 列（SQLite 走 TEXT + JSON1，Postgres 走 JSONB）
- `events.seq` 是 session 内的单调序列号，由 EventStore.append 在事务里串行计算
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.connection import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Event(Base):
    """append-only 事件流（永不更新 / 删除）"""

    __tablename__ = "events"

    # SQLite 只能在 INTEGER PRIMARY KEY 上自增，所以 PK 上用 with_variant
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    book_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_event_id: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("idx_events_book_session_seq", "book_id", "session_id", "seq", unique=True),
        Index("idx_events_book_chapter", "book_id", "chapter_number"),
        Index("idx_events_event_type", "event_type"),
        Index("idx_events_session_id", "session_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "session_id": self.session_id,
            "parent_session_id": self.parent_session_id,
            "seq": self.seq,
            "event_type": self.event_type,
            "actor": self.actor,
            "payload": self.payload,
            "chapter_number": self.chapter_number,
            "parent_event_id": self.parent_event_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SessionRecord(Base):
    """生产 session 记录。

    - parent_session_id + forked_at_event 表示从某个事件点 fork 出本 session
    - status: active / merged / abandoned
    """

    __tablename__ = "production_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parent_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    forked_at_event: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), nullable=True
    )
    branch_name: Mapped[str] = mapped_column(String(128), nullable=False, default="main")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_prod_session_book_status", "book_id", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "parent_session_id": self.parent_session_id,
            "forked_at_event": self.forked_at_event,
            "branch_name": self.branch_name,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "merged_at": self.merged_at.isoformat() if self.merged_at else None,
        }
