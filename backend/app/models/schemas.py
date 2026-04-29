from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"


class LLMProfileCreate(BaseModel):
    name: str = Field(min_length=1)
    provider_type: Literal["openai_compatible", "anthropic_compatible", "custom"] = "openai_compatible"
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    max_tokens_per_call: int | None = Field(default=None, ge=1)
    cost_per_1k_input_tokens: float | None = Field(default=None, ge=0)
    cost_per_1k_output_tokens: float | None = Field(default=None, ge=0)


class LLMProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    provider_type: Literal["openai_compatible", "anthropic_compatible", "custom"] | None = None
    base_url: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    api_key: str | None = Field(default=None, min_length=1)
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    max_tokens_per_call: int | None = Field(default=None, ge=1)
    cost_per_1k_input_tokens: float | None = Field(default=None, ge=0)
    cost_per_1k_output_tokens: float | None = Field(default=None, ge=0)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1)
    genre: str = Field(min_length=1)
    target_chapter_count: int = Field(ge=1, le=5000)
    target_words_per_chapter: int = Field(ge=200, le=20000)
    style_goal: str = Field(min_length=1)
    update_cadence: str | None = None
    default_llm_profile_id: str | None = None
    cost_limit_total: float | None = Field(default=None, ge=0)
    cost_limit_per_run: float | None = Field(default=None, ge=0)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    genre: str | None = Field(default=None, min_length=1)
    target_chapter_count: int | None = Field(default=None, ge=1, le=5000)
    target_words_per_chapter: int | None = Field(default=None, ge=200, le=20000)
    style_goal: str | None = Field(default=None, min_length=1)
    update_cadence: str | None = None
    default_llm_profile_id: str | None = None
    cost_limit_total: float | None = Field(default=None, ge=0)
    cost_limit_per_run: float | None = Field(default=None, ge=0)
    status: Literal["draft", "active", "paused", "archived"] | None = None


class CastMember(BaseModel):
    id: str
    name: str
    role: str | None = None
    motivation: str | None = None
    voice_hint: str | None = None
    forbidden_actions: list[str] = Field(default_factory=list)


class Place(BaseModel):
    id: str
    name: str
    kind: str | None = None
    summary: str | None = None
    parent_place_id: str | None = None


class PlotLine(BaseModel):
    id: str
    name: str
    goal: str
    stakes: str | None = None
    current_state: str | None = None


class ConstraintRule(BaseModel):
    id: str
    scope: Literal["world", "character", "style", "safety"]
    rule: str
    severity: Literal["info", "warn", "block"] = "warn"


class StoryBiblePut(BaseModel):
    premise: str = ""
    world_summary: str = ""
    tone_profile: str = ""
    content_limits: list[str] = Field(default_factory=list)
    cast_members: list[CastMember] = Field(default_factory=list)
    places: list[Place] = Field(default_factory=list)
    plot_lines: list[PlotLine] = Field(default_factory=list)
    constraint_rules: list[ConstraintRule] = Field(default_factory=list)


class SerialRunCreate(BaseModel):
    mode: Literal["plan_only", "draft_only", "full_auto"] = "full_auto"
    start_chapter_number: int = Field(default=1, ge=1)
    target_chapter_count: int = Field(default=5, ge=1, le=100)
    cost_limit: float | None = Field(default=None, ge=0)
    llm_profile_id: str | None = None


class ChapterPlanUpdate(BaseModel):
    title_hint: str | None = None
    goal: str | None = None
    conflict: str | None = None
    hook: str | None = None
    cast_ids: list[str] | None = None
    context_dependencies: list[str] | None = None
    status: Literal["planned", "used", "rejected"] | None = None


class ChapterDraftUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    status: Literal["draft", "accepted", "needs_revision", "rejected"] | None = None


class PromptTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    purpose: str | None = Field(default=None, min_length=1)
    system_template: str | None = Field(default=None, min_length=1)
    user_template: str | None = Field(default=None, min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)


class ExportCreate(BaseModel):
    format: Literal["markdown", "txt"] = "markdown"
    chapter_from: int | None = Field(default=None, ge=1)
    chapter_to: int | None = Field(default=None, ge=1)


class Envelope(BaseModel):
    data: Any
