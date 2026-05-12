"""LLM 配置 Pydantic DTO"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class LLMProfileCreate(BaseModel):
    name: str
    protocol: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout_seconds: int = 300
    notes: str = ""


class LLMProfileUpdate(BaseModel):
    name: Optional[str] = None
    protocol: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout_seconds: Optional[int] = None
    notes: Optional[str] = None


class LLMProfileDTO(BaseModel):
    id: str
    name: str
    protocol: str
    base_url: str
    api_key_masked: str  # 只显示前4+后4位
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: int
    notes: str


class StageBindingDTO(BaseModel):
    stage: str
    stage_label: str
    profile_id: str
    profile_name: str
    model: str
    preset_name: str
    model_override: str = ""


class SetStageBindingRequest(BaseModel):
    stage: str
    profile_id: str
    model_override: str = ""


class ApplyPresetRequest(BaseModel):
    preset_name: str  # practical / flagship


class StageModelConfigDTO(BaseModel):
    active_preset: str
    profiles: list[LLMProfileDTO]
    bindings: list[StageBindingDTO]
    available_stages: list[dict]  # [{stage, label}]
