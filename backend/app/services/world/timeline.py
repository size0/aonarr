"""时间线聚合器 — 从章节 events 和 Observer timeline facts 自动构建全书时间线

数据来源：
1. Chapter.events JSON（post_pipeline 提取的事件列表）
2. MemoryIndex 中 entry_type='event' 的记忆条目
3. Observer 提取的 category='timeline' facts（存在真相文件中）

输出：按章节排序的时间线条目列表，支持过滤和分页。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models.novel import Novel, Chapter

logger = logging.getLogger(__name__)


@dataclass
class TimelineEntry:
    """时间线条目"""
    chapter_number: int
    chapter_title: str = ""
    time_marker: str = ""          # 时间标记（"第二天黎明"、"三个月后"）
    description: str = ""
    importance: str = "medium"     # high / medium / low
    category: str = "event"        # event / timeline / milestone
    characters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "chapter": self.chapter_number,
            "chapter_title": self.chapter_title,
            "time": self.time_marker,
            "description": self.description,
            "importance": self.importance,
            "category": self.category,
            "characters": self.characters,
        }


@dataclass
class Timeline:
    """全书时间线"""
    novel_id: str
    novel_title: str = ""
    entries: list[TimelineEntry] = field(default_factory=list)
    chapter_count: int = 0
    milestone_count: int = 0

    def to_dict(self) -> dict:
        return {
            "novel_id": self.novel_id,
            "novel_title": self.novel_title,
            "total_entries": len(self.entries),
            "chapter_count": self.chapter_count,
            "milestone_count": self.milestone_count,
            "entries": [e.to_dict() for e in self.entries],
        }


def build_timeline(db: Session, novel_id: str, importance_filter: Optional[str] = None) -> Timeline:
    """从 DB 中聚合构建全书时间线"""
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        return Timeline(novel_id=novel_id)

    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .order_by(Chapter.number)
        .all()
    )

    tl = Timeline(
        novel_id=novel_id,
        novel_title=novel.title,
        chapter_count=len(chapters),
    )

    for ch in chapters:
        ch_title = ch.title or f"第{ch.number}章"

        # 1. 从 events JSON 提取
        if ch.events:
            try:
                events = json.loads(ch.events) if isinstance(ch.events, str) else ch.events
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    imp = ev.get("importance", "medium")
                    if importance_filter and imp != importance_filter:
                        continue
                    entry = TimelineEntry(
                        chapter_number=ch.number,
                        chapter_title=ch_title,
                        time_marker="",
                        description=ev.get("description", "")[:100],
                        importance=imp,
                        category="event",
                    )
                    tl.entries.append(entry)
            except (json.JSONDecodeError, TypeError):
                pass

        # 2. 从 entities 提取关键人物行为作为里程碑
        if ch.entities:
            try:
                entities = json.loads(ch.entities) if isinstance(ch.entities, str) else ch.entities
                for ent in entities:
                    if not isinstance(ent, dict):
                        continue
                    state_change = ent.get("state_change", "")
                    if state_change and len(state_change) > 5:
                        entry = TimelineEntry(
                            chapter_number=ch.number,
                            chapter_title=ch_title,
                            description=f"{ent.get('name', '?')}: {state_change}"[:100],
                            importance="medium",
                            category="milestone",
                            characters=[ent.get("name", "")],
                        )
                        tl.entries.append(entry)
            except (json.JSONDecodeError, TypeError):
                pass

    # 3. 从 MemoryIndex 补充 timeline 类型条目
    try:
        from app.models.novel import MemoryIndex
        mem_entries = (
            db.query(MemoryIndex)
            .filter_by(novel_id=novel_id)
            .filter(MemoryIndex.entry_type.in_(["event", "fact"]))
            .filter(MemoryIndex.importance >= 6)
            .order_by(MemoryIndex.chapter_number)
            .all()
        )
        existing_descs = {e.description for e in tl.entries}
        for mem in mem_entries:
            desc = (mem.content or "")[:100]
            if desc and desc not in existing_descs:
                entry = TimelineEntry(
                    chapter_number=mem.chapter_number,
                    chapter_title="",
                    description=desc,
                    importance="high" if mem.importance >= 8 else "medium",
                    category="event",
                )
                tl.entries.append(entry)
                existing_descs.add(desc)
    except Exception as e:
        logger.warning("MemoryIndex 时间线补充失败: %s", e)

    # 按章节排序
    tl.entries.sort(key=lambda e: e.chapter_number)
    tl.milestone_count = sum(1 for e in tl.entries if e.category == "milestone")

    return tl
