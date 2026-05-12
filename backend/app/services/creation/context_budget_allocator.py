"""上下文配额分配器 — 洋葱模型优先级挤压 + 全局收敛沙漏

移植自 PlotPilot，适配 NovelForgeX 的 SQLAlchemy 模型体系。

核心设计：
- T0 级（绝对不删减）：系统 Prompt、当前幕摘要、强制伏笔、角色锚点、生命周期行为准则
- T1 级（按比例压缩）：知识图谱子网、近期幕摘要
- T2 级（动态水位线）：最近章节内容
- T3 级（可牺牲泡沫）：向量召回片段、写作方法论

全局倒计时与收敛沙漏：
- 根据当前章节 / 目标总章节数 计算 progress (0.0 ~ 1.0)
- 根据 progress 自动切换行为模式：开局(0-25%) / 发展(25-75%) / 收敛(75-90%) / 终局(90-100%)
- 行为准则作为最高优先级 T0 槽位注入，引导 AI 自然收束笔墨

当 Token 预算紧张时，从 T3 → T2 → T1 逐层挤压，T0 绝对保护。
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session

from app.models.novel import (
    Novel, Chapter, Character, WorldItem, OutlineNode,
    TruthFile,
)

logger = logging.getLogger(__name__)


class PriorityTier(str, Enum):
    """优先级层级（洋葱模型）"""
    T0_CRITICAL = "t0_critical"
    T1_COMPRESSIBLE = "t1_compressible"
    T2_DYNAMIC = "t2_dynamic"
    T3_SACRIFICIAL = "t3_sacrificial"


class StoryPhase(str, Enum):
    """故事生命周期阶段 — 全局收敛沙漏的核心状态机"""
    OPENING = "opening"
    DEVELOPMENT = "development"
    CONVERGENCE = "convergence"
    FINALE = "finale"


# 各阶段硬编码行为准则（后续可迁移到 DB prompts 表）
PHASE_DIRECTIVES: Dict[StoryPhase, str] = {
    StoryPhase.OPENING: (
        "【开局期】当前处于故事开头阶段。\n"
        "✅ 允许：铺陈世界观、介绍人物、制造悬念、抛出伏笔\n"
        "✅ 鼓励：强烈的开场钩子、人物第一印象塑造\n"
        "❌ 禁止：提前揭露终极真相、过早解决核心矛盾"
    ),
    StoryPhase.DEVELOPMENT: (
        "【发展期】当前处于故事中段，矛盾正在激化。\n"
        "✅ 允许：激化矛盾、引入支线、人物成长、伏笔推进\n"
        "✅ 鼓励：反转、困境升级、人物内心冲突\n"
        "⚠️ 注意：已播下的伏笔需要适时推进，不要遗忘"
    ),
    StoryPhase.CONVERGENCE: (
        "【收敛期】故事进入收束阶段，必须开始闭合伏笔。\n"
        "✅ 允许：闭合伏笔、收束支线、人物关系定型\n"
        "❌ 严禁：开新坑、引入新势力、新增未解悬念\n"
        "⚠️ 强制：每章必须推进至少一条悬念的解决"
    ),
    StoryPhase.FINALE: (
        "【终局期】这是最后的冲刺，故事即将结束。\n"
        "✅ 允许：终极对决、最终反转、人物命运终结\n"
        "❌ 严禁：任何新伏笔、日常填充、拖沓描写\n"
        "⚠️ 所有未闭合伏笔必须在此阶段内完成"
    ),
}


@dataclass
class ContextSlot:
    """上下文槽位"""
    name: str
    tier: PriorityTier
    content: str = ""
    tokens: int = 0
    max_tokens: Optional[int] = None
    min_tokens: int = 0
    priority: int = 0

    @property
    def is_mandatory(self) -> bool:
        return self.tier == PriorityTier.T0_CRITICAL


@dataclass
class BudgetAllocation:
    """预算分配结果"""
    slots: Dict[str, ContextSlot] = field(default_factory=dict)
    total_budget: int = 35000
    used_tokens: int = 0
    remaining_tokens: int = 0

    t0_reserved: int = 0
    t1_allocated: int = 0
    t2_allocated: int = 0
    t3_allocated: int = 0

    compression_applied: bool = False
    compression_log: List[str] = field(default_factory=list)
    expired_foreshadows: List[str] = field(default_factory=list)

    progress: float = 0.0
    phase: StoryPhase = StoryPhase.OPENING
    total_chapters: int = 0

    def get_final_context(self) -> str:
        """组装最终上下文"""
        parts = []

        for tier in [PriorityTier.T0_CRITICAL, PriorityTier.T1_COMPRESSIBLE,
                     PriorityTier.T2_DYNAMIC, PriorityTier.T3_SACRIFICIAL]:
            tier_slots = [(name, slot) for name, slot in self.slots.items() if slot.tier == tier]
            tier_slots.sort(key=lambda x: x[1].priority, reverse=True)

            for name, slot in tier_slots:
                if slot.content.strip():
                    parts.append(f"\n=== {slot.name.upper()} ===\n{slot.content}")

        if self.expired_foreshadows:
            parts.append(
                "\n=== 强制剧情收束令 ===\n"
                "以下伏笔已超出预期揭晓章节，必须在本章行文中通过回忆、对话、意外发展或直接揭露等方式解答或推进：\n"
                + "\n".join(f"- {f}" for f in self.expired_foreshadows)
                + "\n【如果你无视此指令，长篇小说的情节网将陷入崩溃】"
            )

        return "\n".join(parts)

    def to_summary(self) -> dict:
        """返回分配摘要（供日志/API）"""
        return {
            "total_budget": self.total_budget,
            "used_tokens": self.used_tokens,
            "remaining_tokens": self.remaining_tokens,
            "t0": self.t0_reserved,
            "t1": self.t1_allocated,
            "t2": self.t2_allocated,
            "t3": self.t3_allocated,
            "progress": self.progress,
            "phase": self.phase.value,
            "compression": self.compression_applied,
            "expired_foreshadows": len(self.expired_foreshadows),
        }


class ContextBudgetAllocator:
    """上下文配额分配器 — 适配 NovelForgeX SQLAlchemy 模型"""

    CHARS_PER_TOKEN_ZH = 1.5
    CHARS_PER_TOKEN_EN = 4.0

    T0_BUDGET_RATIO = 0.25
    T1_BUDGET_RATIO = 0.25
    T2_BUDGET_RATIO = 0.30
    T3_BUDGET_RATIO = 0.20

    MAX_FORESHADOWING_TOKENS = 2000
    MAX_CHARACTER_ANCHORS_TOKENS = 1500
    MAX_WORLD_ITEMS_TOKENS = 1000
    MAX_SUMMARIES_TOKENS = 1500
    MAX_RECENT_CHAPTERS_TOKENS = 5000
    MAX_VECTOR_RECALL_TOKENS = 5000

    PREV_CHAPTER_BRIDGE_HEAD_CHARS = 300
    PREV_CHAPTER_BRIDGE_TAIL_CHARS = 2000
    OLDER_CHAPTER_HEAD_PREVIEW_CHARS = 500

    def __init__(self, db: Session):
        self.db = db

    def estimate_tokens(self, text: str) -> int:
        """估算文本的 Token 数量（中英混合）"""
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        total_chars = len(text)
        if total_chars == 0:
            return 0
        chinese_ratio = chinese_chars / total_chars
        zh_tokens = chinese_chars / self.CHARS_PER_TOKEN_ZH
        en_tokens = (total_chars - chinese_chars) / self.CHARS_PER_TOKEN_EN
        return int(zh_tokens * chinese_ratio + en_tokens * (1 - chinese_ratio) + 0.5)

    def allocate(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str = "",
        total_budget: int = 35000,
    ) -> BudgetAllocation:
        """执行预算分配"""
        allocation = BudgetAllocation(total_budget=total_budget)

        # ========== V7 全局收敛沙漏 ==========
        total_chapters = self._estimate_total_chapters(novel_id)
        progress = chapter_number / max(total_chapters, 1)
        phase = self._classify_phase(progress)
        allocation.progress = round(progress, 4)
        allocation.phase = phase
        allocation.total_chapters = total_chapters

        logger.info(
            "[沙漏] 进度: %d/%d = %.0f%% | 阶段: %s",
            chapter_number, total_chapters, progress * 100, phase.value,
        )

        # ========== 第一步：收集所有内容 ==========
        slots = self._collect_all_slots(novel_id, chapter_number, outline)

        # 提取过期伏笔
        pending_fs_slot = slots.get("pending_foreshadowings")
        if pending_fs_slot and pending_fs_slot.content:
            for line in pending_fs_slot.content.split('\n'):
                if "[已过期]" in line:
                    desc = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
                    allocation.expired_foreshadows.append(desc)

        # ========== 第二步：T0 强制保留 ==========
        t0_slots = {n: s for n, s in slots.items() if s.tier == PriorityTier.T0_CRITICAL}
        t0_total = sum(s.tokens for s in t0_slots.values())

        if t0_total > total_budget:
            logger.warning("T0 强制内容 %d tokens 超出总预算 %d", t0_total, total_budget)
            allocation.compression_log.append("T0 超预算，强制截断")
            t0_total = self._truncate_t0_slots(t0_slots, total_budget)

        allocation.t0_reserved = t0_total

        # ========== 第三步：T1/T2/T3 分配 ==========
        remaining = total_budget - t0_total

        t1_budget = int(remaining * self.T1_BUDGET_RATIO / (self.T1_BUDGET_RATIO + self.T2_BUDGET_RATIO + self.T3_BUDGET_RATIO))
        t1_slots = {n: s for n, s in slots.items() if s.tier == PriorityTier.T1_COMPRESSIBLE}
        t1_actual = self._allocate_tier(t1_slots, t1_budget, allocation.compression_log)
        allocation.t1_allocated = t1_actual

        remaining_after_t1 = remaining - t1_actual
        t2_budget = int(remaining_after_t1 * self.T2_BUDGET_RATIO / (self.T2_BUDGET_RATIO + self.T3_BUDGET_RATIO))
        t2_slots = {n: s for n, s in slots.items() if s.tier == PriorityTier.T2_DYNAMIC}
        t2_actual = self._allocate_tier(t2_slots, t2_budget, allocation.compression_log)
        allocation.t2_allocated = t2_actual

        remaining_after_t2 = remaining_after_t1 - t2_actual
        t3_slots = {n: s for n, s in slots.items() if s.tier == PriorityTier.T3_SACRIFICIAL}
        t3_actual = self._allocate_tier(t3_slots, remaining_after_t2, allocation.compression_log)
        allocation.t3_allocated = t3_actual

        # ========== 第四步：组装结果 ==========
        allocation.slots = slots
        allocation.used_tokens = t0_total + t1_actual + t2_actual + t3_actual
        allocation.remaining_tokens = total_budget - allocation.used_tokens

        if allocation.compression_log:
            allocation.compression_applied = True

        logger.info(
            "[BudgetAllocator] T0=%d, T1=%d, T2=%d, T3=%d, 使用=%d/%d",
            allocation.t0_reserved, allocation.t1_allocated,
            allocation.t2_allocated, allocation.t3_allocated,
            allocation.used_tokens, total_budget,
        )

        return allocation

    # ==================== 内容收集 ====================

    def _collect_all_slots(
        self, novel_id: str, chapter_number: int, outline: str,
    ) -> Dict[str, ContextSlot]:
        slots = {}

        # ── T0: 强制内容 ──

        # T0-Ω: 生命周期行为准则（最高优先级）
        lifecycle = self._build_lifecycle_directive(novel_id, chapter_number)
        slots["lifecycle_directive"] = ContextSlot(
            name="生命周期行为准则",
            tier=PriorityTier.T0_CRITICAL,
            content=lifecycle,
            tokens=self.estimate_tokens(lifecycle),
            max_tokens=600,
            priority=130,
        )

        # T0-α: 真相文件事实锁（current_state + character_matrix）
        fact_lock = self._build_fact_lock(novel_id, chapter_number)
        slots["fact_lock"] = ContextSlot(
            name="绝对事实边界(FACT_LOCK)",
            tier=PriorityTier.T0_CRITICAL,
            content=fact_lock,
            tokens=self.estimate_tokens(fact_lock),
            max_tokens=2500,
            priority=120,
        )

        # T0-β: 当前幕/卷摘要
        act_summary = self._get_current_act_summary(novel_id, chapter_number)
        slots["current_act_summary"] = ContextSlot(
            name="当前幕摘要",
            tier=PriorityTier.T0_CRITICAL,
            content=act_summary,
            tokens=self.estimate_tokens(act_summary),
            priority=100,
        )

        # T0-γ: 待回收伏笔
        foreshadowing = self._get_pending_foreshadowings(novel_id, chapter_number)
        slots["pending_foreshadowings"] = ContextSlot(
            name="待回收伏笔",
            tier=PriorityTier.T0_CRITICAL,
            content=foreshadowing,
            tokens=self.estimate_tokens(foreshadowing),
            max_tokens=self.MAX_FORESHADOWING_TOKENS,
            priority=90,
        )

        # T0-δ: 角色锚点
        char_anchors = self._get_character_anchors(novel_id, chapter_number, outline)
        slots["character_anchors"] = ContextSlot(
            name="角色状态锚点",
            tier=PriorityTier.T0_CRITICAL,
            content=char_anchors,
            tokens=self.estimate_tokens(char_anchors),
            max_tokens=self.MAX_CHARACTER_ANCHORS_TOKENS,
            priority=80,
        )

        # ── T1: 可压缩 ──

        # 世界设定（location/faction/rule 等）
        world_content = self._get_world_items(novel_id, chapter_number, outline)
        slots["world_items"] = ContextSlot(
            name="世界设定",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=world_content,
            tokens=self.estimate_tokens(world_content),
            max_tokens=self.MAX_WORLD_ITEMS_TOKENS,
            priority=70,
        )

        # 近期章节摘要
        summaries = self._get_recent_summaries(novel_id, chapter_number, limit=5)
        slots["recent_summaries"] = ContextSlot(
            name="近期章节摘要",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=summaries,
            tokens=self.estimate_tokens(summaries),
            max_tokens=self.MAX_SUMMARIES_TOKENS,
            priority=60,
        )

        # ── T2: 动态 ──

        # 最近章节正文（上一章尾 + 更早章首）
        recent_text = self._get_recent_chapters_text(novel_id, chapter_number, limit=3)
        slots["recent_chapters"] = ContextSlot(
            name="最近章节",
            tier=PriorityTier.T2_DYNAMIC,
            content=recent_text,
            tokens=self.estimate_tokens(recent_text),
            max_tokens=self.MAX_RECENT_CHAPTERS_TOKENS,
            priority=50,
        )

        # ── T3: 可牺牲 ──

        # 向量召回
        vector_content = self._get_vector_recall(novel_id, chapter_number, outline)
        slots["vector_recall"] = ContextSlot(
            name="向量召回",
            tier=PriorityTier.T3_SACRIFICIAL,
            content=vector_content,
            tokens=self.estimate_tokens(vector_content),
            max_tokens=self.MAX_VECTOR_RECALL_TOKENS,
            priority=40,
        )

        # 编译记忆
        memory = self._get_compiled_memory(novel_id, chapter_number)
        slots["compiled_memory"] = ContextSlot(
            name="编译记忆",
            tier=PriorityTier.T3_SACRIFICIAL,
            content=memory,
            tokens=self.estimate_tokens(memory),
            max_tokens=3000,
            priority=35,
        )

        return slots

    # ==================== T0 内容收集 ====================

    def _build_lifecycle_directive(self, novel_id: str, chapter_number: int) -> str:
        """构建生命周期行为准则"""
        total = self._estimate_total_chapters(novel_id)
        progress = chapter_number / max(total, 1)
        phase = self._classify_phase(progress)

        directive = PHASE_DIRECTIVES.get(phase, "")
        directive += f"\n\n📊 全局进度：第 {chapter_number} 章 / 约 {total} 章 ({progress:.0%})\n"
        directive += f"🎯 当前阶段：{phase.value}\n"

        if phase == StoryPhase.CONVERGENCE:
            remaining = total - chapter_number
            directive += f"⚠️ 剩余约 {remaining} 章完成收束，时间紧迫。\n"
        elif phase == StoryPhase.FINALE:
            remaining = total - chapter_number
            directive += f"🔥 剩余约 {remaining} 章，这是最后的冲刺。\n"

        return directive

    def _build_fact_lock(self, novel_id: str, chapter_number: int) -> str:
        """从真相文件构建不可篡改事实块"""
        truth_files = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id)
            .filter(TruthFile.file_key.in_(["current_state", "character_matrix"]))
            .all()
        )
        if not truth_files:
            return ""

        parts = ["【不可篡改事实（基于已写章节确定的事实）】"]
        for tf in truth_files:
            if tf.content and tf.content.strip():
                parts.append(f"\n[{tf.file_key}]\n{tf.content[:1200]}")
        return "\n".join(parts)

    def _get_current_act_summary(self, novel_id: str, chapter_number: int) -> str:
        """获取当前幕/卷摘要"""
        nodes = (
            self.db.query(OutlineNode)
            .filter_by(novel_id=novel_id, level="volume")
            .all()
        )
        if not nodes:
            nodes = self.db.query(OutlineNode).filter_by(novel_id=novel_id, level="act").all()
        if not nodes:
            return ""

        # 按 sort_order 找包含当前章节的卷/幕
        for node in sorted(nodes, key=lambda n: n.sort_order):
            try:
                meta = json.loads(node.metadata_json) if node.metadata_json else {}
                ch_start = meta.get("chapter_start", 0)
                ch_end = meta.get("chapter_end", 9999)
                if ch_start <= chapter_number <= ch_end:
                    return f"【{node.title}】\n{node.summary or ''}"
            except (json.JSONDecodeError, TypeError):
                pass

        return ""

    def _get_pending_foreshadowings(self, novel_id: str, chapter_number: int) -> str:
        """获取待回收伏笔（从 TruthFile.pending_hooks 或 Chapter.foreshadows）"""
        # 先尝试真相文件
        tf = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id, file_key="pending_hooks")
            .first()
        )
        if tf and tf.data_json:
            try:
                hooks = json.loads(tf.data_json)
                if isinstance(hooks, list) and hooks:
                    lines = ["【待回收伏笔】"]
                    for h in hooks[:15]:
                        if isinstance(h, dict):
                            planted = h.get("planted_chapter", "?")
                            resolve = h.get("resolve_by", None)
                            desc = h.get("description", "")
                            status = ""
                            if resolve and resolve <= chapter_number:
                                status = "[已过期] "
                            elif resolve and resolve <= chapter_number + 3:
                                status = "[即将到期] "
                            lines.append(f"- Ch{planted} {status}{desc}")
                    return "\n".join(lines)
            except (json.JSONDecodeError, TypeError):
                pass

        # 回退：从各章节的 foreshadows 字段聚合
        chapters = (
            self.db.query(Chapter)
            .filter(Chapter.novel_id == novel_id, Chapter.number < chapter_number)
            .order_by(Chapter.number)
            .all()
        )
        active = []
        for ch in chapters:
            try:
                fsh = json.loads(ch.foreshadows) if ch.foreshadows else []
                for f in fsh:
                    if isinstance(f, dict) and f.get("status") in ("planted", "tracked"):
                        f["_chapter"] = ch.number
                        active.append(f)
            except (json.JSONDecodeError, TypeError):
                pass

        if not active:
            return ""

        lines = ["【待回收伏笔】"]
        for f in active[-15:]:
            lines.append(f"- Ch{f.get('_chapter', '?')}: {f.get('description', '')}")
        return "\n".join(lines)

    def _get_character_anchors(self, novel_id: str, chapter_number: int, outline: str) -> str:
        """获取角色锚点 — 智能调度版"""
        characters = self.db.query(Character).filter_by(novel_id=novel_id).all()
        if not characters:
            return ""

        MAX_CHARS = 7

        # 从大纲提取提及的角色名
        mentioned = set()
        for c in characters:
            if c.name in (outline or ""):
                mentioned.add(c.name)

        # 从最近5章 events 统计角色活跃度
        recent_chs = (
            self.db.query(Chapter)
            .filter(Chapter.novel_id == novel_id, Chapter.number >= max(1, chapter_number - 5), Chapter.number < chapter_number)
            .all()
        )
        activity: Dict[str, int] = {}
        for ch in recent_chs:
            try:
                events = json.loads(ch.events) if ch.events else []
                for ev in events:
                    if isinstance(ev, dict):
                        for name in ev.get("involved_characters", []):
                            if isinstance(name, str):
                                activity[name] = activity.get(name, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass

        # 分类 + 排序
        def sort_key(c: Character) -> tuple:
            role_priority = {"protagonist": 0, "antagonist": 1, "supporting": 2}.get(c.role, 3)
            is_mentioned = 0 if c.name in mentioned else 1
            act_score = -activity.get(c.name, 0)
            return (is_mentioned, role_priority, act_score)

        sorted_chars = sorted(characters, key=sort_key)[:MAX_CHARS]

        lines = ["【角色状态锚点】"]
        for c in sorted_chars:
            parts = []
            if c.description:
                parts.append(c.description[:100])
            try:
                rels = json.loads(c.relationships) if c.relationships else []
                if rels:
                    rel_strs = [f"{r.get('target', '?')}({r.get('type', '?')})" for r in rels[:3]]
                    parts.append(f"关系: {'、'.join(rel_strs)}")
            except (json.JSONDecodeError, TypeError):
                pass
            if c.name in mentioned:
                parts.append("★本章出场")
            act = activity.get(c.name, 0)
            if act > 0:
                parts.append(f"近5章活跃{act}次")

            lines.append(f"\n- {c.name}（{c.role}）: " + " | ".join(parts))

        return "\n".join(lines)

    # ==================== T1 内容收集 ====================

    def _get_world_items(self, novel_id: str, chapter_number: int, outline: str) -> str:
        """获取与当前章节相关的世界设定"""
        items = self.db.query(WorldItem).filter_by(novel_id=novel_id).all()
        if not items:
            return ""

        # 优先返回大纲中提及的
        mentioned = [w for w in items if w.name in (outline or "")]
        others = [w for w in items if w not in mentioned]

        selected = mentioned + others[:10]
        lines = ["【世界设定】"]
        for w in selected:
            lines.append(f"- [{w.category}] {w.name}: {(w.description or '')[:120]}")
        return "\n".join(lines)

    def _get_recent_summaries(self, novel_id: str, chapter_number: int, limit: int = 5) -> str:
        """获取近期章节摘要"""
        chapters = (
            self.db.query(Chapter)
            .filter(Chapter.novel_id == novel_id, Chapter.number < chapter_number)
            .order_by(Chapter.number.desc())
            .limit(limit)
            .all()
        )
        if not chapters:
            return ""

        lines = ["【近期章节摘要】"]
        for ch in reversed(chapters):
            summary = (ch.summary or "")[:200]
            lines.append(f"第{ch.number}章 {ch.title or ''}: {summary}")
        return "\n".join(lines)

    # ==================== T2 内容收集 ====================

    def _get_recent_chapters_text(self, novel_id: str, chapter_number: int, limit: int = 3) -> str:
        """获取最近章节正文（上一章尾 + 更早章首）"""
        chapters = (
            self.db.query(Chapter)
            .filter(Chapter.novel_id == novel_id, Chapter.number < chapter_number)
            .order_by(Chapter.number.desc())
            .limit(limit)
            .all()
        )
        if not chapters:
            return ""

        prev_num = chapter_number - 1
        lines = ["【最近章节】"]
        for ch in reversed(chapters):
            body = (ch.content or "").strip()
            if not body:
                continue
            lines.append(f"\n第{ch.number}章：{ch.title or ''}")
            if ch.number == prev_num:
                # 紧邻上一章：头短+尾长，供本章开头承接
                head_n = self.PREV_CHAPTER_BRIDGE_HEAD_CHARS
                tail_n = self.PREV_CHAPTER_BRIDGE_TAIL_CHARS
                if len(body) <= tail_n:
                    lines.append(f"【章末节选，供本章开头承接】\n{body}")
                else:
                    lines.append(f"【章首略览】\n{body[:head_n]}……")
                    lines.append(f"【章末节选，供本章开头承接】\n{body[-tail_n:]}")
            else:
                # 更早章节只取章首
                preview = body[:self.OLDER_CHAPTER_HEAD_PREVIEW_CHARS]
                if len(body) > self.OLDER_CHAPTER_HEAD_PREVIEW_CHARS:
                    preview += "..."
                lines.append(f"【章首预览】\n{preview}")

        return "\n".join(lines)

    # ==================== T3 内容收集 ====================

    def _get_vector_recall(self, novel_id: str, chapter_number: int, outline: str) -> str:
        """向量语义召回"""
        if not outline:
            return ""
        try:
            from app.services.creation.vector_store import NovelVectorStore
            vs = NovelVectorStore()
            results = vs.query(novel_id, outline, n_results=5)
            if not results:
                return ""
            lines = ["【相关上下文（向量召回）】"]
            for r in results[:3]:
                ch_num = r.get("chapter_number", "?")
                text = r.get("text", "")[:400]
                lines.append(f"\n[第{ch_num}章] {text}")
            return "\n".join(lines)
        except Exception as e:
            logger.debug("向量召回失败: %s", e)
            return ""

    def _get_compiled_memory(self, novel_id: str, chapter_number: int) -> str:
        """获取编译记忆"""
        try:
            from app.services.creation.memory_compiler import MemoryCompiler
            compiler = MemoryCompiler(self.db)
            mem = compiler.compile(novel_id, chapter_number)
            return mem.to_prompt_text() if mem else ""
        except Exception as e:
            logger.debug("编译记忆失败: %s", e)
            return ""

    # ==================== 预算分配辅助 ====================

    def _truncate_t0_slots(self, t0_slots: Dict[str, ContextSlot], budget: int) -> int:
        total = 0
        for name, slot in t0_slots.items():
            if total + slot.tokens <= budget:
                total += slot.tokens
            else:
                remaining = budget - total
                if remaining > 0:
                    target_chars = int(remaining * self.CHARS_PER_TOKEN_ZH)
                    slot.content = slot.content[:target_chars] + "..."
                    slot.tokens = remaining
                    total += remaining
                break
        return total

    def _allocate_tier(
        self,
        tier_slots: Dict[str, ContextSlot],
        budget: int,
        compression_log: List[str],
    ) -> int:
        sorted_slots = sorted(tier_slots.items(), key=lambda x: x[1].priority, reverse=True)

        total_used = 0
        for name, slot in sorted_slots:
            if total_used + slot.tokens <= budget:
                total_used += slot.tokens
            elif slot.max_tokens and slot.max_tokens > 0:
                remaining = budget - total_used
                if remaining > slot.min_tokens:
                    target_chars = int(remaining * self.CHARS_PER_TOKEN_ZH)
                    slot.content = slot.content[:target_chars] + "..."
                    slot.tokens = remaining
                    total_used += remaining
                    compression_log.append(f"压缩 {name}: → {remaining} tokens")
                else:
                    slot.content = ""
                    slot.tokens = 0
                    compression_log.append(f"舍弃 {name}")
            else:
                remaining = budget - total_used
                if remaining > 0:
                    target_chars = int(remaining * self.CHARS_PER_TOKEN_ZH)
                    slot.content = slot.content[:target_chars] + "..."
                    slot.tokens = remaining
                    total_used += remaining
                    compression_log.append(f"截断 {name}: {remaining} tokens")
                else:
                    slot.content = ""
                    slot.tokens = 0

        return total_used

    # ==================== 沙漏辅助 ====================

    def _estimate_total_chapters(self, novel_id: str) -> int:
        """估算目标总章节数"""
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        if novel and novel.target_chapter_count and novel.target_chapter_count > 0:
            return novel.target_chapter_count

        # 回退：已有最大章节号 × 1.2
        max_ch = (
            self.db.query(Chapter.number)
            .filter_by(novel_id=novel_id)
            .order_by(Chapter.number.desc())
            .first()
        )
        if max_ch:
            return max(int(max_ch[0] * 1.2), max_ch[0] + 10)

        return 100

    def _classify_phase(self, progress: float) -> StoryPhase:
        if progress >= 0.90:
            return StoryPhase.FINALE
        elif progress >= 0.75:
            return StoryPhase.CONVERGENCE
        elif progress >= 0.25:
            return StoryPhase.DEVELOPMENT
        else:
            return StoryPhase.OPENING
