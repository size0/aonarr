"""Observer Agent — 从已写章节正文中提取 9 类事实

9 类事实维度：
1. characters  — 出场角色及行为
2. locations   — 场景/地点变化
3. resources   — 物品/金钱/资源变动
4. relations   — 角色关系变化
5. emotions    — 情感状态变化
6. information — 角色获得/泄露的信息
7. foreshadows — 伏笔（埋设/推进/回收）
8. timeline    — 时间线推进（时间跨度/时间点）
9. physics     — 物理状态（伤势/修为/能力变化）

提取结果为结构化 JSON，供 Reflector 写入真相文件。
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.models.novel import Novel
from app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

_OBSERVER_SYSTEM = """你是一位精密的小说事实提取引擎。给定一章正文，你必须从中提取 9 个维度的结构化事实。

输出严格 JSON 格式：
{
  "facts": [
    {
      "category": "characters|locations|resources|relations|emotions|information|foreshadows|timeline|physics",
      "subject": "主体（角色名）",
      "predicate": "动作/变化描述",
      "object": "客体（角色名/地点名/物品名）",
      "detail": "具体细节（30字以内）",
      "confidence": 0.9
    }
  ]
}

提取规则：
1. characters — 每个出场角色列一条，记录本章关键行为
2. locations — 场景变化、新地点出现
3. resources — 物品获得/失去、金钱变动、功法获取
4. relations — 【重要！】任意两个角色之间发生互动、对话、冲突、合作、帮助、背叛等，都必须提取一条 relations 事实。subject 和 object 必须都填角色全名。detail 必须描述关系性质（如：信任加深、产生矛盾、结为盟友、初次相遇等）。每章至少检查所有出场角色两两之间是否有互动。
   示例：{"category":"relations","subject":"林渊","predicate":"救了","object":"苏清寒","detail":"信任加深，苏清寒开始认可林渊","confidence":0.9}
5. emotions — 角色情感状态显著变化
6. information — 角色获知新信息、秘密暴露
7. foreshadows — 新埋伏笔(planted)、推进中(tracked)、已回收(paid_off)
8. timeline — 时间推进（"三天后"、"次日黎明"等），subject填"时间"，detail填具体时间点或跨度
   示例：{"category":"timeline","subject":"时间","predicate":"推进","object":"","detail":"比赛第二天清晨","confidence":0.95}
9. physics — 修为突破、受伤、能力觉醒、体质变化

要求：
- confidence 为 0-1 之间的浮点数，0.7 以下的弱推测可省略
- relations 和 timeline 是最容易遗漏的维度，请特别注意
- 不要编造正文中不存在的事实
- 总条目控制在 8-40 条，其中 relations 至少 2 条（有互动的话）"""


class Observer:
    """从章节正文中提取结构化事实"""

    def __init__(self, db: Session):
        self.db = db
        self._resolver = StageModelResolver(db)
        self._prompt_loader = PromptLoader(db)

    async def extract_facts(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        *,
        max_content_chars: int = 8000,
    ) -> list[dict]:
        """提取 9 类事实

        Returns:
            list of fact dicts, each with category/subject/predicate/detail/confidence
        """
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        novel_title = novel.title if novel else "未知"
        novel_genre = novel.genre if novel else ""

        # 获取 LLM（使用 post_chapter_pipeline 阶段的低温模型）
        llm = self._resolver.get_llm_for_stage("post_chapter_pipeline")

        system = self._prompt_loader.get_prompt(
            "post_chapter_pipeline", name="Observer 事实提取"
        )
        if not system:
            system = _OBSERVER_SYSTEM

        config = GenerationConfig(
            system=system,
            max_tokens=4096,
            temperature=0.3,
        )

        user_prompt = f"""请从以下章节正文中提取结构化事实。

【小说】《{novel_title}》（{novel_genre}）
【章节】第 {chapter_number} 章
【字数】{len(content)} 字

---正文开始---
{content[:max_content_chars]}
---正文结束---

请严格按 JSON 格式输出提取的事实列表。"""

        result = await llm.generate(user_prompt, config)
        parsed = _extract_json(result.content)

        facts = parsed.get("facts", []) if isinstance(parsed, dict) else []
        if isinstance(parsed, list):
            facts = parsed

        # 过滤低置信度
        facts = [
            f for f in facts
            if isinstance(f, dict) and f.get("confidence", 1.0) >= 0.7
        ]

        # ── 人名归一化：将别名/泛称映射到规范角色名 ──
        facts = self._normalize_names(novel_id, facts)

        logger.info(
            "[Observer] novel=%s ch=%d → %d facts extracted",
            novel_id, chapter_number, len(facts),
        )
        return facts

    def _normalize_names(self, novel_id: str, facts: list[dict]) -> list[dict]:
        """用 NameAuthority 对 fact 中的 subject/object 做规范化"""
        try:
            from app.services.creation.name_authority import NameAuthority, is_generic_reference
            authority = NameAuthority.from_novel(self.db, novel_id)
            if not authority.canonical_names:
                return facts

            for fact in facts:
                # 归一化 subject
                subj = fact.get("subject", "")
                if subj:
                    resolved = authority.resolve(subj, keep_unknown=True)
                    if resolved:
                        fact["subject"] = resolved

                # 归一化 object
                obj = fact.get("object", "")
                if obj:
                    resolved = authority.resolve(obj, keep_unknown=True)
                    if resolved:
                        fact["object"] = resolved

                # 过滤 subject 为纯泛称的 characters 类事实
                if fact.get("category") == "characters":
                    if is_generic_reference(fact.get("subject", "")):
                        fact["confidence"] = 0.0  # 标记为低置信度，后续被过滤

            # 二次过滤
            facts = [f for f in facts if f.get("confidence", 1.0) >= 0.7]
        except Exception as e:
            logger.warning("人名归一化跳过: %s", e)

        return facts


def _extract_json(text: str) -> dict | list:
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
    # 找第一个 { 或 [
    for i, c in enumerate(text):
        if c in "{[":
            for j in range(len(text) - 1, i, -1):
                if text[j] in "}]":
                    try:
                        return json.loads(text[i:j + 1])
                    except json.JSONDecodeError:
                        break
    return {"facts": []}
