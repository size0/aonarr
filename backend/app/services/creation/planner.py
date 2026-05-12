"""Planner — 读取 author_intent + current_focus + 真相文件，产出本章意图

职责：
1. 读取作者对本章的意图（author_intent，可由前端面板传入）
2. 读取当前焦点（current_focus: 主线推进/支线展开/情感深化等）
3. 读取真相文件中的最新状态
4. 输出本章详细写作计划（chapter_plan）

输出结构：
{
  "chapter_intent": "本章核心目标（一句话）",
  "pov": "视角角色",
  "location": "场景地点",
  "tone": "情感基调",
  "key_events": ["关键事件1", "关键事件2"],
  "character_goals": [{"name": "角色名", "goal": "本章目标"}],
  "foreshadow_actions": [{"hook": "伏笔描述", "action": "plant|track|payoff"}],
  "beats_suggestion": [{"type": "opening|rising|climax|falling|hook", "summary": "节拍概要"}],
  "constraints": ["不可违反的约束"]
}
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.models.novel import Novel, TruthFile
from app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM = """你是一位专业的网文写作策划师。根据作者意图、当前状态和真相文件，制定本章详细写作计划。

输出严格 JSON 格式：
{
  "chapter_intent": "本章核心目标（一句话）",
  "pov": "视角角色名",
  "location": "主要场景",
  "tone": "情感基调",
  "key_events": ["关键事件1", "关键事件2"],
  "character_goals": [{"name": "角色名", "goal": "本章目标"}],
  "foreshadow_actions": [{"hook": "伏笔描述", "action": "plant|track|payoff"}],
  "beats_suggestion": [
    {"type": "opening", "summary": "开场概要", "word_target": 400},
    {"type": "rising", "summary": "升温概要", "word_target": 500},
    {"type": "climax", "summary": "高潮概要", "word_target": 500},
    {"type": "falling", "summary": "落潮概要", "word_target": 400},
    {"type": "hook", "summary": "钩子概要", "word_target": 300}
  ],
  "constraints": ["不可违反的约束1", "约束2"]
}

规则：
1. beats_suggestion 给出 4-7 个节拍
2. 每个节拍标明 type 和 word_target
3. constraints 列出当前真相文件中不可违反的硬事实
4. foreshadow_actions 基于 pending_hooks 决定本章要推进/回收哪些伏笔
5. 不要编造真相文件中不存在的角色或设定"""


class Planner:
    """章节写作计划生成器"""

    def __init__(self, db: Session):
        self.db = db
        self._resolver = StageModelResolver(db)
        self._prompt_loader = PromptLoader(db)

    async def plan(
        self,
        novel_id: str,
        chapter_number: int,
        *,
        author_intent: str = "",
        current_focus: str = "",
    ) -> dict:
        """生成本章写作计划

        Args:
            novel_id: 小说 ID
            chapter_number: 要规划的章节号
            author_intent: 作者对本章的意图（自然语言，可为空）
            current_focus: 当前写作焦点（主线推进/支线展开等）

        Returns:
            结构化的 chapter_plan dict
        """
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        if not novel:
            raise ValueError(f"小说不存在: {novel_id}")

        # 收集真相文件
        truth_context = self._gather_truth_files(novel_id)

        # 获取 LLM
        llm = self._resolver.get_llm_for_stage("outline_planning")

        system = self._prompt_loader.get_prompt(
            "outline_planning", name="Planner 章节规划"
        )
        if not system:
            system = _PLANNER_SYSTEM

        config = GenerationConfig(
            system=system,
            max_tokens=4096,
            temperature=0.7,
        )

        user_prompt = f"""请为以下小说的第 {chapter_number} 章制定写作计划。

【小说信息】
标题：《{novel.title}》
题材：{novel.genre}
简介：{novel.synopsis or '暂无'}
已写章数：{novel.chapter_count}
已写字数：{novel.current_word_count}

【作者意图】
{author_intent or '（未指定，请根据故事发展自行规划）'}

【当前焦点】
{current_focus or '主线推进'}

【真相文件·当前状态】
{truth_context.get('current_state', '暂无数据')}

【真相文件·未闭合伏笔】
{truth_context.get('pending_hooks', '暂无伏笔')}

【真相文件·角色关系】
{truth_context.get('character_matrix', '暂无关系数据')}

【真相文件·情感弧线】
{truth_context.get('emotional_arcs', '暂无情感数据')}

【最近章节摘要】
{truth_context.get('chapter_summaries', '暂无摘要')}

请输出本章的详细写作计划（严格 JSON 格式）。"""

        result = await llm.generate(user_prompt, config)
        plan = _extract_json(result.content)

        logger.info(
            "[Planner] novel=%s ch=%d → intent=%s, beats=%d",
            novel_id, chapter_number,
            plan.get("chapter_intent", "?")[:30],
            len(plan.get("beats_suggestion", [])),
        )
        return plan

    def _gather_truth_files(self, novel_id: str) -> dict[str, str]:
        """读取所有真相文件的 markdown 内容"""
        truth_files = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id)
            .all()
        )
        result = {}
        for tf in truth_files:
            # 截断过长内容
            content = tf.content or ""
            if len(content) > 2000:
                content = content[:2000] + "\n…（已截断）"
            result[tf.file_key] = content
        return result


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        try:
            return json.loads(text[start:end].strip())
        except json.JSONDecodeError:
            pass
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        try:
            return json.loads(text[first:last + 1])
        except json.JSONDecodeError:
            pass
    return {"chapter_intent": "规划失败", "beats_suggestion": [], "raw": text[:500]}
