"""逐章 LLM 深度提取 - 人物/事件/关系/伏笔

对每个章节调用 LLM 提取结构化信息，支持异步并发。
使用 get_llm_for_stage("book_analysis_extract") 获取客户端。
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.llm.client import LLMClient, GenerationConfig

logger = logging.getLogger(__name__)


@dataclass
class ChapterAnalysis:
    """单章提取结果"""
    chapter_number: int
    chapter_title: str
    characters: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    foreshadows: list[dict] = field(default_factory=list)
    summary: str = ""
    word_count: int = 0
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "chapter_number": self.chapter_number,
            "chapter_title": self.chapter_title,
            "characters": self.characters,
            "events": self.events,
            "relationships": self.relationships,
            "foreshadows": self.foreshadows,
            "summary": self.summary,
            "word_count": self.word_count,
        }


EXTRACT_SYSTEM_PROMPT = """你是一个专业的小说分析助手。你需要仔细阅读给定的章节内容，并提取结构化信息。

请严格按照以下 JSON 格式输出，不要添加任何额外文字：

{
  "summary": "本章内容概要 (100-200字)",
  "characters": [
    {
      "name": "角色名",
      "role": "主角/配角/路人",
      "actions": ["本章中的关键行为"],
      "emotions": ["本章中的情感变化"],
      "first_appearance": false
    }
  ],
  "events": [
    {
      "description": "事件描述",
      "importance": "high/medium/low",
      "participants": ["参与角色名"],
      "location": "发生地点",
      "type": "conflict/revelation/transition/climax/daily"
    }
  ],
  "relationships": [
    {
      "from": "角色A",
      "to": "角色B",
      "type": "友情/敌对/爱情/师徒/从属/合作/对抗",
      "change": "本章中关系的变化描述，无变化则为空"
    }
  ],
  "foreshadows": [
    {
      "description": "伏笔描述",
      "type": "planted/resolved",
      "hint": "原文暗示线索"
    }
  ]
}"""


EXTRACT_USER_TEMPLATE = """## 小说信息
- 书名: {novel_title}
- 章节: 第{chapter_number}章 - {chapter_title}
- 已知角色: {known_entities}

## 章节正文
{chapter_text}

---
请提取本章的结构化分析信息，严格输出 JSON 格式。"""


async def extract_chapter(
    llm: LLMClient,
    chapter_number: int,
    chapter_title: str,
    chapter_text: str,
    novel_title: str = "",
    known_entities: Optional[list[str]] = None,
    db=None,
) -> ChapterAnalysis:
    """对单个章节进行 LLM 提取"""
    entity_str = ", ".join(known_entities[:30]) if known_entities else "(待识别)"

    # 截断过长章节 (避免超出 token 限制)
    max_chars = 15000
    truncated = chapter_text[:max_chars]
    if len(chapter_text) > max_chars:
        truncated += "\n...(正文过长，已截断)"

    prompt = EXTRACT_USER_TEMPLATE.format(
        novel_title=novel_title or "(未知)",
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        known_entities=entity_str,
        chapter_text=truncated,
    )

    # 优先从 DB 加载拆书提取提示词
    system = EXTRACT_SYSTEM_PROMPT
    if db is not None:
        from app.services.prompt_loader import PromptLoader
        db_prompt = PromptLoader(db).get_prompt("book_analysis_extract")
        if db_prompt:
            system = db_prompt

    config = GenerationConfig(
        system=system,
        temperature=0.3,
        max_tokens=4096,
    )

    try:
        result = await llm.generate(prompt, config)
        parsed = _parse_llm_response(result.content)
        return ChapterAnalysis(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            characters=parsed.get("characters", []),
            events=parsed.get("events", []),
            relationships=parsed.get("relationships", []),
            foreshadows=parsed.get("foreshadows", []),
            summary=parsed.get("summary", ""),
            word_count=len(chapter_text),
            raw_response=result.content,
        )
    except Exception as e:
        logger.error("章节 %d 提取失败: %s", chapter_number, e)
        return ChapterAnalysis(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            summary=f"[提取失败: {e}]",
            word_count=len(chapter_text),
        )


async def extract_all_chapters(
    llm: LLMClient,
    chapters: list[dict],
    novel_title: str = "",
    known_entities: Optional[list[str]] = None,
    concurrency: int = 3,
    progress_callback=None,
) -> list[ChapterAnalysis]:
    """批量提取所有章节，使用信号量控制并发

    Args:
        llm: LLM 客户端
        chapters: [{"number": int, "title": str, "text": str}, ...]
        novel_title: 小说标题
        known_entities: 已知实体列表
        concurrency: 最大并发数
        progress_callback: 进度回调 fn(done, total)
    """
    sem = asyncio.Semaphore(concurrency)
    total = len(chapters)
    done_count = 0
    results: list[ChapterAnalysis] = [None] * total  # type: ignore

    async def _task(idx: int, ch: dict):
        nonlocal done_count
        async with sem:
            r = await extract_chapter(
                llm=llm,
                chapter_number=ch["number"],
                chapter_title=ch["title"],
                chapter_text=ch["text"],
                novel_title=novel_title,
                known_entities=known_entities,
            )
            results[idx] = r
            done_count += 1
            if progress_callback:
                progress_callback(done_count, total)
            logger.info("章节提取完成: %d/%d - %s", done_count, total, ch["title"])

    tasks = [_task(i, ch) for i, ch in enumerate(chapters)]
    await asyncio.gather(*tasks)
    return results


def _parse_llm_response(content: str) -> dict:
    """解析 LLM 返回的 JSON，容错处理"""
    content = content.strip()

    # 尝试提取 JSON 块 (可能被 markdown 代码块包裹)
    json_match = None
    import re
    json_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if json_block:
        json_match = json_block.group(1).strip()
    else:
        # 找第一个 { 到最后一个 }
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace != -1 and last_brace != -1:
            json_match = content[first_brace : last_brace + 1]

    if json_match:
        try:
            return json.loads(json_match)
        except json.JSONDecodeError:
            logger.warning("JSON 解析失败，尝试修复...")
            return _try_fix_json(json_match)

    logger.warning("无法从 LLM 响应中提取 JSON")
    return {"summary": content[:500]}


def _try_fix_json(text: str) -> dict:
    """尝试修复常见的 JSON 错误"""
    import re
    # 移除尾部多余逗号
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # 移除注释
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"summary": "[JSON 解析失败]", "_raw": text[:500]}
