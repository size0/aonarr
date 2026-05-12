"""hard_rules 单元测试 — Track F · Week 1 · Claude-A"""
from __future__ import annotations

import time

import pytest

from app.services.audit.hard_rules import (
    HARD_RULES,
    HardRule,
    HardRuleContext,
    HardRuleViolation,
    run_hard_rules,
)


# ── 工具 ─────────────────────────────────────────────────────

def _make_ctx(**overrides) -> HardRuleContext:
    """构造默认合法的 HardRuleContext，测试时只覆盖关心的字段。"""
    defaults = dict(
        novel_id="test_novel",
        chapter_number=5,
        draft_text="这是一段测试文本。" * 500,  # ~3500 Chinese chars
        truth_file={},
        active_foreshadows=[],
        expected_word_range=(2800, 4500),
    )
    defaults.update(overrides)
    return HardRuleContext(**defaults)  # type: ignore[arg-type]


def _has(violations: list[HardRuleViolation], rule_id: str) -> bool:
    return any(v.rule_id == rule_id for v in violations)


def _get(violations: list[HardRuleViolation], rule_id: str) -> HardRuleViolation | None:
    for v in violations:
        if v.rule_id == rule_id:
            return v
    return None


# ── 1. protagonist_name_immutable ────────────────────────────

class TestProtagonistNameImmutable:
    def test_name_present(self):
        ctx = _make_ctx(
            draft_text="苏明走在路上，心中无限感慨。" * 300,
            truth_file={"current_state": {"protagonist_name": "苏明"}},
        )
        assert not _has(run_hard_rules(ctx), "protagonist_name_immutable")

    def test_name_missing(self):
        ctx = _make_ctx(
            draft_text="他走在路上，心中无限感慨。" * 300,
            truth_file={"current_state": {"protagonist_name": "苏明"}},
        )
        v = _get(run_hard_rules(ctx), "protagonist_name_immutable")
        assert v is not None
        assert v.severity == "blocker"
        assert "苏明" in v.evidence

    def test_no_truth_file_skips(self):
        ctx = _make_ctx(draft_text="他走在路上。" * 300, truth_file={})
        assert not _has(run_hard_rules(ctx), "protagonist_name_immutable")

    def test_no_protagonist_in_truth_file_skips(self):
        ctx = _make_ctx(
            draft_text="他走在路上。" * 300,
            truth_file={"current_state": {"dead_characters": []}},
        )
        assert not _has(run_hard_rules(ctx), "protagonist_name_immutable")


# ── 2. chapter_word_range ────────────────────────────────────

class TestChapterWordRange:
    def test_within_range(self):
        # "这是一段测试文本。" has 8 Chinese chars, × 500 = 4000
        ctx = _make_ctx(draft_text="这是一段测试文本。" * 500)
        assert not _has(run_hard_rules(ctx), "chapter_word_range")

    def test_below_range_blocker(self):
        ctx = _make_ctx(draft_text="很短的文本。", expected_word_range=(2800, 4500))
        v = _get(run_hard_rules(ctx), "chapter_word_range")
        assert v is not None
        assert v.severity == "blocker"

    def test_above_range_warning(self):
        # 8 Chinese chars × 2000 = 16000
        ctx = _make_ctx(draft_text="超长的文本内容。" * 2000, expected_word_range=(2800, 4500))
        v = _get(run_hard_rules(ctx), "chapter_word_range")
        assert v is not None
        assert v.severity == "warning"

    def test_empty_text_blocker(self):
        ctx = _make_ctx(draft_text="", expected_word_range=(2800, 4500))
        v = _get(run_hard_rules(ctx), "chapter_word_range")
        assert v is not None
        assert v.severity == "blocker"


# ── 3. timeline_monotonic ────────────────────────────────────

