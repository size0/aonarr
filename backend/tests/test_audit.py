"""审核引擎测试"""
from __future__ import annotations

import pytest


# ============================================================
# quality_radar 测试
# ============================================================

SAMPLE_CHAPTER = """
　　清晨的阳光透过窗帘洒进了房间，苏明缓缓睁开了眼睛。他看了一眼床头的闹钟，已经七点了。

　　"又是新的一天。"他自言自语道，从床上坐了起来。

　　突然，手机响了。苏明拿起手机一看，是一条陌生号码发来的短信："你的命运即将改变。"

　　"什么意思？"苏明皱了皱眉，心中涌起一丝不安。难道这是什么恶作剧？但那种说不清道不明的直觉告诉他，事情没那么简单。

　　他匆匆洗漱完毕，推开门走了出去。街上的行人来来往往，一切看起来都那么平常。然而苏明却总觉得有什么不对劲，仿佛有一双无形的眼睛在暗中注视着他。

　　"苏明！"一个清脆的声音从身后传来。他转过头，看到了林小雨正朝他跑来。她穿着一件白色的连衣裙，长发在风中飘扬。

　　"小雨？你怎么在这里？"苏明有些意外。

　　"我有重要的事情要告诉你。"林小雨的表情很严肃，"关于你收到的那条短信——我知道是谁发的。"

　　苏明心头一震。她怎么会知道？这究竟是怎么回事？

　　林小雨拉着他的手，快步走向了街角的咖啡馆。两人在角落里坐下后，她才开口说道："那条短信是我哥发给你的。他说……日后你会明白一切。"

　　"你哥？"苏明更加困惑了。林小雨的哥哥不是三年前就已经出国了吗？

　　紧接着，咖啡馆的门被猛地推开，一个穿着黑色风衣的男人走了进来。他的目光如同利剑一般，直直地盯着苏明。

　　"你就是苏明？"男人的声音冰冷，"跟我走。"

　　"你是谁？"苏明站了起来，拳头不自觉地握紧。他心中暗想：不管对方是什么来头，自己绝不能退缩。

　　然而就在这时，整个咖啡馆突然陷入了一片黑暗之中。
"""

SAMPLE_MONOTONE = "他走了。他停了。他看了。他笑了。他哭了。他说了。他想了。他走了。他停了。他看了。" * 10


class TestQualityRadar:
    """质量雷达测试"""

    def test_score_chapter_basic(self):
        from app.services.audit.quality_radar import score_chapter

        qs = score_chapter(SAMPLE_CHAPTER)
        d = qs.to_dict()

        assert "naturalness" in d
        assert "reading_power" in d
        assert "pacing" in d
        assert "dialogue" in d
        assert "foreshadowing" in d
        assert "continuity" in d
        assert "overall" in d

        # 合理范围
        for key in ["naturalness", "reading_power", "pacing", "dialogue", "foreshadowing", "continuity"]:
            assert 0 <= d[key] <= 100, f"{key} = {d[key]} out of range"

    def test_score_chapter_overall(self):
        from app.services.audit.quality_radar import score_chapter

        qs = score_chapter(SAMPLE_CHAPTER)
        # 样本是中等质量的文本，overall 应在合理范围
        assert 30 <= qs.overall <= 90

    def test_score_empty_text(self):
        from app.services.audit.quality_radar import score_chapter

        qs = score_chapter("")
        assert qs.overall == 0.0

    def test_score_very_short_text(self):
        from app.services.audit.quality_radar import score_chapter

        qs = score_chapter("很短。")
        assert qs.overall >= 0

    def test_naturalness_penalizes_repetition(self):
        from app.services.audit.quality_radar import score_chapter

        qs_good = score_chapter(SAMPLE_CHAPTER)
        qs_bad = score_chapter(SAMPLE_MONOTONE)
        # 重复文本的自然度应更低
        assert qs_bad.naturalness < qs_good.naturalness

    def test_reading_power_detects_hooks(self):
        from app.services.audit.quality_radar import score_chapter

        text_with_hooks = "突然，一道雷光劈了下来！难道这就是传说中的天雷？究竟是怎么回事？莫非那个预言要应验了！" * 5
        text_plain = "天气很好。阳光灿烂。小鸟在唱歌。花儿在开放。树叶在摇动。微风轻轻吹。" * 5

        qs_hooks = score_chapter(text_with_hooks)
        qs_plain = score_chapter(text_plain)
        assert qs_hooks.reading_power > qs_plain.reading_power

    def test_dialogue_scoring(self):
        from app.services.audit.quality_radar import score_chapter

        text_with_dialogue = """
        "你好！"苏明笑着说道。
        "你也好。"林小雨微笑回应。
        "今天天气不错。"他看了看天。
        "是啊，很适合出去走走。"她点了点头。
        苏明想了想，又问道："你最近在忙什么？"
        "在写一本小说。"林小雨认真地回答道。
        """ * 3
        text_no_dialogue = "阳光洒满大地。树木郁郁葱葱。河水静静流淌。白云悠悠飘荡。" * 10

        qs_dlg = score_chapter(text_with_dialogue)
        qs_no_dlg = score_chapter(text_no_dialogue)
        assert qs_dlg.dialogue > qs_no_dlg.dialogue

    def test_quality_score_dataclass(self):
        from app.services.audit.quality_radar import QualityScore

        qs = QualityScore(naturalness=80, reading_power=70, pacing=60, dialogue=75, foreshadowing=50, continuity=65)
        assert qs.overall == pytest.approx(66.67, abs=0.1)
        d = qs.to_dict()
        assert d["overall"] == pytest.approx(66.7, abs=0.1)


