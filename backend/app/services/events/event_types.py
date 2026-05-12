"""事件类型常量表 · Track F · Week 2 · Claude-B

按契约 §1.4 定义。所有常量值采用 snake_case 字符串，与表 events.event_type 列对齐。
新增事件类型时：1) 在此文件加常量；2) 在 event_payloads.py 中加对应 Pydantic schema。
"""
from __future__ import annotations


# ── 章节生产 ────────────────────────────────────────────────
CHAPTER_STARTED = "chapter_started"
BEAT_PLAN_COMPLETED = "beat_plan_completed"
WRITER_SPAWNED = "writer_spawned"
WRITER_PROGRESS = "writer_progress"
DRAFT_COMPLETED = "draft_completed"
EARLY_STOP_TRIGGERED = "early_stop_triggered"


# ── 审核 ────────────────────────────────────────────────────
REVIEW_STARTED = "review_started"
REVIEW_COMPLETED = "review_completed"
HARD_RULE_VIOLATION = "hard_rule_violation"
REVISION_REQUESTED = "revision_requested"
REVISION_COMPLETED = "revision_completed"
CHAPTER_PASSED = "chapter_passed"
CHAPTER_REJECTED = "chapter_rejected"


# ── 连续性 ──────────────────────────────────────────────────
OBSERVER_EXTRACTED = "observer_extracted"
TRUTH_FILE_UPDATED = "truth_file_updated"
FORESHADOW_PLANTED = "foreshadow_planted"
FORESHADOW_RECOVERED = "foreshadow_recovered"
FORESHADOW_OVERDUE = "foreshadow_overdue"
CHARACTER_STATE_UPDATED = "character_state_updated"


# ── 跨章节审核 ──────────────────────────────────────────────
VOLUME_REVIEW_STARTED = "volume_review_started"
VOLUME_REVIEW_COMPLETED = "volume_review_completed"
ARC_CONSISTENCY_CHECK = "arc_consistency_check"
THEME_DRIFT_ALERT = "theme_drift_alert"


# ── 用户介入 ────────────────────────────────────────────────
USER_DECISION_REQUESTED = "user_decision_requested"
USER_DECISION_RECEIVED = "user_decision_received"
USER_EDIT_APPLIED = "user_edit_applied"
USER_PREFERENCE_INFERRED = "user_preference_inferred"


# ── Fork ────────────────────────────────────────────────────
SESSION_FORKED = "session_forked"
BRANCH_MERGED = "branch_merged"


# ── 生命周期 ────────────────────────────────────────────────
BOOK_CREATED = "book_created"
BOOK_PHASE_CHANGED = "book_phase_changed"


# ── 注册表（用于校验和反查）─────────────────────────────────
ALL_EVENT_TYPES: frozenset[str] = frozenset(
    v
    for k, v in list(globals().items())
    if not k.startswith("_") and isinstance(v, str) and k.isupper()
)


def is_known_event_type(event_type: str) -> bool:
    """快速校验某事件类型字符串是否在已注册集合中"""
    return event_type in ALL_EVENT_TYPES