class TestTimelineMonotonic:
    def test_no_dates_skips(self):
        ctx = _make_ctx(truth_file={"current_state": {"current_date": "2024年3月5日"}})
        assert not _has(run_hard_rules(ctx), "timeline_monotonic")

    def test_single_date_ok(self):
        # 只有一个不同日期出现，且穿插大量正文以保证字数合法
        ctx = _make_ctx(
            draft_text="2024年3月10日，他出发了，走了很久很久。" + "他走在路上思考人生的意义。" * 200
        )
        assert not _has(run_hard_rules(ctx), "timeline_monotonic")

    def test_dates_monotonic_increasing(self):
        # 两个日期递增，字数用其它文本凑足
        draft = (
            "2024年3月10日出发。"
            + "他走在路上思考人生的意义。" * 200
            + "2024年3月12日到达目的地。"
        )
        ctx = _make_ctx(draft_text=draft)
        assert not _has(run_hard_rules(ctx), "timeline_monotonic")

    def test_dates_non_monotonic(self):
        # 两个日期倒序出现
        draft = (
            "2024年3月15日到达。"
            + "他走在路上思考人生的意义。" * 200
            + "2024年3月5日出发。"
        )
        ctx = _make_ctx(draft_text=draft)
        v = _get(run_hard_rules(ctx), "timeline_monotonic")
        assert v is not None
        assert v.severity == "warning"

    def test_date_before_baseline(self):
        draft = "2024年1月1日，他开始行动。" + "他走在路上思考人生的意义。" * 200
        ctx = _make_ctx(
            draft_text=draft,
            truth_file={"current_state": {"current_date": "2024年3月5日"}},
        )
        v = _get(run_hard_rules(ctx), "timeline_monotonic")
        assert v is not None
        assert v.severity == "warning"

    def test_date_after_baseline(self):
        draft = "2024年4月1日，他出发了。" + "他走在路上思考人生的意义。" * 200
        ctx = _make_ctx(
            draft_text=draft,
            truth_file={"current_state": {"current_date": "2024年3月5日"}},
        )
        assert not _has(run_hard_rules(ctx), "timeline_monotonic")


# ── 4. dead_character_stays_dead ─────────────────────────────

class TestDeadCharacterStaysDead:
    def test_no_dead_characters_skips(self):
        ctx = _make_ctx(
            draft_text="苏明走在路上。" * 300,
            truth_file={"current_state": {"protagonist_name": "苏明"}},
        )
        assert not _has(run_hard_rules(ctx), "dead_character_stays_dead")

    def test_dead_not_mentioned(self):
        ctx = _make_ctx(
            draft_text="苏明走在路上。" * 300,
            truth_file={"current_state": {"protagonist_name": "苏明", "dead_characters": ["张三"]}},
        )
        assert not _has(run_hard_rules(ctx), "dead_character_stays_dead")

    def test_dead_mentioned_no_flashback_blocker(self):
        ctx = _make_ctx(
            draft_text="苏明走在路上。张三朝他走来打招呼。" * 150,
            truth_file={"current_state": {"protagonist_name": "苏明", "dead_characters": ["张三"]}},
        )
        v = _get(run_hard_rules(ctx), "dead_character_stays_dead")
        assert v is not None
        assert v.severity == "blocker"
        assert "张三" in v.evidence

    def test_dead_in_flashback_pass(self):
        ctx = _make_ctx(
            draft_text="苏明回忆起往事，张三曾经帮助过他。" * 150,
            truth_file={"current_state": {"protagonist_name": "苏明", "dead_characters": ["张三"]}},
        )
        assert not _has(run_hard_rules(ctx), "dead_character_stays_dead")


# ── 5. foreshadow_recovery_deadline ──────────────────────────

class TestForeshadowRecoveryDeadline:
    def test_no_foreshadows_skips(self):
        ctx = _make_ctx(active_foreshadows=[])
        assert not _has(run_hard_rules(ctx), "foreshadow_recovery_deadline")

    def test_foreshadow_within_deadline(self):
        ctx = _make_ctx(
            chapter_number=10,
            active_foreshadows=[
                {"foreshadow_id": "fs1", "description": "一把断剑", "recovery_deadline": 50},
            ],
        )
        assert not _has(run_hard_rules(ctx), "foreshadow_recovery_deadline")

    def test_foreshadow_overdue(self):
        ctx = _make_ctx(
            chapter_number=55,
            draft_text="主角一如既往地修行。" * 300,
            active_foreshadows=[
                {"foreshadow_id": "fs1", "description": "一把断剑的秘密", "recovery_deadline": 50},
            ],
        )
        v = _get(run_hard_rules(ctx), "foreshadow_recovery_deadline")
        assert v is not None
        assert v.severity == "warning"

    def test_foreshadow_being_resolved_this_chapter(self):
        ctx = _make_ctx(
            chapter_number=55,
            draft_text="他终于再次看到了一把断剑的秘密被揭开。" * 100,
            active_foreshadows=[
                {"foreshadow_id": "fs1", "description": "一把断剑的秘密", "recovery_deadline": 50},
            ],
        )
        assert not _has(run_hard_rules(ctx), "foreshadow_recovery_deadline")

    def test_foreshadow_no_deadline_skipped(self):
        ctx = _make_ctx(
            chapter_number=100,
            active_foreshadows=[
                {"foreshadow_id": "fs1", "description": "某个伏笔", "recovery_deadline": 0},
            ],
        )
        assert not _has(run_hard_rules(ctx), "foreshadow_recovery_deadline")


# ── 6. no_outline_skip ───────────────────────────────────────

