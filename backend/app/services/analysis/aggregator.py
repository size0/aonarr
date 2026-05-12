"""全局聚合器 - 逆向大纲 + 人物图谱 + 时间线 + 伏笔网

将逐章提取的结构化数据聚合为全局视图，可选调用 LLM 深度分析。
使用 get_llm_for_stage("book_analysis_deep") 获取客户端。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.llm.client import LLMClient, GenerationConfig

logger = logging.getLogger(__name__)


@dataclass
class CharacterProfile:
    name: str
    role: str = "unknown"
    first_chapter: int = 0
    last_chapter: int = 0
    appearance_count: int = 0
    relationships: list[dict] = field(default_factory=list)
    arc_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "first_chapter": self.first_chapter,
            "last_chapter": self.last_chapter,
            "appearance_count": self.appearance_count,
            "relationships": self.relationships,
            "arc_summary": self.arc_summary,
        }


@dataclass
class TimelineEvent:
    chapter: int
    description: str
    importance: str = "medium"
    participants: list[str] = field(default_factory=list)
    event_type: str = ""

    def to_dict(self) -> dict:
        return {
            "chapter": self.chapter,
            "description": self.description,
            "importance": self.importance,
            "participants": self.participants,
            "event_type": self.event_type,
        }


@dataclass
class ForeshadowLink:
    description: str
    planted_chapter: int = 0
    resolved_chapter: int = 0
    status: str = "open"  # open / resolved
    hint: str = ""

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "planted_chapter": self.planted_chapter,
            "resolved_chapter": self.resolved_chapter,
            "status": self.status,
            "hint": self.hint,
        }


@dataclass
class AggregationResult:
    reverse_outline: list[dict] = field(default_factory=list)
    character_profiles: list[CharacterProfile] = field(default_factory=list)
    relationship_graph: list[dict] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    foreshadow_net: list[ForeshadowLink] = field(default_factory=list)
    global_summary: str = ""
    theme_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "reverse_outline": self.reverse_outline,
            "character_profiles": [c.to_dict() for c in self.character_profiles],
            "relationship_graph": self.relationship_graph,
            "timeline": [t.to_dict() for t in self.timeline],
            "foreshadow_net": [f.to_dict() for f in self.foreshadow_net],
            "global_summary": self.global_summary,
            "theme_keywords": self.theme_keywords,
        }


def aggregate(chapter_analyses: list[dict]) -> AggregationResult:
    """纯算法聚合 (不调用 LLM)

    Args:
        chapter_analyses: 逐章提取结果 list of ChapterAnalysis.to_dict()
    """
    result = AggregationResult()

    char_data: dict[str, CharacterProfile] = {}
    rel_set: dict[str, dict] = {}
    all_events: list[TimelineEvent] = []
    all_foreshadows: list[ForeshadowLink] = []

    for ch in chapter_analyses:
        ch_num = ch.get("chapter_number", 0)
        ch_title = ch.get("chapter_title", "")

        # -- reverse outline --
        result.reverse_outline.append({
            "chapter": ch_num,
            "title": ch_title,
            "summary": ch.get("summary", ""),
            "event_count": len(ch.get("events", [])),
            "character_count": len(ch.get("characters", [])),
        })

        # -- characters --
        for c in ch.get("characters", []):
            name = c.get("name", "").strip()
            if not name:
                continue
            if name not in char_data:
                char_data[name] = CharacterProfile(
                    name=name,
                    role=c.get("role", "unknown"),
                    first_chapter=ch_num,
                )
            prof = char_data[name]
            prof.last_chapter = ch_num
            prof.appearance_count += 1
            if c.get("role") in ("protagonist", "main"):
                prof.role = c["role"]

        # -- relationships --
        for r in ch.get("relationships", []):
            fr = r.get("from", "").strip()
            to = r.get("to", "").strip()
            if not fr or not to:
                continue
            key = f"{fr}->{to}"
            if key not in rel_set:
                rel_set[key] = {
                    "from": fr,
                    "to": to,
                    "type": r.get("type", "unknown"),
                    "chapters": [],
                    "changes": [],
                }
            rel_set[key]["chapters"].append(ch_num)
            change = r.get("change", "")
            if change:
                rel_set[key]["changes"].append({"chapter": ch_num, "change": change})

        # -- events -> timeline --
        for e in ch.get("events", []):
            all_events.append(TimelineEvent(
                chapter=ch_num,
                description=e.get("description", ""),
                importance=e.get("importance", "medium"),
                participants=e.get("participants", []),
                event_type=e.get("type", ""),
            ))

        # -- foreshadows --
        for f in ch.get("foreshadows", []):
            fs = ForeshadowLink(
                description=f.get("description", ""),
                hint=f.get("hint", ""),
            )
            if f.get("type") == "planted":
                fs.planted_chapter = ch_num
                fs.status = "open"
            elif f.get("type") == "resolved":
                fs.resolved_chapter = ch_num
                fs.status = "resolved"
            all_foreshadows.append(fs)

    # -- finalize --
    profiles = sorted(char_data.values(), key=lambda c: c.appearance_count, reverse=True)
    result.character_profiles = profiles
    result.relationship_graph = list(rel_set.values())
    result.timeline = sorted(all_events, key=lambda e: e.chapter)
    result.foreshadow_net = _match_foreshadows(all_foreshadows)

    return result


def _match_foreshadows(foreshadows: list[ForeshadowLink]) -> list[ForeshadowLink]:
    """尝试将 planted 和 resolved 的伏笔配对"""
    planted = [f for f in foreshadows if f.status == "open"]
    resolved = [f for f in foreshadows if f.status == "resolved"]

    for r in resolved:
        for p in planted:
            if p.status == "resolved":
                continue
            # 简单关键词匹配
            if _text_overlap(p.description, r.description) > 0.3:
                p.resolved_chapter = r.resolved_chapter
                p.status = "resolved"
                break

    return planted + [r for r in resolved if not any(
        p.resolved_chapter == r.resolved_chapter and p.status == "resolved"
        for p in planted
    )]


def _text_overlap(a: str, b: str) -> float:
    """简单文本重叠度"""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


DEEP_AGGREGATE_SYSTEM = """你是一个资深文学分析师。基于以下小说各章节的结构化分析数据，请输出全局深度分析。

