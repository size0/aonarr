"""百科全书聚合器 — 从 Character / WorldItem / 章节 entities 自动构建百科

数据来源：
1. Character 表 — 角色档案
2. WorldItem 表 — 世界观条目（力量体系/地点/势力等）
3. Chapter.entities JSON — 每章提取的出场角色行为
4. MemoryIndex — 高重要性记忆条目

输出：分类索引的百科条目列表。
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.novel import Novel, Character, WorldItem, Chapter

logger = logging.getLogger(__name__)


@dataclass
class EncyclopediaEntry:
    """百科条目"""
    name: str
    category: str            # character / location / faction / item / power / concept
    description: str = ""
    first_chapter: int = 0
    last_chapter: int = 0
    mention_count: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description[:300],
            "first_chapter": self.first_chapter,
            "last_chapter": self.last_chapter,
            "mentions": self.mention_count,
            "details": self.details,
        }


@dataclass
class Encyclopedia:
    """全书百科"""
    novel_id: str
    novel_title: str = ""
    entries: list[EncyclopediaEntry] = field(default_factory=list)
    categories: dict = field(default_factory=dict)  # category → count

    def to_dict(self) -> dict:
        return {
            "novel_id": self.novel_id,
            "novel_title": self.novel_title,
            "total_entries": len(self.entries),
            "categories": self.categories,
            "entries": [e.to_dict() for e in self.entries],
        }


def build_encyclopedia(db: Session, novel_id: str) -> Encyclopedia:
    """从 DB 中聚合构建全书百科"""
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        return Encyclopedia(novel_id=novel_id)

    enc = Encyclopedia(novel_id=novel_id, novel_title=novel.title)
    entry_map: dict[str, EncyclopediaEntry] = {}

    # 1. Characters → 百科条目
    characters = db.query(Character).filter_by(novel_id=novel_id).all()
    for ch in characters:
        desc = ch.description or ""
        rels = []
        try:
            rels = json.loads(ch.relationships) if ch.relationships else []
        except (json.JSONDecodeError, TypeError):
            pass
        traits = []
        try:
            traits = json.loads(ch.traits) if ch.traits else []
        except (json.JSONDecodeError, TypeError):
            pass

        entry = EncyclopediaEntry(
            name=ch.name,
            category="character",
            description=desc.split("\n")[0][:300] if desc else "",
            first_chapter=ch.first_appearance or 0,
            details={
                "role": ch.role,
                "traits": traits[:5],
                "relationships": [
                    {"target": r.get("target", ""), "description": r.get("description", "")[:50]}
                    for r in rels[:8] if isinstance(r, dict)
                ],
            },
        )
        entry_map[ch.name] = entry

    # 2. WorldItems → 百科条目
    world_items = db.query(WorldItem).filter_by(novel_id=novel_id).all()
    for wi in world_items:
        props = {}
        try:
            props = json.loads(wi.properties) if wi.properties else {}
        except (json.JSONDecodeError, TypeError):
            pass

        entry = EncyclopediaEntry(
            name=wi.name,
            category=wi.category or "concept",
            description=wi.description[:300] if wi.description else "",
            details=props,
        )
        entry_map[wi.name] = entry

    # 3. 从章节 entities 补充提及频率和出场范围
    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .order_by(Chapter.number)
        .all()
    )
    mention_counts: dict[str, int] = defaultdict(int)
    first_seen: dict[str, int] = {}
    last_seen: dict[str, int] = {}

    for ch in chapters:
        # 从 entities JSON 提取
        if ch.entities:
            try:
                entities = json.loads(ch.entities) if isinstance(ch.entities, str) else ch.entities
                for ent in entities:
                    if not isinstance(ent, dict):
                        continue
                    name = ent.get("name", "")
                    if not name:
                        continue
                    mention_counts[name] += 1
                    if name not in first_seen:
                        first_seen[name] = ch.number
                    last_seen[name] = ch.number

                    if name not in entry_map:
                        action = ent.get("action", "")
                        entry_map[name] = EncyclopediaEntry(
                            name=name,
                            category="character",
                            description=action[:100] if action else "",
                            first_chapter=ch.number,
                        )
            except (json.JSONDecodeError, TypeError):
                pass

        # 从 events JSON 的 involved_characters 提取提及
        if ch.events:
            try:
                events = json.loads(ch.events) if isinstance(ch.events, str) else ch.events
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    involved = ev.get("involved_characters", [])
                    if not isinstance(involved, list):
                        continue
                    for name in involved:
                        if not name or not isinstance(name, str):
                            continue
                        mention_counts[name] += 1
                        if name not in first_seen:
                            first_seen[name] = ch.number
                        last_seen[name] = ch.number
                        if name not in entry_map:
                            entry_map[name] = EncyclopediaEntry(
                                name=name,
                                category="character",
                                description=ev.get("description", "")[:100],
                                first_chapter=ch.number,
                            )
            except (json.JSONDecodeError, TypeError):
                pass

    # 合并提及数据
    for name, entry in entry_map.items():
        entry.mention_count = mention_counts.get(name, 0)
        if name in first_seen and (entry.first_chapter == 0 or first_seen[name] < entry.first_chapter):
            entry.first_chapter = first_seen[name]
        if name in last_seen:
            entry.last_chapter = last_seen[name]

    # 排序：角色优先，然后按提及次数降序
    category_order = {"character": 0, "power_system": 1, "location": 2, "faction": 3}
    entries = sorted(
        entry_map.values(),
        key=lambda e: (category_order.get(e.category, 5), -e.mention_count),
    )
    enc.entries = entries

    # 分类统计
    cat_counts: dict[str, int] = defaultdict(int)
    for e in entries:
        cat_counts[e.category] += 1
    enc.categories = dict(cat_counts)

    return enc
