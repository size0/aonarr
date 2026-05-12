"""事件 Payload Pydantic schema · Track F · Week 2 · Claude-B

按契约 §1.5 定义。命名规则：每个 event_type 对应一个 <CamelCase>Payload。
后续 Claude 需要新增事件类型时，在此追加对应 schema。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ── 章节生产 ────────────────────────────────────────────────


class ChapterStartedPayload(BaseModel):
    chapter_number: int
    target_words: int
    triggered_by: Literal["autopilot", "user", "rewrite_request"]


class BeatPlanCompletedPayload(BaseModel):
    chapter_number: int
    beat_count: int
    plan_text: str = ""


class WriterSpawnedPayload(BaseModel):
    chapter_number: int
    writer_id: str
    target_beats: list[str] = Field(default_factory=list)


class WriterProgressPayload(BaseModel):
    chapter_number: int
    chars_so_far: int
    beat_index: int = 0


class DraftCompletedPayload(BaseModel):
    chapter_number: int
    word_count: int
    draft_text: str
    elapsed_ms: int


class EarlyStopTriggeredPayload(BaseModel):
    chapter_number: int
    reason: str


# ── 审核 ────────────────────────────────────────────────────


class ReviewStartedPayload(BaseModel):
    chapter_number: int
    novel_id: str | None = None


class ReviewCompletedPayload(BaseModel):
    decision: Literal["pass", "revise", "rewrite", "ask_user"]
    overall_score: float
    dimensions: dict[str, float] = Field(default_factory=dict)
    summary: str
    annotation_count: int = 0


class HardRuleViolationPayload(BaseModel):
    rule_id: str
    severity: Literal["info", "warning", "blocker"]
    evidence: str
    suggested_fix: str | None = None


class RevisionRequestedPayload(BaseModel):
    chapter_number: int
    revision_round: int
    focus: str = ""


class RevisionCompletedPayload(BaseModel):
    chapter_number: int
    revision_round: int
    accepted: bool


# ── 连续性 ──────────────────────────────────────────────────


class ForeshadowPlantedPayload(BaseModel):
    foreshadow_id: str
    description: str
    recovery_deadline: int = 0  # 必须在第几章前回收


class ForeshadowRecoveredPayload(BaseModel):
    foreshadow_id: str
    recovered_in_chapter: int


class ForeshadowOverduePayload(BaseModel):
    foreshadow_id: str
    description: str
    deadline: int
    current_chapter: int


class CharacterStateUpdatedPayload(BaseModel):
    character_name: str
    field: str
    old_value: str | None = None
    new_value: str | None = None
    chapter_number: int


# ── 跨章节审核 ──────────────────────────────────────────────


class VolumeReviewCompletedPayload(BaseModel):
    volume_index: int
    chapter_range: list[int]
    summary: str


class ThemeDriftAlertPayload(BaseModel):
    chapter_number: int
    drift_score: float
    drift_level: Literal["normal", "mild", "moderate", "severe"]


# ── 用户介入 ────────────────────────────────────────────────


class UserDecisionRequestedPayload(BaseModel):
    chapter_number: int
    question: str
    options: list[str] = Field(default_factory=list)


class UserDecisionReceivedPayload(BaseModel):
    chapter_number: int
    decision: str


class UserEditAppliedPayload(BaseModel):
    chapter_number: int
    diff_summary: str


# ── Fork（关键）────────────────────────────────────────────


class SessionForkedPayload(BaseModel):
    """fork_session 时写入到原 session 的事件 payload"""

    new_session_id: str
    branch_name: str
    forked_at_event: int


class BranchMergedPayload(BaseModel):
    merged_session_id: str
    target_session_id: str


# ── 生命周期 ────────────────────────────────────────────────


class BookCreatedPayload(BaseModel):
    novel_id: str
    title: str
    target_chapters: int


class BookPhaseChangedPayload(BaseModel):
    from_phase: str
    to_phase: Literal["init", "cold_start", "stable", "long_run", "finale"]
    at_chapter: int
