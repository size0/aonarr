"""墨语主编 - 编辑/审稿模式 · Track F · Week 1 · Claude-A

为 MuyuEditor 提供单章全维度审稿能力，输出严格符合 ReviewResult schema：
- 先跑硬规则（hard_rules）；任一 blocker 命中则跳过 LLM 直接 rewrite
- 否则并发跑 quality_radar / consistency_checker / style_drift_detector
- 把信号交给 LLM (EDITOR_SYSTEM) 综合判断；LLM 不可用时降级到本地启发式
- 全过程可选写入 EventStore（review_started / hard_rule_violation / review_completed）
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any, AsyncIterator, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.llm.client import GenerationConfig, LLMClient
from app.llm.resolver import StageModelResolver
from app.models.novel import Chapter, Novel, TruthFile
from app.services.audit import consistency_checker, quality_radar, style_drift_detector
from app.services.audit.hard_rules import (
    HardRuleContext,
    HardRuleViolation,
    run_hard_rules,
)
from app.services.inspiration.editor_prompts import EDITOR_SYSTEM

if TYPE_CHECKING:
    from app.services.events.event_store import EventStore  # noqa: F401

logger = logging.getLogger(__name__)


# ── ReviewResult Schema (契约 §2.1) ─────────────────────────

_ANNOTATION_CATEGORIES = {
    "consistency", "style", "pacing", "foreshadow",
    "hard_rule", "dialogue", "ai_taste", "structure",
}
_SEVERITIES = {"info", "warning", "blocker"}
_DECISIONS = {"pass", "revise", "rewrite", "ask_user"}
_ACTIONS = {"pass", "trigger_revision", "trigger_rewrite", "ask_user", "escalate"}


class Annotation(BaseModel):
    location: dict = Field(default_factory=dict)
    category: Literal[
        "consistency", "style", "pacing", "foreshadow",
        "hard_rule", "dialogue", "ai_taste", "structure",
    ]
    severity: Literal["info", "warning", "blocker"]
    issue: str
    suggestion: str | None = None
    evidence: list[dict] = Field(default_factory=list)
    auto_fixable: bool = False


class NextAction(BaseModel):
    action: Literal["pass", "trigger_revision", "trigger_rewrite", "ask_user", "escalate"]
    target: str | None = None
    payload: dict = Field(default_factory=dict)


class ReviewResult(BaseModel):
    decision: Literal["pass", "revise", "rewrite", "ask_user"]
    overall_score: float
    dimensions: dict[str, float] = Field(default_factory=dict)
    summary: str
    annotations: list[Annotation] = Field(default_factory=list)
    next_action: NextAction
    elapsed_ms: int = 0
    tokens_used: int = 0


# ── MuyuEditor ─────────────────────────────────────────────


class MuyuEditor:
    """墨语主编 - 编辑模式"""

    def __init__(self, db: Session, event_store: "EventStore | None" = None):
        """event_store 为 None 时不写事件（第 1 周默认场景）。"""
        self.db = db
        self.event_store = event_store

    async def review_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        session_id: str | None = None,
    ) -> ReviewResult:
        """对某章进行全维度审稿。"""
        t0 = time.time()
        tokens_used = 0

        novel, chapter = self._load_novel_chapter(novel_id, chapter_number)
        draft_text = chapter.content or ""
        if not draft_text.strip():
            raise ValueError(
                f"Chapter {chapter_number} of novel {novel_id} has empty content"
            )

        await self._emit(
            "review_started", novel_id, session_id, chapter_number,
            {"novel_id": novel_id, "chapter_number": chapter_number},
        )

        # 1. 硬规则
        truth_file = self._compile_truth_file(novel_id)
        active_foreshadows = self._load_active_foreshadows(novel_id, truth_file)
        word_range = self._compute_word_range(novel)

        ctx = HardRuleContext(
            novel_id=novel_id,
            chapter_number=chapter_number,
            draft_text=draft_text,
            truth_file=truth_file,
            active_foreshadows=active_foreshadows,
            expected_word_range=word_range,
        )
        violations = run_hard_rules(ctx)
        blockers = [v for v in violations if v.severity == "blocker"]
        for v in blockers:
            await self._emit(
                "hard_rule_violation", novel_id, session_id, chapter_number,
                {
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "evidence": v.evidence,
                    "suggested_fix": v.suggested_fix,
                },
            )

        if blockers:
            result = self._rewrite_for_blockers(blockers, violations, t0)
            await self._emit_completed(novel_id, session_id, chapter_number, result)
            return result

        # 2. 解析 LLM 客户端（容错）
        llm: LLMClient | None = None
        try:
            llm = StageModelResolver(self.db).get_llm_for_stage("audit_review")
        except Exception as e:  # noqa: BLE001
            logger.info("audit_review LLM 未配置，降级本地启发式: %s", e)

        # 3. 并发审核
        baseline_text = self._load_baseline_text(novel_id, chapter_number)
        audits = await self._run_parallel_audits(
            draft_text=draft_text,
            baseline_text=baseline_text,
            chapter_number=chapter_number,
            novel_id=novel_id,
            llm=llm,
        )
        quality_score = audits.get("quality")
        consistency_report = audits.get("consistency")
        drift_report = audits.get("drift")

        # 4. LLM 综合判断（或降级）
        result: ReviewResult | None = None
        if llm is not None:
            try:
                prompt = self._build_editor_prompt(
                    draft_text=draft_text,
                    violations=violations,
                    quality_score=quality_score,
                    consistency_report=consistency_report,
                    drift_report=drift_report,
                    truth_file=truth_file,
                    active_foreshadows=active_foreshadows,
                )
                config = GenerationConfig(system=EDITOR_SYSTEM, temperature=0.3, max_tokens=4000)
                gen = await llm.generate(prompt, config)
                tokens_used = (gen.input_tokens or 0) + (gen.output_tokens or 0)
                parsed = self._parse_llm_json(gen.content)
                if parsed:
                    result = self._build_result_from_llm(
                        parsed=parsed,
                        violations=violations,
                        quality_score=quality_score,
                        elapsed_start=t0,
                        tokens_used=tokens_used,
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("LLM 审稿失败，降级本地启发式: %s", e)

        if result is None:
            result = self._fallback_result(
                violations=violations,
                quality_score=quality_score,
                consistency_report=consistency_report,
                drift_report=drift_report,
                elapsed_start=t0,
                tokens_used=tokens_used,
            )

        await self._emit_completed(novel_id, session_id, chapter_number, result)
        return result

    async def review_chapter_streaming(
        self,
        novel_id: str,
        chapter_number: int,
        session_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """简化流式：阶段标记 + 最终结果。"""
        yield {"type": "stage", "name": "running_hard_rules"}
        result = await self.review_chapter(novel_id, chapter_number, session_id=session_id)
        for ann in result.annotations:
            yield {"type": "annotation", "data": ann.model_dump()}
        yield {"type": "result", "data": result.model_dump()}

    # ── 数据加载 ─────────────────────────────────────────────

    def _load_novel_chapter(self, novel_id: str, chapter_number: int) -> tuple[Novel, Chapter]:
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        if not novel:
            raise ValueError(f"Novel {novel_id} not found")
        chapter = (
            self.db.query(Chapter)
            .filter_by(novel_id=novel_id, number=chapter_number)
            .first()
        )
        if not chapter:
            raise ValueError(
                f"Chapter {chapter_number} of novel {novel_id} not found"
            )
        return novel, chapter

    def _compile_truth_file(self, novel_id: str) -> dict:
        rows = self.db.query(TruthFile).filter_by(novel_id=novel_id).all()
        compiled: dict[str, Any] = {}
        for row in rows:
            try:
                compiled[row.file_key] = json.loads(row.data_json) if row.data_json else {}
            except (json.JSONDecodeError, TypeError):
                compiled[row.file_key] = {}
        return compiled

    def _load_active_foreshadows(self, novel_id: str, truth_file: dict) -> list[dict]:
        # 优先从 truth_file.pending_hooks
        hooks = truth_file.get("pending_hooks")
        if isinstance(hooks, list):
            return [h for h in hooks if isinstance(h, dict)]
        if isinstance(hooks, dict):
            for key in ("items", "foreshadows", "list"):
                items = hooks.get(key)
                if isinstance(items, list):
                    return [h for h in items if isinstance(h, dict)]
        # fallback：聚合各章节的 foreshadows JSON
        out: list[dict] = []
        chapters = self.db.query(Chapter).filter_by(novel_id=novel_id).all()
        for ch in chapters:
            try:
                arr = json.loads(ch.foreshadows or "[]")
            except (json.JSONDecodeError, TypeError):
                continue
            for fs in arr:
                if isinstance(fs, dict) and not fs.get("resolved"):
                    out.append(fs)
        return out

    @staticmethod
    def _compute_word_range(novel: Novel) -> tuple[int, int]:
        target = int(getattr(novel, "words_per_chapter", 0) or 3000)
        low = max(1000, int(target * 0.8))
        high = max(low + 500, int(target * 1.3))
        return (low, high)

    def _load_baseline_text(self, novel_id: str, chapter_number: int) -> str:
        if chapter_number <= 1:
            return ""
        limit = min(chapter_number - 1, 10)
        rows = (
            self.db.query(Chapter)
            .filter(Chapter.novel_id == novel_id, Chapter.number < chapter_number)
            .order_by(Chapter.number.desc())
            .limit(limit)
            .all()
        )
        return "\n\n".join(r.content or "" for r in rows if r.content)

    # ── 并发审核 ─────────────────────────────────────────────

    async def _run_parallel_audits(
        self,
        draft_text: str,
        baseline_text: str,
        chapter_number: int,
        novel_id: str,
        llm: LLMClient | None,
    ) -> dict:
        quality_task = asyncio.to_thread(quality_radar.score_chapter, draft_text)
        drift_task = asyncio.to_thread(
            style_drift_detector.detect_drift, draft_text, baseline_text, chapter_number
        )
        coros = [quality_task, drift_task]
        if llm is not None:
            coros.append(consistency_checker.check_full_consistency(self.db, llm, novel_id))

        gathered = await asyncio.gather(*coros, return_exceptions=True)

        def _safe(v):
            if isinstance(v, Exception):
                logger.warning("audit task failed: %s", v)
                return None
            return v

        quality_res = _safe(gathered[0])
        drift_res = _safe(gathered[1])
        consistency_res = _safe(gathered[2]) if len(gathered) > 2 else None

        return {"quality": quality_res, "drift": drift_res, "consistency": consistency_res}

    # ── LLM prompt 构造与解析 ────────────────────────────────

    def _build_editor_prompt(
        self,
        draft_text: str,
        violations: list[HardRuleViolation],
        quality_score,
        consistency_report,
        drift_report,
        truth_file: dict,
        active_foreshadows: list[dict],
    ) -> str:
        def _violations_block() -> str:
            if not violations:
                return "(无)"
            return "\n".join(
                f"- [{v.severity}] {v.rule_id}: {v.evidence}" for v in violations
            )

        def _quality_block() -> str:
            if quality_score is None:
                return "(quality_radar 未跑通)"
            d = quality_score.to_dict()
            keep = {k: v for k, v in d.items() if k != "issues"}
            return json.dumps(keep, ensure_ascii=False)

        def _consistency_block() -> str:
            if consistency_report is None:
                return "(无一致性数据)"
            try:
                return json.dumps(consistency_report.to_dict(), ensure_ascii=False)[:1500]
            except Exception:  # noqa: BLE001
                return "(一致性序列化失败)"

        def _drift_block() -> str:
            if drift_report is None:
                return "(无漂移数据)"
            try:
                return json.dumps(drift_report.to_dict(), ensure_ascii=False)
            except Exception:  # noqa: BLE001
                return "(漂移序列化失败)"

        def _truth_block() -> str:
            cs = truth_file.get("current_state") or {}
            brief = {k: cs[k] for k in ("protagonist_name", "current_date", "dead_characters") if k in cs}
            return json.dumps(brief, ensure_ascii=False)

        def _foreshadow_block() -> str:
            head = active_foreshadows[:10]
            return json.dumps(
                [
                    {
                        "id": h.get("foreshadow_id", ""),
                        "desc": (h.get("description") or "")[:40],
                        "deadline": h.get("recovery_deadline", 0),
                    }
                    for h in head
                ],
                ensure_ascii=False,
            )

        # 限长（quality + consistency + drift 已自截，draft 在外面截）
        if len(draft_text) > 6000:
            draft_snippet = draft_text[:3000] + "\n\n[...中段省略...]\n\n" + draft_text[-3000:]
        else:
            draft_snippet = draft_text

        return (
            "# 工具输出\n"
            f"### hard_rules\n{_violations_block()}\n\n"
            f"### quality_radar\n{_quality_block()}\n\n"
            f"### consistency_checker\n{_consistency_block()}\n\n"
            f"### style_drift_detector\n{_drift_block()}\n\n"
            "# 章节草稿\n"
            f"{draft_snippet}\n\n"
            "# 全局上下文\n"
            f"- 真相文件摘要: {_truth_block()}\n"
            f"- 活跃伏笔: {_foreshadow_block()}\n\n"
            "请严格按 EDITOR_SYSTEM 中定义的 JSON 格式输出。"
        )

    def _parse_llm_json(self, content: str) -> dict:
        text = (content or "").strip()
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            text = text[first : last + 1]
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {}

    # ── 结果组装 ─────────────────────────────────────────────

    def _build_result_from_llm(
        self,
        parsed: dict,
        violations: list[HardRuleViolation],
        quality_score,
        elapsed_start: float,
        tokens_used: int,
    ) -> ReviewResult:
        decision_raw = parsed.get("decision")
        decision = decision_raw if decision_raw in _DECISIONS else "revise"

        try:
            overall = float(parsed.get("overall_score") or 0)
        except (TypeError, ValueError):
            overall = 0.0
        if overall <= 0 and quality_score is not None:
            overall = float(quality_score.overall)

        dims = parsed.get("dimensions") if isinstance(parsed.get("dimensions"), dict) else None
        if not dims and quality_score is not None:
            qd = quality_score.to_dict()
            dims = {k: float(qd[k]) for k in qd if k not in ("issues", "overall", "passed")}
        dims = dims or {}

        summary = parsed.get("summary") or ""
        if not isinstance(summary, str):
            summary = str(summary)

        annotations: list[Annotation] = []
        for a in parsed.get("annotations", []) or []:
            if not isinstance(a, dict):
                continue
            try:
                annotations.append(
                    Annotation(
                        location=a.get("location") or {},
                        category=a.get("category") if a.get("category") in _ANNOTATION_CATEGORIES else "structure",
                        severity=a.get("severity") if a.get("severity") in _SEVERITIES else "info",
                        issue=a.get("issue") or "",
                        suggestion=a.get("suggestion"),
                        evidence=a.get("evidence") if isinstance(a.get("evidence"), list) else [],
                        auto_fixable=bool(a.get("auto_fixable", False)),
                    )
                )
            except ValidationError:
                continue

        # 把 hard_rules 的非 blocker 违反也作为 annotation 暴露给上层
        for v in violations:
            if v.severity != "blocker":
                annotations.append(
                    Annotation(
                        location={},
                        category="hard_rule",
                        severity=v.severity,
                        issue=f"[{v.rule_id}] {v.evidence}",
                        suggestion=v.suggested_fix,
                        evidence=[],
                        auto_fixable=False,
                    )
                )

        next_action = self._build_next_action(
            decision,
            parsed.get("next_action") if isinstance(parsed.get("next_action"), dict) else None,
        )

        elapsed_ms = int((time.time() - elapsed_start) * 1000)
        return ReviewResult(
            decision=decision,
            overall_score=overall,
            dimensions=dims,
            summary=summary[:500],
            annotations=annotations,
            next_action=next_action,
            elapsed_ms=elapsed_ms,
            tokens_used=tokens_used,
        )

    def _build_next_action(self, decision: str, na_dict: dict | None) -> NextAction:
        mapping = {
            "pass": ("pass", None),
            "revise": ("trigger_revision", "revision_loop"),
            "rewrite": ("trigger_rewrite", "writer_agent"),
            "ask_user": ("ask_user", None),
        }
        default_action, default_target = mapping.get(decision, ("trigger_revision", "revision_loop"))

        if na_dict:
            action = na_dict.get("action")
            if action not in _ACTIONS:
                action = default_action
            target = na_dict.get("target") if "target" in na_dict else default_target
            payload = na_dict.get("payload") if isinstance(na_dict.get("payload"), dict) else {}
            return NextAction(action=action, target=target, payload=payload)
        return NextAction(action=default_action, target=default_target, payload={})

    def _rewrite_for_blockers(
        self,
        blockers: list[HardRuleViolation],
        all_violations: list[HardRuleViolation],
        elapsed_start: float,
    ) -> ReviewResult:
        annotations = [
            Annotation(
                location={},
                category="hard_rule",
                severity=v.severity,
                issue=f"[{v.rule_id}] {v.evidence}",
                suggestion=v.suggested_fix,
                evidence=[],
                auto_fixable=False,
            )
            for v in all_violations
        ]
        elapsed_ms = int((time.time() - elapsed_start) * 1000)
        return ReviewResult(
            decision="rewrite",
            overall_score=0.0,
            dimensions={},
            summary=f"触发 {len(blockers)} 条硬性约束（blocker），本章需重写。",
            annotations=annotations,
            next_action=NextAction(
                action="trigger_rewrite",
                target="writer_agent",
                payload={
                    "reason": "hard_rule_blocker",
                    "blocker_ids": [v.rule_id for v in blockers],
                },
            ),
            elapsed_ms=elapsed_ms,
            tokens_used=0,
        )

    def _fallback_result(
        self,
        violations: list[HardRuleViolation],
        quality_score,
        consistency_report,
        drift_report,
        elapsed_start: float,
        tokens_used: int,
    ) -> ReviewResult:
        overall = float(quality_score.overall) if quality_score is not None else 50.0

        dims: dict[str, float] = {}
        if quality_score is not None:
            qd = quality_score.to_dict()
            dims = {k: float(qd[k]) for k in qd if k not in ("issues", "overall", "passed")}

        annotations: list[Annotation] = []
        for v in violations:
            annotations.append(
                Annotation(
                    location={},
                    category="hard_rule",
                    severity=v.severity,
                    issue=f"[{v.rule_id}] {v.evidence}",
                    suggestion=v.suggested_fix,
                    evidence=[],
                    auto_fixable=False,
                )
            )

        if quality_score is not None and quality_score.issues:
            for iss in quality_score.issues[:5]:
                sev = "warning" if iss.get("severity") == "critical" else "info"
                annotations.append(
                    Annotation(
                        location={},
                        category="style",
                        severity=sev,
                        issue=f"[{iss.get('dimension', '?')}] {iss.get('message', '')}",
                        suggestion=None,
                        evidence=[],
                        auto_fixable=False,
                    )
                )

        if consistency_report is not None and consistency_report.issues:
            for ci in consistency_report.issues[:5]:
                sev = "warning" if ci.severity == "error" else "info"
                annotations.append(
                    Annotation(
                        location={},
                        category="consistency",
                        severity=sev,
                        issue=f"[{ci.issue_type}] {ci.description}",
                        suggestion=None,
                        evidence=[{"type": "chapter_range", "range": ci.chapter_range}],
                        auto_fixable=False,
                    )
                )

        if drift_report is not None and drift_report.drift_level in {"moderate", "severe"}:
            annotations.append(
                Annotation(
                    location={},
                    category="style",
                    severity="warning" if drift_report.drift_level == "severe" else "info",
                    issue=f"风格漂移 {drift_report.drift_level} (score={drift_report.drift_score:.1f})",
                    suggestion="对齐全书文风基线",
                    evidence=[],
                    auto_fixable=False,
                )
            )

        if overall < 50:
            decision = "rewrite"
        elif overall < 70 or annotations:
            decision = "revise"
        else:
            decision = "pass"

        next_action = self._build_next_action(decision, None)
        elapsed_ms = int((time.time() - elapsed_start) * 1000)

        return ReviewResult(
            decision=decision,
            overall_score=overall,
            dimensions=dims,
            summary=f"本地启发式审稿：overall={overall:.1f} → {decision}",
            annotations=annotations,
            next_action=next_action,
            elapsed_ms=elapsed_ms,
            tokens_used=tokens_used,
        )

    # ── 事件 ─────────────────────────────────────────────────

    async def _emit(
        self,
        event_type: str,
        novel_id: str,
        session_id: str | None,
        chapter_number: int,
        payload: dict,
    ) -> None:
        if self.event_store is None or session_id is None:
            return
        try:
            await self.event_store.append(
                book_id=novel_id,
                session_id=session_id,
                event_type=event_type,
                actor="muyu_editor",
                payload=payload,
                chapter_number=chapter_number,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("emit event 失败 (%s): %s", event_type, e)

    async def _emit_completed(
        self,
        novel_id: str,
        session_id: str | None,
        chapter_number: int,
        result: ReviewResult,
    ) -> None:
        if self.event_store is None or session_id is None:
            return
        await self._emit(
            "review_completed", novel_id, session_id, chapter_number,
            {
                "decision": result.decision,
                "overall_score": result.overall_score,
                "dimensions": result.dimensions,
                "summary": result.summary,
                "annotation_count": len(result.annotations),
            },
        )
