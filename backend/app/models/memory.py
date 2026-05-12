"""灵感助理记忆系统 — 数据模型

三张表:
- ChatSession: 对话会话（一次完整对话）
- ChatMessage: 对话消息（逐条存储）
- MemoryFact:  原子事实（从对话摘要中提取，跨 session 持久）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.connection import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class ChatSession(Base):
    """对话会话"""
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    # 滚动摘要：LLM 每 N 轮压缩当前 session 的对话内容
    summary: Mapped[str] = mapped_column(Text, default="")
    # 摘要指纹（用于跳过无变化的重新编译）
    summary_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ChatMessage(Base):
    """对话消息"""
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, default="")
    turn_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_chatmsg_session_turn", "session_id", "turn_index"),
    )


class MemoryFact(Base):
    """原子事实 — 从对话摘要中提取的持久记忆

    仿 OpenHanako 的 FactStore：
    - fact: 一条原子事实（如"用户喜欢写玄幻题材"）
    - tags: JSON 数组，用于标签检索
    - source_session_id: 提取自哪个 session
    """
    __tablename__ = "memory_facts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    source_session_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_memfact_created", "created_at"),
    )


class CompiledMemory(Base):
    """编译后的多层记忆 — 注入 system prompt 用

    仿 OpenHanako 的 4 段结构:
    - recent: 近期摘要（最近几次 session）
    - longterm: 长期用户画像
    - facts: 重要事实汇总
    - assembled: 最终拼装的 memory.md（直接注入 prompt）
    """
    __tablename__ = "compiled_memory"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default="singleton")
    recent: Mapped[str] = mapped_column(Text, default="")
    longterm: Mapped[str] = mapped_column(Text, default="")
    facts: Mapped[str] = mapped_column(Text, default="")
    assembled: Mapped[str] = mapped_column(Text, default="")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    compiled_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