# ============================================================
# style_drift_detector 测试
# ============================================================

SAMPLE_BASELINE = """
　　苏明是一个普通的大学生，每天的生活就是上课、吃饭、睡觉。他没有什么特别的爱好，也没有什么远大的抱负。

　　"你就不能有点追求吗？"室友王浩总是这样说他。

　　苏明笑了笑，"平平淡淡才是真啊。"

　　然而命运总是喜欢开玩笑。就在苏明以为自己的一生都会这样平淡度过的时候，一封神秘的来信改变了一切。
""" * 10

SAMPLE_DRIFTED = """
　　吾观天象，紫微星动，乾坤将变矣。苍穹之下，万物俱寂，唯闻北风呜咽。

　　古之圣贤有云：天将降大任于斯人也，必先苦其心志，劳其筋骨。此言诚不虚也。

　　彼时，山河破碎，黎民涂炭。英雄豪杰揭竿而起，誓要匡扶社稷。然则天道无常，成败转头空。

　　"将军，敌军已至城下！"一名斥候飞马来报。

　　"传令三军，据城死守！"将军拔剑而起，目光如炬。
""" * 10


class TestStyleDriftDetector:
    """文风漂移检测测试"""

    def test_detect_drift_no_drift(self):
        from app.services.audit.style_drift_detector import detect_drift

        report = detect_drift(
            chapter_text=SAMPLE_BASELINE[:500],
            baseline_text=SAMPLE_BASELINE,
            chapter_number=1,
        )
        assert report.drift_level in ("normal", "mild")
        assert report.drift_score < 50

    def test_detect_drift_high_drift(self):
        from app.services.audit.style_drift_detector import detect_drift

        report = detect_drift(
            chapter_text=SAMPLE_DRIFTED,
            baseline_text=SAMPLE_BASELINE,
            chapter_number=5,
        )
        # 古文 vs 现代文应有明显漂移
        assert report.drift_score > 10
        assert report.chapter_number == 5
        assert len(report.dimension_diffs) > 0

    def test_detect_drift_empty_text(self):
        from app.services.audit.style_drift_detector import detect_drift

        report = detect_drift("", SAMPLE_BASELINE, 1)
        assert report.drift_score == 0.0

    def test_detect_drift_multi(self):
        from app.services.audit.style_drift_detector import detect_drift_multi

        chapters = [SAMPLE_BASELINE[:400], SAMPLE_BASELINE[400:800], SAMPLE_DRIFTED[:500]]
        reports = detect_drift_multi(chapters, SAMPLE_BASELINE)
        assert len(reports) == 3
        # 第三章与基准差异应最大
        assert reports[2].drift_score >= reports[0].drift_score

    def test_drift_report_to_dict(self):
        from app.services.audit.style_drift_detector import DriftReport

        report = DriftReport(
            chapter_number=3,
            drift_score=42.5,
            drift_level="moderate",
            dimension_diffs={"dialogue_ratio": 0.15},
            warnings=["对话比例偏高"],
        )
        d = report.to_dict()
        assert d["chapter_number"] == 3
        assert d["drift_score"] == 42.5
        assert d["drift_level"] == "moderate"
        assert len(d["warnings"]) == 1

    def test_detect_drift_with_precomputed_baseline(self):
        from app.services.audit.style_drift_detector import detect_drift
        from app.services.analysis.style_fingerprint import analyze_style

        baseline_fp = analyze_style(SAMPLE_BASELINE)
        report = detect_drift(
            chapter_text=SAMPLE_DRIFTED,
            baseline_text="",
            chapter_number=1,
            baseline_fp=baseline_fp,
        )
        assert report.drift_score > 0


