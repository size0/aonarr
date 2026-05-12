"""MuyuEditor 单元测试 — Track F · Week 1 · Claude-A

覆盖：
- happy path（mock LLM 返回合法 JSON）
- 硬规则 blocker → 跳过 LLM 直接 rewrite
- LLM 不可用 → 本地启发式 fallback
- LLM JSON 解析（含 markdown 围栏 / 残缺）
- ReviewResult schema 一致性
- event_store=None 不写事件 / 传入时调用 append
- 异常路径（章节不存在 / 空内容）
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass

import pytest

from app.db.connection import Base, SessionLocal, engine
from app.models.novel import Chapter, Novel, TruthFile
from app.services.audit import consistency_checker
from app.services.audit.consistency_checker import ConsistencyReport
from app.services.inspiration import editor_mode as em
from app.services.inspiration.editor_mode import (
    Annotation,
    MuyuEditor,
    NextAction,
    ReviewResult,
)


# ── 测试 fixture ─────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema():
    """确保测试数据库 schema 存在（conftest 已切到 tmp 数据库）"""
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def sample_novel(db_session):
    novel = Novel(
        id=str(uuid.uuid4()),
        title="测试小说",
        words_per_chapter=3000,
        target_chapter_count=200,
    )
    db_session.add(novel)
    db_session.commit()
    yield novel
    # 清理
    db_session.query(TruthFile).filter_by(novel_id=novel.id).delete()
    db_session.query(Chapter).filter_by(novel_id=novel.id).delete()
    db_session.query(Novel).filter_by(id=novel.id).delete()
    db_session.commit()


def _make_chapter(db, novel_id: str, number: int, content: str) -> Chapter:
    ch = Chapter(
        id=str(uuid.uuid4()),
        novel_id=novel_id,
        number=number,
        title=f"第{number}章",
        content=content,
        word_count=len(content),
    )
    db.add(ch)
    db.commit()
    return ch


def _normal_content() -> str:
    """生成一段含主角名「苏明」、字数落在 2400-3900 区间的合法草稿。"""
    para = "苏明走在街上，思考着昨夜发生的事情。" + "他望向远方的天空，心中升起一丝疑虑。" * 8
    # 153 中文字符/段 × 18 段 ≈ 2750 字，落在 (2400, 3900) 内
    return (para + "\n\n") * 18


# ── Mock LLM 工具 ────────────────────────────────────────────


@dataclass
class _FakeGenResult:
    content: str = ""
    model: str = "fake"
    input_tokens: int = 100
    output_tokens: int = 200
    finish_reason: str = "stop"


class _FakeLLMClient:
    """假 LLMClient，不发出真实 HTTP 请求。"""

    def __init__(self, response: str = ""):
        self._response = response

    @property
    def model(self) -> str:
        return "fake-model"

    async def generate(self, prompt: str, config=None):
        return _FakeGenResult(content=self._response)


def _llm_response_pass() -> str:
    return json.dumps(
        {
            "decision": "pass",
            "overall_score": 85.0,
            "dimensions": {
                "naturalness": 88,
                "reading_power": 80,
                "pacing": 82,
                "dialogue": 75,
                "foreshadowing": 70,
                "continuity": 90,
                "ai_detect": 85,
                "vocab_diversity": 78,
                "emotion_arc": 80,
                "sentence_variety": 82,
            },
            "summary": "本章节奏稳健，主角动机清晰，仅有少量风格瑕疵。",
            "annotations": [
                {
                    "location": {"paragraph": 2, "char_range": [10, 50]},
                    "category": "style",
                    "severity": "info",
                    "issue": "段首句重复",
                    "suggestion": "替换为不同句首词",
                    "evidence": [],
                    "auto_fixable": True,
                }
            ],
            "next_action": {"action": "pass", "target": None, "payload": {}},
        },
        ensure_ascii=False,
    )


def _llm_response_revise_with_fence() -> str:
    inner = json.dumps(
        {
            "decision": "revise",
            "overall_score": 62.0,
            "dimensions": {},
            "summary": "节奏偏慢，需要修订。",
            "annotations": [],
            "next_action": {
                "action": "trigger_revision",
                "target": "revision_loop",
                "payload": {"focus": "pacing"},
            },
        },
        ensure_ascii=False,
    )
    return f"```json\n{inner}\n```"


def _llm_response_malformed() -> str:
    return "this is not json at all 这不是 JSON"


def _patch_llm(monkeypatch, llm_client: _FakeLLMClient | None):
    """让 StageModelResolver.get_llm_for_stage 返回我们的假客户端，或者抛错"""

    def _fake_get_llm_for_stage(self, stage: str):  # noqa: ARG001
        if llm_client is None:
            raise ValueError("LLM not configured (test)")
        return llm_client

    from app.llm.resolver import StageModelResolver

    monkeypatch.setattr(StageModelResolver, "get_llm_for_stage", _fake_get_llm_for_stage)

    # 同时屏蔽 consistency_checker 真实调用（其内部会再调 LLM）
    async def _fake_consistency(db, llm, novel_id):  # noqa: ARG001
        return ConsistencyReport(novel_id=novel_id, issues=[], checked_chapters=0)

    monkeypatch.setattr(consistency_checker, "check_full_consistency", _fake_consistency)


# ── 测试 ────────────────────────────────────────────────────


class TestReviewResultSchema:
    def test_review_result_required_fields(self):
        r = ReviewResult(
            decision="pass",
            overall_score=80.0,
            summary="ok",
            next_action=NextAction(action="pass"),
        )
        d = r.model_dump()
        for key in ("decision", "overall_score", "dimensions", "summary",
                    "annotations", "next_action", "elapsed_ms", "tokens_used"):
            assert key in d

    def test_decision_literal(self):
        with pytest.raises(Exception):
            ReviewResult(decision="invalid", overall_score=0, summary="", next_action=NextAction(action="pass"))


class TestHappyPath:
    def test_review_pass(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_pass()))
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        editor = MuyuEditor(db_session, event_store=None)
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1))

        assert isinstance(result, ReviewResult)
        assert result.decision == "pass"
        assert result.overall_score == 85.0
        assert result.next_action.action == "pass"
        assert len(result.annotations) >= 1
        assert result.tokens_used == 300  # 100 + 200
        assert result.elapsed_ms >= 0

    def test_review_revise_with_markdown_fence(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_revise_with_fence()))
        _make_chapter(db_session, sample_novel.id, 2, _normal_content())

        editor = MuyuEditor(db_session)
        result = asyncio.run(editor.review_chapter(sample_novel.id, 2))

        assert result.decision == "revise"
        assert result.next_action.action == "trigger_revision"
        assert result.next_action.target == "revision_loop"


class TestHardRuleBlocker:
    def test_word_range_blocker_skips_llm(self, monkeypatch, db_session, sample_novel):
        # LLM 配成会被调用就 fail，证明没有调用 LLM
        called = {"n": 0}

        class _BoomLLM(_FakeLLMClient):
            async def generate(self, prompt, config=None):
                called["n"] += 1
                raise AssertionError("LLM should NOT be called when blocker hits")

        _patch_llm(monkeypatch, _BoomLLM(""))

        # 章节内容超短，必中 chapter_word_range blocker
        _make_chapter(db_session, sample_novel.id, 1, "苏明很短。")

        editor = MuyuEditor(db_session)
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1))

        assert result.decision == "rewrite"
        assert result.next_action.action == "trigger_rewrite"
        assert result.next_action.payload.get("reason") == "hard_rule_blocker"
        assert "chapter_word_range" in result.next_action.payload.get("blocker_ids", [])
        assert result.tokens_used == 0
        assert called["n"] == 0

    def test_protagonist_missing_blocker_with_truth_file(
        self, monkeypatch, db_session, sample_novel
    ):
        # 写 truth_file，但章节正文不出现主角名
        tf = TruthFile(
            id=str(uuid.uuid4()),
            novel_id=sample_novel.id,
            file_key="current_state",
            data_json=json.dumps({"protagonist_name": "李四"}),
        )
        db_session.add(tf)
        db_session.commit()

        # content 不包含「李四」
        text = "他走在街上。" + "天空一片蓝。" * 200
        _make_chapter(db_session, sample_novel.id, 1, text)

        _patch_llm(monkeypatch, _FakeLLMClient("should not be called"))

        editor = MuyuEditor(db_session)
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1))
        assert result.decision == "rewrite"
        assert "protagonist_name_immutable" in result.next_action.payload.get("blocker_ids", [])


class TestFallbackPaths:
    def test_no_llm_fallback(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, None)  # 不可用
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        editor = MuyuEditor(db_session)
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1))

        # 走本地启发式，不会抛错
        assert result.decision in {"pass", "revise", "rewrite"}
        assert "本地启发式" in result.summary
        assert result.tokens_used == 0

    def test_llm_malformed_response_falls_back(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_malformed()))
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        editor = MuyuEditor(db_session)
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1))

        # parse 返回空 dict，走 fallback
        assert result.decision in {"pass", "revise", "rewrite"}
        assert "本地启发式" in result.summary

    def test_llm_exception_falls_back(self, monkeypatch, db_session, sample_novel):
        class _ErrLLM(_FakeLLMClient):
            async def generate(self, prompt, config=None):
                raise RuntimeError("simulated LLM failure")

        _patch_llm(monkeypatch, _ErrLLM())
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        editor = MuyuEditor(db_session)
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1))

        assert result.decision in {"pass", "revise", "rewrite"}
        assert "本地启发式" in result.summary


class TestErrorPaths:
    def test_novel_not_found(self, monkeypatch, db_session):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_pass()))
        editor = MuyuEditor(db_session)
        with pytest.raises(ValueError, match="Novel .* not found"):
            asyncio.run(editor.review_chapter("nonexistent_id", 1))

    def test_chapter_not_found(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_pass()))
        editor = MuyuEditor(db_session)
        with pytest.raises(ValueError, match="Chapter .* not found"):
            asyncio.run(editor.review_chapter(sample_novel.id, 99))

    def test_empty_content_raises(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_pass()))
        _make_chapter(db_session, sample_novel.id, 1, "   \n\n  ")

        editor = MuyuEditor(db_session)
        with pytest.raises(ValueError, match="empty content"):
            asyncio.run(editor.review_chapter(sample_novel.id, 1))


class TestEventStore:
    def test_event_store_none_no_emit(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_pass()))
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        editor = MuyuEditor(db_session, event_store=None)
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1))
        assert result.decision == "pass"  # 仅证明不出错

    def test_event_store_emits_when_session_id(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_pass()))
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        events: list[dict] = []

        class _StubEventStore:
            async def append(self, **kwargs):
                events.append(kwargs)
                return len(events)

        editor = MuyuEditor(db_session, event_store=_StubEventStore())
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1, session_id="sess_test"))

        types = [e["event_type"] for e in events]
        assert "review_started" in types
        assert "review_completed" in types
        assert all(e["actor"] == "muyu_editor" for e in events)
        assert result.decision == "pass"

    def test_event_store_no_session_no_emit(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_pass()))
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        events: list[dict] = []

        class _StubEventStore:
            async def append(self, **kwargs):
                events.append(kwargs)
                return len(events)

        editor = MuyuEditor(db_session, event_store=_StubEventStore())
        # session_id=None：不应写事件
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1, session_id=None))
        assert events == []
        assert result.decision == "pass"

    def test_event_store_blocker_emits_violation(
        self, monkeypatch, db_session, sample_novel
    ):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_pass()))
        _make_chapter(db_session, sample_novel.id, 1, "苏明很短。")  # 字数过少

        events: list[dict] = []

        class _StubEventStore:
            async def append(self, **kwargs):
                events.append(kwargs)
                return len(events)

        editor = MuyuEditor(db_session, event_store=_StubEventStore())
        result = asyncio.run(editor.review_chapter(sample_novel.id, 1, session_id="sess_x"))

        types = [e["event_type"] for e in events]
        assert "hard_rule_violation" in types
        assert result.decision == "rewrite"


class TestParseLLMJson:
    def test_parse_clean_json(self):
        editor = MuyuEditor(db=None)  # type: ignore[arg-type]
        out = editor._parse_llm_json('{"a": 1}')
        assert out == {"a": 1}

    def test_parse_markdown_fence(self):
        editor = MuyuEditor(db=None)  # type: ignore[arg-type]
        out = editor._parse_llm_json('```json\n{"a": 1}\n```')
        assert out == {"a": 1}

    def test_parse_with_preamble(self):
        editor = MuyuEditor(db=None)  # type: ignore[arg-type]
        out = editor._parse_llm_json('blabla here is your json: {"a": 1} thanks')
        assert out == {"a": 1}

    def test_parse_invalid_returns_empty(self):
        editor = MuyuEditor(db=None)  # type: ignore[arg-type]
        assert editor._parse_llm_json("not json at all") == {}

    def test_parse_empty_string(self):
        editor = MuyuEditor(db=None)  # type: ignore[arg-type]
        assert editor._parse_llm_json("") == {}


class TestNextActionMapping:
    def test_pass_decision_maps(self):
        editor = MuyuEditor(db=None)  # type: ignore[arg-type]
        na = editor._build_next_action("pass", None)
        assert na.action == "pass"
        assert na.target is None

    def test_revise_decision_maps(self):
        editor = MuyuEditor(db=None)  # type: ignore[arg-type]
        na = editor._build_next_action("revise", None)
        assert na.action == "trigger_revision"
        assert na.target == "revision_loop"

    def test_rewrite_decision_maps(self):
        editor = MuyuEditor(db=None)  # type: ignore[arg-type]
        na = editor._build_next_action("rewrite", None)
        assert na.action == "trigger_rewrite"
        assert na.target == "writer_agent"

    def test_invalid_action_in_dict_falls_back_to_default(self):
        editor = MuyuEditor(db=None)  # type: ignore[arg-type]
        na = editor._build_next_action("revise", {"action": "unknown_action"})
        assert na.action == "trigger_revision"  # 退回默认


class TestComputeWordRange:
    def test_default_3000(self):
        n = Novel(words_per_chapter=3000)
        low, high = MuyuEditor._compute_word_range(n)
        assert low == 2400  # 3000 * 0.8
        assert high == 3900  # 3000 * 1.3

    def test_zero_target_uses_default_3000(self):
        n = Novel(words_per_chapter=0)
        low, high = MuyuEditor._compute_word_range(n)
        assert low > 0 and high > low


class TestStreamingReview:
    def test_streaming_yields_stages(self, monkeypatch, db_session, sample_novel):
        _patch_llm(monkeypatch, _FakeLLMClient(_llm_response_pass()))
        _make_chapter(db_session, sample_novel.id, 1, _normal_content())

        editor = MuyuEditor(db_session)

        async def _collect():
            out = []
            async for ev in editor.review_chapter_streaming(sample_novel.id, 1):
                out.append(ev)
            return out

        events = asyncio.run(_collect())
        types = [e["type"] for e in events]
        assert "stage" in types
        assert "result" in types
        # 最后一条必须是 result
        assert events[-1]["type"] == "result"
