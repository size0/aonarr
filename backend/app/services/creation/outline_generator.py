"""大纲生成服务 — 宏观大纲 + 章节节拍"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

_FALLBACK_MACRO_SYSTEM = """你是一位资深网文策划，擅长设计引人入胜的长篇小说大纲。
请根据用户提供的设定，生成一份结构化的宏观大纲。

输出格式要求（严格 JSON）：
{
  "volumes": [
    {
      "number": 1,
      "title": "卷名",
      "summary": "本卷概要",
      "chapter_range": [1, 50],
      "acts": [
        {
          "number": 1,
          "title": "幕名",
          "chapter_range": [1, 10],
          "summary": "本幕概要",
          "key_events": ["事件1", "事件2"]
        }
      ]
    }
  ],
  "total_chapters": 200,
  "main_conflict": "核心矛盾",
  "character_arcs": [
    {"name": "角色名", "arc": "成长弧线描述"}
  ]
}"""

_FALLBACK_BEATS_SYSTEM = """你是一位资深网文作者，擅长设计章节节拍(beat sheet)。
根据大纲上下文和前文摘要，为指定章节生成详细的节拍列表。

【重要】严格遵守用户给出的字数硬约束。所有节拍的 word_target 之和必须等于目标总字数。
通常 4-6 个节拍，每节拍 300-500 字。

输出格式要求（严格 JSON）：
{
  "chapter_number": N,
  "chapter_title": "章节标题",
  "beats": [
    {
      "index": 1,
      "type": "opening|rising|climax|falling|hook",
      "summary": "这个节拍写什么",
      "word_target": 400,
      "characters_involved": ["角色1"],
      "emotion_tone": "紧张/轻松/悲伤/热血",
      "notes": "特殊要求"
    }
  ],
  "foreshadows_to_plant": ["伏笔描述"],
  "foreshadows_to_pay_off": ["要回收的伏笔"]
}"""


class OutlineGenerator:
    """大纲生成服务"""

    def __init__(self, db: Session):
        self.db = db
        self._resolver = StageModelResolver(db)
        self._prompt_loader = PromptLoader(db)

    async def generate_macro_outline(
        self,
        novel_id: str,
        premise: str,
        genre: str,
        *,
        synopsis: str = "",
        world_setting: str = "",
        target_chapters: int = 200,
    ) -> dict:
        """生成宏观大纲（卷/幕结构）"""
        llm = self._resolver.get_llm_for_stage("outline_planning")

        user_prompt = f"""请为以下小说生成宏观大纲：

【题材】{genre}
【核心设定】{premise}
【简介】{synopsis or '暂无'}
【世界设定】{world_setting or '暂无'}
【目标章数】约 {target_chapters} 章

请生成完整的卷/幕结构大纲。"""

        # 优先从 DB 加载大纲提示词
        raw_prompt = self._prompt_loader.get_prompt("outline_planning", name="极速宏观规划·破城槌")
        if not raw_prompt:
            raw_prompt = self._prompt_loader.get_prompt("outline_planning")
        if not raw_prompt:
            system = _FALLBACK_MACRO_SYSTEM
        else:
            logger.info("大纲生成使用 DB 提示词")
            # 使用 PromptRenderer 正确分离 [SYSTEM]/[USER]
            from app.services.prompt_renderer import render as render_prompt
            rendered = render_prompt(raw_prompt, {
                "genre": genre, "premise": premise,
                "synopsis": synopsis or "", "world_setting": world_setting or "",
                "target_chapters": str(target_chapters),
            })
            system = rendered.system
            # 如果模板有 [USER] 部分且非空，用它替换硬编码 user_prompt
            if rendered.user:
                user_prompt = rendered.user

        config = GenerationConfig(
            system=system,
            max_tokens=8192,
            temperature=0.8,
        )

        result = await llm.generate(user_prompt, config)
        outline = _extract_json(result.content)

        logger.info("宏观大纲已生成: %d 卷, model=%s", len(outline.get("volumes", [])), result.model)
        return outline

    async def generate_chapter_beats(
        self,
        novel_id: str,
        chapter_number: int,
        *,
        outline: str = "",
        previous_summaries: str = "",
        previous_ending: str = "",
        story_log: str = "",
        characters: str = "",
        active_foreshadows: str = "",
        words_per_chapter: int = 2000,
    ) -> dict:
        """为指定章节生成节拍列表"""
        llm = self._resolver.get_llm_for_stage("outline_planning")

        # 从知识库检索节奏/结构方法论
        knowledge_hint = self._get_beat_knowledge(chapter_number)

        # 根据目标字数计算节拍数和每节拍字数
        beat_count = max(4, min(6, words_per_chapter // 400))
        per_beat = words_per_chapter // beat_count

        # ── 黄金三章特殊要求 ──
        golden_rules = ""
        if chapter_number == 1:
            golden_rules = """
⚠️ 【黄金第一章·硬性要求】这是全书最重要的一章，决定读者去留！
必须包含以下要素，缺一不可：
1. 开篇即冲突：从一个紧张/有趣/悬疑的场景开始，禁止慢热描写
2. 金手指初现：主角的核心能力必须在本章展示（至少暗示），让读者知道爽点在哪
3. 主角人设立住：通过行动（不是内心独白）展示主角的核心性格魅力
4. 阅读期待建立：本章结尾必须有一个强钩子，让读者迫不及待想看下一章
5. 事件密度要高：开篇节奏必须快，禁止大段环境描写和背景交代
6. 世界观融入情节：设定通过角色对话和行动自然展现，绝不能像说明书"""
        elif chapter_number == 2:
            golden_rules = """