class TestNoOutlineSkip:
    def test_no_outline_data_skips(self):
        ctx = _make_ctx(chapter_number=5, truth_file={})
        assert not _has(run_hard_rules(ctx), "no_outline_skip")

    def test_no_chapter_summary_skips(self):
        ctx = _make_ctx(chapter_number=5, truth_file={"chapter_summaries": {"3": {"key_beats": ["x"]}}})
        assert not _has(run_hard_rules(ctx), "no_outline_skip")

    def test_outline_beats_covered(self):
        ctx = _make_ctx(
            chapter_number=5,
            draft_text="主角遭遇劫匪，经过一番搏斗，获得胜利并逃脱。" * 100,
            truth_file={
                "chapter_summaries": {
                    "5": {"key_beats": ["主角遭遇劫匪", "获得胜利"]}
                }
            },
        )
        assert not _has(run_hard_rules(ctx), "no_outline_skip")

    def test_outline_beats_missing(self):
        ctx = _make_ctx(
            chapter_number=5,
            draft_text="他在街上悠闲漫步欣赏景色。" * 300,
            truth_file={
                "chapter_summaries": {
                    "5": {"key_beats": ["主角遭遇劫匪", "获得胜利"]}
                }
            },
        )
        v = _get(run_hard_rules(ctx), "no_outline_skip")
        assert v is not None
        assert v.severity == "warning"

    def test_empty_key_beats_skips(self):
        ctx = _make_ctx(
            chapter_number=5,
            truth_file={"chapter_summaries": {"5": {"key_beats": []}}},
        )
        assert not _has(run_hard_rules(ctx), "no_outline_skip")


# ── 综合测试 ────────────────────────────────────────────────

class TestRunHardRules:
    def test_all_pass(self):
        ctx = _make_ctx(
            draft_text="苏明走在路上，心中无限感慨。" * 300,
            truth_file={"current_state": {"protagonist_name": "苏明"}},
        )
        assert run_hard_rules(ctx) == []

    def test_multiple_violations(self):
        ctx = _make_ctx(
            chapter_number=55,
            draft_text="他走在路上。",  # 太短 + 主角名缺失
            truth_file={"current_state": {"protagonist_name": "苏明"}},
            active_foreshadows=[
                {"foreshadow_id": "fs1", "description": "一把断剑", "recovery_deadline": 50},
            ],
            expected_word_range=(2800, 4500),
        )
        violations = run_hard_rules(ctx)
        rule_ids = {v.rule_id for v in violations}
        assert "chapter_word_range" in rule_ids
        assert "protagonist_name_immutable" in rule_ids
        assert "foreshadow_recovery_deadline" in rule_ids

    def test_rule_exception_does_not_crash(self, monkeypatch):
        """某条规则内部异常时，其他规则仍应执行。"""
        import app.services.audit.hard_rules as hr

        def _boom(_ctx):
            raise RuntimeError("simulated rule crash")

        # 替换第一条规则为会抛异常的版本
        monkeypatch.setattr(hr.HARD_RULES[0], "check", _boom)

        ctx = _make_ctx()
        violations = run_hard_rules(ctx)
        # 不应抛异常；异常被吸收为 info 级违反
        assert any(v.severity == "info" and "simulated rule crash" in v.evidence for v in violations)

    def test_performance(self):
        """单次 run_hard_rules 平均 ≤ 10ms（含全部 6 条规则）。"""
        # 大约 32K 中文字符的 draft
        ctx = _make_ctx(draft_text="苏明走在路上，心中无限感慨。" * 3000)
        # 预热
        run_hard_rules(ctx)
        start = time.perf_counter()
        for _ in range(50):
            run_hard_rules(ctx)
        elapsed = time.perf_counter() - start
        avg_ms = elapsed / 50 * 1000
        assert avg_ms < 10, f"avg per call = {avg_ms:.2f}ms, expected < 10ms"


class TestHardRulesRegistry:
    def test_six_rules_present(self):
        rule_ids = {r.id for r in HARD_RULES}
        expected = {
            "protagonist_name_immutable",
            "chapter_word_range",
            "timeline_monotonic",
            "dead_character_stays_dead",
            "foreshadow_recovery_deadline",
            "no_outline_skip",
        }
        missing = expected - rule_ids
        assert not missing, f"missing rules: {missing}"

    def test_rules_have_metadata(self):
        for rule in HARD_RULES:
            assert rule.id
            assert rule.description
            assert rule.category in {"character", "structure", "continuity", "foreshadow", "style"}
            assert rule.severity in {"info", "warning", "blocker"}
            assert callable(rule.check)
            # 签名：只接受 HardRuleContext
            import inspect
            params = list(inspect.signature(rule.check).parameters.values())
            assert len(params) == 1

    def test_rule_ids_unique(self):
        ids = [r.id for r in HARD_RULES]
        assert len(ids) == len(set(ids)), f"重复 rule id: {[x for x in ids if ids.count(x) > 1]}"
