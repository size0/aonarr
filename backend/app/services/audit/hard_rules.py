"""硬约束规则集 — Track F · Week 1 · Claude-A

提供 6 条纯逻辑、不调 LLM 的硬规则，用于审稿前的快速拦截。
任一 blocker 命中时，MuyuEditor 应跳过 LLM 审稿直接要求重写。

设计原则：
- 纯本地计算，每条规则 < 10ms
- 规则内部异常不得让整个审稿流程崩溃（由 run_hard_rules 吸收）
- 规则对缺失的 truth_file / active_foreshadows 字段保持宽容（skip，不报错）
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal


# ── 数据结构 ────────────────────────────────────────────────


@dataclass
class HardRuleContext:
    """传给规则 check 函数的上下文。"""

    novel_id: str
    chapter_number: int
    draft_text: str
    truth_file: dict
    active_foreshadows: list[dict]
    expected_word_range: tuple[int, int]


@dataclass
class HardRuleViolation:
    rule_id: str
    severity: Literal["info", "warning", "blocker"]
    evidence: str
    suggested_fix: str | None = None


@dataclass
class HardRule:
    id: str
    description: str
    category: str  # character / structure / continuity / foreshadow / style
    severity: Literal["info", "warning", "blocker"]  # 典型严重度（实际由 check 返回决定）
    check: Callable[[HardRuleContext], "HardRuleViolation | None"]


# ── 工具 ────────────────────────────────────────────────────

_CN_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_DATE_RE = re.compile(r"(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})日?")
_FLASHBACK_MARKERS = (
    "回忆",
    "往事",
    "想起",
    "想当年",
    "旧事",
    "梦境",
    "回想",
    "梦见",
    "倒叙",
    "追忆",
    "当年",
    "曾经",
    "那年",
    "那时",
)


def _count_chinese_chars(text: str) -> int:
    return len(_CN_CHAR_RE.findall(text))


def _parse_date_tuple(year: str, month: str, day: str) -> tuple[int, int, int]:
    return (int(year), int(month), int(day))


def _parse_date_string(s: str) -> tuple[int, int, int] | None:
    m = _DATE_RE.search(s)
    if not m:
        return None
    try:
        return _parse_date_tuple(*m.groups())
    except (ValueError, TypeError):
        return None


# ── 规则 1. protagonist_name_immutable ─────────────────────


def _check_protagonist_name(ctx: HardRuleContext) -> HardRuleViolation | None:
    current_state = ctx.truth_file.get("current_state") or {}
    protagonist = current_state.get("protagonist_name")
    if not protagonist:
        return None
    if protagonist not in ctx.draft_text:
        return HardRuleViolation(
            rule_id="protagonist_name_immutable",
            severity="blocker",
            evidence=f"真相文件声明主角为「{protagonist}」，但本章未出现该姓名",
            suggested_fix=(
                f"确保「{protagonist}」在本章至少出现一次；"
                f"若主角改名，请先在真相文件 current_state.protagonist_name 更新"
            ),
        )
    return None


# ── 规则 2. chapter_word_range ─────────────────────────────


def _check_word_range(ctx: HardRuleContext) -> HardRuleViolation | None:
    count = _count_chinese_chars(ctx.draft_text)
    low, high = ctx.expected_word_range
    if count < low:
        return HardRuleViolation(
            rule_id="chapter_word_range",
            severity="blocker",
            evidence=f"本章中文字数 {count}，低于下限 {low}",
            suggested_fix=f"扩写至 {low}-{high} 字区间",
        )
    if count > high:
        return HardRuleViolation(
            rule_id="chapter_word_range",
            severity="warning",
            evidence=f"本章中文字数 {count}，超过上限 {high}",
            suggested_fix=f"建议精简至 {low}-{high} 字区间",
        )
    return None


# ── 规则 3. timeline_monotonic ─────────────────────────────


def _check_timeline_monotonic(ctx: HardRuleContext) -> HardRuleViolation | None:
    matches = _DATE_RE.findall(ctx.draft_text)
    if not matches:
        return None

    try:
        dates = [_parse_date_tuple(*m) for m in matches]
    except (ValueError, TypeError):
        return None

    # 章内单调递增（等于允许，用于同日多段）
    for i in range(1, len(dates)):
        if dates[i] < dates[i - 1]:
            return HardRuleViolation(
                rule_id="timeline_monotonic",
                severity="warning",
                evidence=f"本章内日期非单调: {dates[i - 1]} → {dates[i]}",
                suggested_fix="加入倒叙/回忆标记（如「回忆起……」「当年……」），或修正日期",
            )

    # 与上章末对比
    baseline_str = (ctx.truth_file.get("current_state") or {}).get("current_date")
    if baseline_str:
        base = _parse_date_string(baseline_str)
        if base and dates[0] < base:
            return HardRuleViolation(
                rule_id="timeline_monotonic",
                severity="warning",
                evidence=f"本章起始日期 {dates[0]} 早于上章结束 {base}",
                suggested_fix="确认是否有回忆/倒叙铺垫，或修正日期",
            )
    return None


# ── 规则 4. dead_character_stays_dead ──────────────────────


def _check_dead_stays_dead(ctx: HardRuleContext) -> HardRuleViolation | None:
    current_state = ctx.truth_file.get("current_state") or {}
    dead = current_state.get("dead_characters") or []
    if not dead:
        return None

    has_flashback = any(m in ctx.draft_text for m in _FLASHBACK_MARKERS)
    for name in dead:
        if not name or not isinstance(name, str):
            continue
        if name in ctx.draft_text:
            if has_flashback:
                continue
            return HardRuleViolation(
                rule_id="dead_character_stays_dead",
                severity="blocker",
                evidence=f"已宣告死亡的角色「{name}」出现在本章，但未见回忆/倒叙标记",
                suggested_fix=(
                    f"若为回忆/倒叙，加入「回忆起」「当年」等标记；"
                    f"若是复活剧情，请先在真相文件更新「{name}」的状态"
                ),
            )
    return None


# ── 规则 5. foreshadow_recovery_deadline ───────────────────


def _check_foreshadow_deadline(ctx: HardRuleContext) -> HardRuleViolation | None:
    overdue: list[dict] = []
    for fs in ctx.active_foreshadows or []:
        try:
            deadline = int(fs.get("recovery_deadline", 0) or 0)
        except (TypeError, ValueError):
            continue
        if deadline <= 0 or ctx.chapter_number <= deadline:
            continue
        # 本章是否正在回收？用描述的前 6 字作为关键词签名
        desc = fs.get("description") or ""
        sig = desc[:6]
        if sig and sig in ctx.draft_text:
            continue
        overdue.append(fs)

    if not overdue:
        return None

    preview = ", ".join(
        f"{fs.get('foreshadow_id', '?')}({(fs.get('description') or '')[:20]})"
        for fs in overdue[:3]
    )
    return HardRuleViolation(
        rule_id="foreshadow_recovery_deadline",
        severity="warning",
        evidence=f"已超期伏笔 {len(overdue)} 条: {preview}",
        suggested_fix="在近几章内回收，或在真相文件中将对应伏笔标记为 abandoned",
    )


# ── 规则 6. no_outline_skip ────────────────────────────────


def _check_no_outline_skip(ctx: HardRuleContext) -> HardRuleViolation | None:
    summaries = ctx.truth_file.get("chapter_summaries") or {}
    if not summaries:
        return None
    summary = summaries.get(str(ctx.chapter_number)) or summaries.get(ctx.chapter_number)
    if not summary or not isinstance(summary, dict):
        return None
    beats = summary.get("key_beats") or []
    if not beats:
        return None

    missing: list[str] = []
    for beat in beats:
        if not beat or not isinstance(beat, str) or len(beat) < 2:
            continue
        sig = beat[:4]  # 用前 4 字做关键词签名（对中文节拍描述足够）
        if sig and sig not in ctx.draft_text:
            missing.append(beat)

    if not missing:
        return None
    preview = ", ".join(missing[:3])
    return HardRuleViolation(
        rule_id="no_outline_skip",
        severity="warning",
        evidence=f"大纲关键节拍未体现: {preview}",
        suggested_fix="补写这些节拍，或在真相文件 chapter_summaries 中更新节拍",
    )


# ── 规则注册表 ──────────────────────────────────────────────


HARD_RULES: list[HardRule] = [
    HardRule(
        id="protagonist_name_immutable",
        description="真相文件声明的主角姓名必须在本章出现",
        category="character",
        severity="blocker",
        check=_check_protagonist_name,
    ),
    HardRule(
        id="chapter_word_range",
        description="章节字数必须落在目标区间内",
        category="structure",
        severity="blocker",
        check=_check_word_range,
    ),
    HardRule(
        id="timeline_monotonic",
        description="章内日期单调递增；不早于上章末时间",
        category="continuity",
        severity="warning",
        check=_check_timeline_monotonic,
    ),
    HardRule(
        id="dead_character_stays_dead",
        description="已死亡角色不可在当下场景出现（回忆除外）",
        category="continuity",
        severity="blocker",
        check=_check_dead_stays_dead,
    ),
    HardRule(
        id="foreshadow_recovery_deadline",
        description="已超期的伏笔必须在近章回收或明确 abandon",
        category="foreshadow",
        severity="warning",
        check=_check_foreshadow_deadline,
    ),
    HardRule(
        id="no_outline_skip",
        description="大纲关键节拍必须在正文中有所体现",
        category="structure",
        severity="warning",
        check=_check_no_outline_skip,
    ),
]


def run_hard_rules(ctx: HardRuleContext) -> list[HardRuleViolation]:
    """按顺序执行全部硬规则，返回违反的规则列表（空列表 = 全过）。

    若某条规则内部抛异常，会被吸收为 severity=info 的 violation，
    保证单条规则 bug 不会让整个审稿流程崩溃。
    """
    violations: list[HardRuleViolation] = []
    for rule in HARD_RULES:
        try:
            v = rule.check(ctx)
        except Exception as e:  # noqa: BLE001
            violations.append(
                HardRuleViolation(
                    rule_id=rule.id,
                    severity="info",
                    evidence=f"规则内部错误: {e!s}",
                    suggested_fix=None,
                )
            )
            continue
        if v is not None:
            violations.append(v)
    return violations