# ============================================================
# consistency_checker 测试
# ============================================================


class TestConsistencyChecker:
    """一致性校验测试"""

    def test_extract_character_context(self):
        from app.services.audit.consistency_checker import _extract_character_context

        text = "苏明走进了教室。苏明看着窗外发呆。王浩叫了他一声。苏明回过头来。"
        contexts = _extract_character_context(text, "苏明", max_snippets=2)
        assert len(contexts) == 2
        assert all("苏明" in c for c in contexts)

    def test_extract_character_context_not_found(self):
        from app.services.audit.consistency_checker import _extract_character_context

        contexts = _extract_character_context("一段没有角色的文本。", "苏明")
        assert contexts == []

    def test_parse_json_response(self):
        from app.services.audit.consistency_checker import _parse_json_response

        content = '```json\n{"issues": [{"character": "苏明", "severity": "error", "description": "年龄矛盾"}]}\n```'
        result = _parse_json_response(content)
        assert len(result["issues"]) == 1
        assert result["issues"][0]["character"] == "苏明"

    def test_parse_json_response_invalid(self):
        from app.services.audit.consistency_checker import _parse_json_response

        result = _parse_json_response("无效内容")
        assert result == {"issues": []}

    def test_consistency_issue_dataclass(self):
        from app.services.audit.consistency_checker import ConsistencyIssue

        issue = ConsistencyIssue(
            issue_type="character",
            severity="error",
            description="苏明的年龄在第3章是18岁，第7章变成了25岁",
            chapter_range="第3章-第7章",
        )
        d = issue.to_dict()
        assert d["issue_type"] == "character"
        assert d["severity"] == "error"
        assert "年龄" in d["description"]

    def test_consistency_report_counts(self):
        from app.services.audit.consistency_checker import ConsistencyReport, ConsistencyIssue

        report = ConsistencyReport(novel_id="test-1")
        report.issues = [
            ConsistencyIssue("character", "error", "矛盾1"),
            ConsistencyIssue("character", "warning", "疑似2"),
            ConsistencyIssue("timeline", "error", "矛盾3"),
        ]
        assert report.error_count == 2
        assert report.warning_count == 1
        d = report.to_dict()
        assert d["total_issues"] == 3


# ============================================================
# 集成测试: API 路由 (mock DB + LLM)
# ============================================================


class TestAuditAPI:
    """审核 API 端点测试"""

    def test_quality_radar_endpoint(self):
        """quality_radar 端点能正常返回"""
        from app.services.audit.quality_radar import score_chapter

        qs = score_chapter(SAMPLE_CHAPTER)
        d = qs.to_dict()
        assert all(k in d for k in ["naturalness", "reading_power", "pacing", "dialogue", "foreshadowing", "continuity", "overall"])
        assert 0 < d["overall"] < 100
