"""一致性校验 — 人物描述矛盾 + 时间线矛盾

调用 get_llm_for_stage("audit_review") 做深度检查。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.llm.client import LLMClient, GenerationConfig
from app.models.novel import Chapter, Character

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    issue_type: str  # character / timeline / location / logic
    severity: str    # error / warning / info
    description: str
    chapter_range: str = ""  # "第3章-第7章" or "第5章"
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "chapter_range": self.chapter_range,
            "details": self.details,
        }


@dataclass
class ConsistencyReport:
    """一致性校验报告"""
    novel_id: str
    issues: list[ConsistencyIssue] = field(default_factory=list)
    checked_chapters: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def to_dict(self) -> dict:
        return {
            "novel_id": self.novel_id,
            "issues": [i.to_dict() for i in self.issues],
            "checked_chapters": self.checked_chapters,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "total_issues": len(self.issues),
        }


# ── 人物一致性 ──────────────────────────────────────────────────

CHARACTER_CHECK_SYSTEM = """你是一位小说审校专家，擅长发现人物描述的前后矛盾。
基于提供的多个章节中对同一角色的描述，找出矛盾之处。

请严格按 JSON 格式输出：
{
  "issues": [
    {
      "character": "角色名",
      "severity": "error/warning",
      "description": "矛盾描述",
      "chapter_a": "章节A编号",
      "chapter_b": "章节B编号",
      "detail_a": "章节A中的描述",
      "detail_b": "章节B中的矛盾描述"
    }
  ]
}

注意:
- 仅报告确定的矛盾, 不要报告模糊或可解释的差异
- severity="error" 表示明确矛盾 (如外貌/年龄/身份冲突)
- severity="warning" 表示可疑不一致 (如性格突变无铺垫)"""


async def check_character_consistency(
    db: Session,
    llm: LLMClient,
    novel_id: str,
    chapter_number: int | None = None,
) -> list[ConsistencyIssue]:
    """检查人物描述一致性"""
    # 加载角色列表
    characters = db.query(Character).filter_by(novel_id=novel_id).all()
    if not characters:
        return []

    # 加载章节
    q = db.query(Chapter).filter_by(novel_id=novel_id).order_by(Chapter.number)
    chapters = q.all()
    if not chapters:
        return []

    # 构建角色在各章节中的出现信息
    char_names = [c.name for c in characters]
    char_mentions: dict[str, list[dict]] = {name: [] for name in char_names}

    for ch in chapters:
        if not ch.content:
            continue
        for name in char_names:
            if name in ch.content:
                # 提取包含角色名的上下文句子
                contexts = _extract_character_context(ch.content, name, max_snippets=3)
                if contexts:
                    char_mentions[name].append({
                        "chapter": ch.number,
                        "title": ch.title,
                        "contexts": contexts,
                    })

    # 仅对出现在多章中的角色做检查
    issues: list[ConsistencyIssue] = []
    chars_to_check = {
        name: mentions
        for name, mentions in char_mentions.items()
        if len(mentions) >= 2
    }

    if not chars_to_check:
        return issues

    # 构建 LLM 提示
    prompt_parts = ["以下是各角色在不同章节中的描述，请找出矛盾：\n"]
    for name, mentions in chars_to_check.items():
        prompt_parts.append(f"\n## 角色: {name}")
        for m in mentions[:6]:  # 限制上下文量
            prompt_parts.append(f"\n### 第{m['chapter']}章 ({m['title']})")
            for ctx in m["contexts"]:
                prompt_parts.append(f"- {ctx}")

    prompt = "\n".join(prompt_parts)

    config = GenerationConfig(
        system=CHARACTER_CHECK_SYSTEM,
        temperature=0.3,
        max_tokens=3000,
    )

    try:
        result = await llm.generate(prompt, config)
        parsed = _parse_json_response(result.content)
        for item in parsed.get("issues", []):
            issues.append(ConsistencyIssue(
                issue_type="character",
                severity=item.get("severity", "warning"),
                description=item.get("description", ""),
                chapter_range=f"第{item.get('chapter_a', '?')}章-第{item.get('chapter_b', '?')}章",
                details={
                    "character": item.get("character", ""),
                    "detail_a": item.get("detail_a", ""),
                    "detail_b": item.get("detail_b", ""),
                },
            ))
    except Exception as e:
        logger.error("人物一致性检查 LLM 调用失败: %s", e)

    return issues


# ── 时间线一致性 ────────────────────────────────────────────────

TIMELINE_CHECK_SYSTEM = """你是一位小说审校专家，擅长发现时间线矛盾。
基于提供的章节摘要和事件列表，找出时间线矛盾。

