"""LLM Profile 数据模型与预设管理"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import String, Integer, Float, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.connection import Base

LLMProtocol = Literal["openai", "anthropic", "gemini"]


# ── SQLAlchemy 持久化模型 ──────────────────────────────────────────

class LLMProfileRow(Base):
    __tablename__ = "llm_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    protocol: Mapped[str] = mapped_column(String(16), default="openai")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    api_key: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    notes: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StageBindingRow(Base):
    """阶段→Profile 绑定表"""
    __tablename__ = "stage_bindings"

    stage: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    preset_name: Mapped[str] = mapped_column(String(32), default="custom")
    model_override: Mapped[str] = mapped_column(String(128), default="")
    # practical / flagship / custom


class LLMConfigMeta(Base):
    __tablename__ = "llm_config_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


# ── Pydantic DTO ──────────────────────────────────────────────────

class LLMProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    protocol: LLMProtocol = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout_seconds: int = 300
    notes: str = ""


class StageBinding(BaseModel):
    stage: str
    profile_id: str
    preset_name: str = "custom"
    model_override: str = ""


class StageModelConfig(BaseModel):
    """完整的阶段模型配置"""
    active_preset: str = "practical"  # practical / flagship / custom
    global_default_profile_id: Optional[str] = None
    profiles: list[LLMProfile] = Field(default_factory=list)
    bindings: list[StageBinding] = Field(default_factory=list)