请严格按照 JSON 格式输出：
{
  "global_summary": "全书内容概要 (300-500字)",
  "theme_keywords": ["主题关键词1", "主题关键词2", ...],
  "character_arcs": [
    {"name": "角色名", "arc_summary": "角色弧线描述 (50-100字)"}
  ],
  "plot_structure": {
    "exposition": "铺垫阶段描述",
    "rising_action": "发展阶段描述",
    "climax": "高潮描述",
    "falling_action": "回落阶段描述",
    "resolution": "结局描述"
  }
}"""


async def deep_aggregate(
    llm: LLMClient,
    chapter_analyses: list[dict],
    novel_title: str = "",
) -> dict:
    """使用 LLM 进行深度全局分析"""
    # 构建精简的章节摘要列表
    summaries = []
    for ch in chapter_analyses:
        summaries.append({
            "chapter": ch.get("chapter_number"),
            "title": ch.get("chapter_title", ""),
            "summary": ch.get("summary", ""),
            "characters": [c.get("name") for c in ch.get("characters", [])],
            "event_count": len(ch.get("events", [])),
        })

    prompt = f"""## 小说: {novel_title or '(未知)'}
## 各章摘要:
{json.dumps(summaries, ensure_ascii=False, indent=2)}

请进行全局深度分析。"""

    config = GenerationConfig(
        system=DEEP_AGGREGATE_SYSTEM,
        temperature=0.4,
        max_tokens=4096,
    )

    try:
        result = await llm.generate(prompt, config)
        return _parse_json_response(result.content)
    except Exception as e:
        logger.error("深度聚合失败: %s", e)
        return {"global_summary": f"[深度分析失败: {e}]"}


def _parse_json_response(content: str) -> dict:
    """解析 LLM JSON 响应"""
    import re
    content = content.strip()
    json_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    text = json_block.group(1).strip() if json_block else content

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        text = text[first:last + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"global_summary": content[:1000]}