请严格按 JSON 格式输出：
{
  "issues": [
    {
      "severity": "error/warning",
      "description": "时间线矛盾描述",
      "chapter_a": "章节A编号",
      "chapter_b": "章节B编号",
      "event_a": "事件A",
      "event_b": "冲突事件B"
    }
  ]
}

仅报告确定的时间线矛盾 (如先后顺序错误/时间跨度不合理/白天黑夜矛盾)。"""


async def check_timeline_consistency(
    db: Session,
    llm: LLMClient,
    novel_id: str,
) -> list[ConsistencyIssue]:
    """检查时间线一致性"""
    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .order_by(Chapter.number)
        .all()
    )
    if len(chapters) < 2:
        return []

    # 构建时间线上下文
    prompt_parts = ["以下是各章节的摘要和事件，请找出时间线矛盾：\n"]
    for ch in chapters:
        events = json.loads(ch.events) if ch.events else []
        event_texts = [e.get("description", str(e)) if isinstance(e, dict) else str(e) for e in events[:5]]
        prompt_parts.append(f"\n## 第{ch.number}章: {ch.title}")
        prompt_parts.append(f"摘要: {ch.summary[:200]}")
        if event_texts:
            prompt_parts.append("事件: " + "; ".join(event_texts))

    prompt = "\n".join(prompt_parts)

    config = GenerationConfig(
        system=TIMELINE_CHECK_SYSTEM,
        temperature=0.3,
        max_tokens=3000,
    )

    issues: list[ConsistencyIssue] = []
    try:
        result = await llm.generate(prompt, config)
        parsed = _parse_json_response(result.content)
        for item in parsed.get("issues", []):
            issues.append(ConsistencyIssue(
                issue_type="timeline",
                severity=item.get("severity", "warning"),
                description=item.get("description", ""),
                chapter_range=f"第{item.get('chapter_a', '?')}章-第{item.get('chapter_b', '?')}章",
                details={
                    "event_a": item.get("event_a", ""),
                    "event_b": item.get("event_b", ""),
                },
            ))
    except Exception as e:
        logger.error("时间线一致性检查 LLM 调用失败: %s", e)

    return issues


# ── 综合检查 ────────────────────────────────────────────────────

async def check_full_consistency(
    db: Session,
    llm: LLMClient,
    novel_id: str,
) -> ConsistencyReport:
    """执行完整一致性校验"""
    report = ConsistencyReport(novel_id=novel_id)

    chapters = db.query(Chapter).filter_by(novel_id=novel_id).all()
    report.checked_chapters = len(chapters)

    char_issues = await check_character_consistency(db, llm, novel_id)
    report.issues.extend(char_issues)

    timeline_issues = await check_timeline_consistency(db, llm, novel_id)
    report.issues.extend(timeline_issues)

    return report


# ── 工具函数 ────────────────────────────────────────────────────

def _extract_character_context(text: str, name: str, max_snippets: int = 3) -> list[str]:
    """提取包含角色名的上下文片段"""
    sentences = re.split(r'[。！？!?\n]', text)
    contexts: list[str] = []
    for s in sentences:
        s = s.strip()
        if name in s and len(s) > 5:
            contexts.append(s[:150])
            if len(contexts) >= max_snippets:
                break
    return contexts


def _parse_json_response(content: str) -> dict:
    """解析 LLM JSON 响应"""
    content = content.strip()
    block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    text = block.group(1).strip() if block else content
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        text = text[first:last + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"issues": []}