⚠️ 【黄金第二章·硬性要求】趁热打铁，把第一章建立的期待兑现一部分！
必须包含以下要素：
1. 能力验证：主角的金手指必须在本章得到实际应用和效果展示
2. 第一个小爽点：让读者看到金手指的厉害/有趣之处
3. 矛盾升级：引入或加深至少一个冲突（对手、困境、秘密）
4. 人物关系推进：至少一个重要配角有实质性互动
5. 节奏保持快：事件密集，不要松懈"""
        elif chapter_number == 3:
            golden_rules = """
⚠️ 【黄金第三章·硬性要求】三章定生死，必须让读者彻底上钩！
必须包含以下要素：
1. 爽点爆发：给读者一个明确的爽感满足（打脸/逆袭/揭秘/获得）
2. 格局打开：暗示更大的世界和更大的可能性
3. 悬念加深：至少一个让读者睡前还在想的悬念
4. 情感共鸣：让读者开始代入主角、关心主角的命运
5. 钩子极强：章末的悬念/期待值拉到最高"""

        # 从大纲中提取当前章的摘要作为核心约束
        chapter_plot = ""
        if outline:
            for line in outline.split("\n"):
                if line.strip().startswith("→"):
                    # 这是当前章的大纲行
                    chapter_plot = line.strip().lstrip("→").strip()
                    break

        user_prompt = f"""请为第 {chapter_number} 章生成节拍列表。

【本章剧情·必须严格遵循】
{chapter_plot or '暂无'}

【字数硬约束】总共 {words_per_chapter} 字，{beat_count} 个节拍，每节拍约 {per_beat} 字。
{golden_rules}
【前后章大纲】
{outline or '暂无大纲'}

【故事日志（前文所有章节的结构化总结）】
{story_log or '这是第一章'}

【上一章结尾】
{previous_ending or '这是第一章，无前文'}

【人物】{characters or '暂无'}
【伏笔】{active_foreshadows or '暂无'}
{knowledge_hint}
要求：
1. 第一个节拍必须从上一章结尾的情境自然接续，不能凭空开新场景
2. 节拍必须按顺序推进【本章剧情】，不许遗漏也不许新增无关内容
3. 每个节拍有明确的单一事件，不能在一个节拍里塞两三件事
4. 节拍之间有因果递进关系，不能互相割裂
5. 最后一个节拍必须留钩子

输出JSON格式：{{"beats":[{{"summary":"做什么","word_target":{per_beat},"emotion_tone":"基调","characters_involved":["人名"]}}]}}"""

        # 优先从 DB 加载节拍提示词
        raw_prompt = self._prompt_loader.get_prompt("outline_planning", name="节拍表拆解（Scene & Sequel）")
        if not raw_prompt:
            raw_prompt = self._prompt_loader.get_prompt("outline_planning")
        if not raw_prompt:
            system = _FALLBACK_BEATS_SYSTEM
        else:
            logger.info("节拍生成使用 DB 提示词")
            from app.services.prompt_renderer import render as render_prompt
            rendered = render_prompt(raw_prompt, {
                "chapter_number": str(chapter_number),
                "words_per_chapter": str(words_per_chapter),
                "beat_count": str(beat_count),
            })
            system = rendered.system
            if rendered.user:
                user_prompt = rendered.user

        config = GenerationConfig(
            system=system,
            max_tokens=4096,
            temperature=0.7,
        )

        result = await llm.generate(user_prompt, config)
        beats = _extract_json(result.content)

        # 兼容 LLM 直接返回 list 或 {"beats": [...]}
        if isinstance(beats, list):
            beats = {"beats": beats}
        elif isinstance(beats, dict) and "beats" not in beats:
            # 尝试找第一个 list 值作为 beats
            for v in beats.values():
                if isinstance(v, list):
                    beats = {"beats": v}
                    break
            else:
                beats = {"beats": []}

        logger.info("第%d章节拍已生成: %d 个 beat", chapter_number, len(beats.get("beats", [])))
        return beats

    def _get_beat_knowledge(self, chapter_number: int) -> str:
        """从知识库检索节奏/爽点/冲突方法论，注入节拍生成提示"""
        try:
            from app.models.learning import KnowledgeEntry
            entries = (
                self.db.query(KnowledgeEntry)
                .filter(
                    KnowledgeEntry.category.in_([
                        "pacing_technique", "writing_technique", "writing_advanced",
                        "webnovel_basics", "webnovel_workflow",
                    ]),
                    KnowledgeEntry.quality_score >= 0.7,
                )
                .order_by(KnowledgeEntry.quality_score.desc())
                .limit(5)
                .all()
            )
            if not entries:
                return ""

            lines = ["\n【写作方法论参考】"]
            for entry in entries:
                try:
                    content = json.loads(entry.content) if entry.content else {}
                except (json.JSONDecodeError, TypeError):
                    content = {}
                elems = content.get("core_elements", content.get("insights", []))[:2]
                if elems:
                    lines.append(f"· {entry.title}: {elems[0][:60]}")
            return "\n".join(lines) if len(lines) > 1 else ""
        except Exception as e:
            logger.debug("知识库检索跳过: %s", e)
            return ""


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON（容错处理）"""
    # 尝试直接解析
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ``` 块
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        try:
            return json.loads(text[start:end].strip())
        except json.JSONDecodeError:
            pass

    # 尝试找到第一个 { 和最后一个 }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("无法从 LLM 输出中提取 JSON，返回原始文本")
    return {"raw": text}
