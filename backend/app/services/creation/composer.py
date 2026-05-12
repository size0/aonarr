"""Composer — RTCO 分层上下文编译器

采用 RTCO (Ranked Token-budget Context Orchestration) 分层框架：

优先级层：
  P0-核心（始终保留，不裁剪）：
    - FACT_LOCK: 不可违反的硬事实
    - 大纲/节拍: 本章计划摘要
    - 衔接锚点: 上章末尾文本 + 摘要
    - 字数/约束要求

  P1-重要（超预算时按比例裁剪）：
    - 角色信息: POV 角色完整档案 + 相关角色
    - 计划详情: 角色目标、伏笔操作
    - 真相文件: current_state, pending_hooks
    - 语气/POV 策略

  P2-参考（超预算时优先裁剪）：
    - 前文摘要: 滑动窗口摘要
    - 编译记忆: 分层记忆
    - 次要真相文件: 其他 truth files
    - 语义检索: 向量匹配段落

输出结构 (ComposedContext):
{
  "fact_lock": "━━━ FACT_LOCK ━━━\\n不可违反的硬事实...",
  "context_block": "精选上下文...",
  "voice_block": "风格/语气指导...",
  "planning_section": "本章计划摘要...",
  "pov_strategy": "视角策略...",
  "constraints": ["约束1", "约束2"],
  "selected_truth": {"file_key": "相关内容..."},
  "rtco_stats": {"p0_chars": 1200, "p1_chars": 3000, "p2_chars": 1500}
}
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.novel import TruthFile
from app.services.creation.context_builder import ContextBuilder, CreationContext

logger = logging.getLogger(__name__)

# ── RTCO Token 预算配置 ─────────────────────────────────────────
# 1 中文字 ≈ 1.5 token, 下面以字符数管理
RTCO_TOTAL_BUDGET = 10000  # 总字符预算
RTCO_P0_RATIO = 0.35       # P0 保底 35%
RTCO_P1_RATIO = 0.40       # P1 分配 40%
RTCO_P2_RATIO = 0.25       # P2 分配 25%

# P0 核心真相文件
_P0_TRUTH_KEYS = {"current_state", "pending_hooks"}


class Composer:
    """RTCO 分层上下文编译器"""

    def __init__(self, db: Session, *, total_budget: int = RTCO_TOTAL_BUDGET):
        self.db = db
        self._context_builder = ContextBuilder(db)
        self._total_budget = total_budget

    def compose(
        self,
        novel_id: str,
        chapter_number: int,
        plan: dict,
    ) -> dict:
        """编译最终写作上下文（RTCO 分层）

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            plan: Planner 输出的 chapter_plan

        Returns:
            ComposedContext dict，可直接注入 ChapterWriter 的 template_vars
        """
        # 基础上下文（复用 ContextBuilder）
        base_ctx = self._context_builder.build(novel_id, chapter_number)

        # 从 plan 中提取关键信息
        pov_char = plan.get("pov", "")
        location = plan.get("location", "")
        tone = plan.get("tone", "")
        intent = plan.get("chapter_intent", "")
        constraints = plan.get("constraints", [])
        char_goals = plan.get("character_goals", [])
        _foreshadow_actions = plan.get("foreshadow_actions", [])  # noqa: F841

        # ── 阶段 1: 计算预算 ──
        _p0_budget = int(self._total_budget * RTCO_P0_RATIO)  # noqa: F841
        p1_budget = int(self._total_budget * RTCO_P1_RATIO)
        p2_budget = int(self._total_budget * RTCO_P2_RATIO)

        # ── 阶段 2: P0-核心 (始终保留) ──
        fact_lock = self._compile_fact_lock(base_ctx, plan)
        planning_section = self._compile_planning(plan)

        # 衔接锚点 — 上章末尾500字
        anchor_text = ""
        if base_ctx.recent_chapter_text:
            anchor_text = base_ctx.recent_chapter_text[-500:]

        p0_total = len(fact_lock) + len(planning_section) + len(anchor_text)

        # ── 阶段 3: P1-重要 (超预算按比例裁剪) ──
        # 精选核心真相文件
        p1_truth = self._select_truth_by_priority(
            novel_id, pov_char, location, plan, priority="p1"
        )
        # 角色信息（POV 优先）
        p1_characters = self._compile_characters(base_ctx, pov_char)
        # 角色目标
        p1_goals = self._compile_char_goals(char_goals)
        # 语气 + POV
        voice_block = self._compile_voice(tone, pov_char, base_ctx)
        pov_strategy = self._compile_pov(pov_char, base_ctx)

        p1_parts = {
            "truth": "\n".join(f"[{k}] {v}" for k, v in p1_truth.items()),
            "characters": p1_characters,
            "goals": p1_goals,
            "voice": voice_block,
            "pov": pov_strategy,
        }
        p1_total = sum(len(v) for v in p1_parts.values())

        # P1 裁剪
        if p1_total > p1_budget:
            p1_parts = self._trim_layer(p1_parts, p1_budget)
            p1_total = sum(len(v) for v in p1_parts.values())

        # ── 阶段 4: P2-参考 (超预算优先裁剪) ──
        p2_truth = self._select_truth_by_priority(
            novel_id, pov_char, location, plan, priority="p2"
        )
        p2_summaries = self._compile_summaries(base_ctx)
        p2_memory = base_ctx.compiled_memory or ""
        p2_hooks = ""
        pending = p1_truth.get("pending_hooks", "")
        if not pending:
            # 如果 P1 没有 pending_hooks，从 P2 truth 里找
            for k, v in p2_truth.items():
                if "伏笔" in k or "hook" in k:
                    p2_hooks = v
                    break

        p2_parts = {
            "summaries": p2_summaries,
            "memory": self._truncate(p2_memory, 1200),
            "secondary_truth": "\n".join(f"[{k}] {v}" for k, v in p2_truth.items()),
            "hooks_extra": p2_hooks,
        }
        p2_total = sum(len(v) for v in p2_parts.values())

        if p2_total > p2_budget:
            p2_parts = self._trim_layer(p2_parts, p2_budget)
            p2_total = sum(len(v) for v in p2_parts.values())

        # ── 阶段 5: 组装输出 ──
        # context_block = P1 truth + P1 goals + P2 summaries + P2 memory
        context_parts = []
        if base_ctx.synopsis:
            context_parts.append(f"【故事简介】{base_ctx.synopsis[:200]}")
        if p1_parts.get("characters"):
            context_parts.append(f"【角色档案】\n{p1_parts['characters']}")
        if p1_parts.get("goals"):
            context_parts.append(f"【本章角色目标】\n{p1_parts['goals']}")
        if p1_parts.get("truth"):
            context_parts.append(f"【核心事实】\n{p1_parts['truth']}")
        if p2_parts.get("summaries"):
            context_parts.append(f"【前文摘要】\n{p2_parts['summaries']}")
        if p2_parts.get("memory"):
            context_parts.append(f"【编译记忆】\n{p2_parts['memory']}")
        if p2_parts.get("secondary_truth"):
            context_parts.append(f"【参考事实】\n{p2_parts['secondary_truth']}")

        context_block = "\n\n".join(context_parts)

        # 聚合所有 selected_truth
        all_truth = {**p1_truth, **p2_truth}

        composed = {
            # 注入 ChapterWriter template_vars 的字段
            "fact_lock": fact_lock,
            "context": context_block,
            "voice_block": p1_parts.get("voice", voice_block),
            "planning_section": planning_section,
            "pov_strategy": p1_parts.get("pov", pov_strategy),
            "pov_character": pov_char,
            "location": location,
            "tone": tone,
            "anchor_text": anchor_text,
            # 额外数据
            "constraints": constraints,
            "selected_truth": all_truth,
            "chapter_intent": intent,
            "beats": plan.get("beats_suggestion", []),
            # RTCO 统计
            "rtco_stats": {
                "p0_chars": p0_total,
                "p1_chars": p1_total,
                "p2_chars": p2_total,
                "total_chars": p0_total + p1_total + p2_total,
                "budget": self._total_budget,
            },
        }

        logger.info(
            "[Composer/RTCO] novel=%s ch=%d → P0=%d P1=%d P2=%d total=%d/%d",
            novel_id, chapter_number,
            p0_total, p1_total, p2_total,
            p0_total + p1_total + p2_total, self._total_budget,
        )
        return composed

    # ── P0 编译方法 ────────────────────────────────────────────

    def _compile_fact_lock(self, ctx: CreationContext, plan: dict) -> str:
        """P0: 编译 FACT_LOCK — 不可违反的硬事实"""
        lines = ["━━━ FACT_LOCK ━━━"]
        lines.append(f"书名=《{ctx.title}》")
        if ctx.genre:
            lines.append(f"题材={ctx.genre}")
        lines.append(f"当前章节=第{ctx.current_chapter_number}章")
        lines.append(f"已写={ctx.total_word_count}字/{ctx.chapter_count}章")

        pov = plan.get("pov", "")
        if pov:
            lines.append(f"视角角色={pov}")

        loc = plan.get("location", "")
        if loc:
            lines.append(f"场景={loc}")

        for c in plan.get("constraints", [])[:5]:
            lines.append(f"约束：{c}")

        return "\n".join(lines)

    def _compile_planning(self, plan: dict) -> str:
        """P0: 编译本章计划摘要"""
        lines = ["── 本章计划 ──"]
        lines.append(f"意图：{plan.get('chapter_intent', '自由推进')}")

        beats = plan.get("beats_suggestion", [])
        if beats:
            lines.append("节拍：")
            for i, b in enumerate(beats[:7], 1):
                lines.append(f"  {i}. [{b.get('type', '?')}] {b.get('summary', '')}")

        fsa = plan.get("foreshadow_actions", [])
        if fsa:
            lines.append("伏笔操作：")
            for fa in fsa[:5]:
                lines.append(f"  · [{fa.get('action', '?')}] {fa.get('hook', '')}")

        return "\n".join(lines)

    # ── P1 编译方法 ────────────────────────────────────────────

    def _compile_characters(self, ctx: CreationContext, pov_char: str) -> str:
        """P1: 编译角色信息，POV 角色优先且详细"""
        if not ctx.characters:
            return ""

        lines = []
        # POV 角色放首位且详细
        pov_found = False  # noqa: F841
        for c in ctx.characters:
            if c.get("name") == pov_char:
                traits = "、".join(c.get("traits", []))
                lines.append(f"★ {c['name']}（{c.get('role', '配角')}）：{c.get('description', '')}")
                if traits:
                    lines.append(f"  性格：{traits}")
                _pov_found = True  # noqa: F841
                break

        # 其他角色简略
        for c in ctx.characters:
            if c.get("name") == pov_char:
                continue
            traits = "、".join(c.get("traits", [])[:3])
            desc = self._truncate(c.get("description", ""), 80)
            lines.append(f"- {c['name']}（{c.get('role', '配角')}）：{desc}  {traits}")

        return "\n".join(lines[:10])  # 最多10个角色

    def _compile_char_goals(self, char_goals: list[dict]) -> str:
        """P1: 编译角色目标"""
        if not char_goals:
            return ""
        return "\n".join(f"  · {cg.get('name', '?')}: {cg.get('goal', '')}" for cg in char_goals[:5])

    def _compile_voice(self, tone: str, pov_char: str, ctx: CreationContext) -> str:
        """P1: 编译语气/风格指导"""
        parts = []
        if tone:
            parts.append(f"情感基调: {tone}")
        if pov_char:
            for c in ctx.characters:
                if c.get("name") == pov_char:
                    traits = "、".join(c.get("traits", []))
                    parts.append(f"视角角色性格: {traits}")
                    break
        if ctx.genre:
            parts.append(f"题材风格: {ctx.genre}")
        return "\n".join(parts) if parts else ""

    def _compile_pov(self, pov_char: str, ctx: CreationContext) -> str:
        """P1: 编译 POV 策略"""
        if not pov_char:
            return "第三人称全知视角"

        for c in ctx.characters:
            if c.get("name") == pov_char:
                role = c.get("role", "supporting")
                return f"第三人称限制视角·{pov_char}（{role}）— 只描写该角色能感知到的信息"

        return f"第三人称限制视角·{pov_char}"

    # ── P2 编译方法 ────────────────────────────────────────────

    def _compile_summaries(self, ctx: CreationContext) -> str:
        """P2: 编译前文摘要"""
        if not ctx.previous_summaries:
            return ""
        lines = [
            f"  第{s.get('number')}章：{s.get('summary', '')}"
            for s in ctx.previous_summaries[-5:]
        ]
        return "\n".join(lines)

    # ── 真相文件选择 ───────────────────────────────────────────

    def _select_truth_by_priority(
        self,
        novel_id: str,
        pov_char: str,
        location: str,
        plan: dict,
        *,
        priority: str = "p1",
    ) -> dict[str, str]:
        """按 RTCO 优先级选择真相文件

        P1: current_state + pending_hooks + 关键词相关文件
        P2: 其余文件
        """
        all_truth = self.db.query(TruthFile).filter_by(novel_id=novel_id).all()

        # 关键词集合
        keywords = set()
        if pov_char:
            keywords.add(pov_char)
        if location:
            keywords.add(location)
        for cg in plan.get("character_goals", []):
            keywords.add(cg.get("name", ""))
        for fa in plan.get("foreshadow_actions", []):
            keywords.add(fa.get("hook", ""))
        keywords.discard("")

        p1_selected: dict[str, str] = {}
        p2_selected: dict[str, str] = {}

        for tf in all_truth:
            content = tf.content or ""
            if not content:
                continue

            if tf.file_key in _P0_TRUTH_KEYS:
                # current_state / pending_hooks → P1 (核心参考)
                p1_selected[tf.file_key] = self._truncate(content, 1500)
            else:
                # 其他文件按关键词相关性决定
                if keywords:
                    relevance = sum(1 for kw in keywords if kw and kw in content)
                    if relevance > 0:
                        p1_selected[tf.file_key] = self._truncate(content, 800)
                    else:
                        p2_selected[tf.file_key] = self._truncate(content, 500)
                else:
                    p2_selected[tf.file_key] = self._truncate(content, 500)

        return p1_selected if priority == "p1" else p2_selected

    # ── 裁剪工具 ─────────────────────────────────────────────

    def _trim_layer(self, parts: dict[str, str], budget: int) -> dict[str, str]:
        """按比例裁剪某层的各部分，使总量不超过预算"""
        total = sum(len(v) for v in parts.values())
        if total <= budget:
            return parts

        ratio = budget / total if total > 0 else 1.0
        trimmed = {}
        for k, v in parts.items():
            max_len = max(50, int(len(v) * ratio))
            trimmed[k] = self._truncate(v, max_len)
        return trimmed

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "\n…（已截断）"
