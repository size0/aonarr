"""世界地图自动增长器 — 从 Observer facts 自动创建/更新 WorldItem

Observer 的 9 类事实中，以下类别与世界地图相关：
- locations  → WorldItem(category='location')
- resources  → WorldItem(category='item')
- physics    → WorldItem(category='power_system')

增长逻辑：
1. 从 Observer facts 中筛选 locations/resources/physics
2. 查找已有 WorldItem，如果名称匹配则追加描述
3. 如果不存在则创建新条目
4. 也可从 Chapter.events 中提取地点信息
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.novel import Chapter, WorldItem

logger = logging.getLogger(__name__)

# Observer fact category → WorldItem category 映射
_CATEGORY_MAP = {
    "locations": "location",
    "resources": "item",
    "physics": "power_system",
}


def enrich_world_from_facts(
    db: Session,
    novel_id: str,
    chapter_number: int,
    facts: list[dict],
) -> dict:
    """从 Observer 提取的 facts 中自动创建/更新 WorldItem

    Returns:
        {"created": int, "updated": int, "items": [...]}
    """
    result = {"created": 0, "updated": 0, "items": []}

    # 筛选世界相关 facts
    world_facts = [
        f for f in facts
        if isinstance(f, dict) and f.get("category") in _CATEGORY_MAP
    ]
    if not world_facts:
        return result

    # 加载已有 WorldItem 索引
    existing = db.query(WorldItem).filter_by(novel_id=novel_id).all()
    name_index: dict[str, WorldItem] = {}
    for item in existing:
        name_index[item.name.strip().lower()] = item

    for fact in world_facts:
        category = _CATEGORY_MAP[fact["category"]]
        name = (fact.get("subject") or "").strip()
        if not name or len(name) < 2:
            continue

        detail = fact.get("detail", "") or fact.get("predicate", "")
        obj = fact.get("object", "")
        description = f"{detail}"
        if obj:
            description += f"（{obj}）"

        key = name.lower()
        if key in name_index:
            # 更新已有条目：追加描述
            item = name_index[key]
            old_desc = item.description or ""
            # 避免重复追加
            if description and description not in old_desc:
                item.description = (old_desc + f"\n[第{chapter_number}章] {description}").strip()
                # 更新 properties 中的 last_chapter
                try:
                    props = json.loads(item.properties) if item.properties else {}
                except (json.JSONDecodeError, TypeError):
                    props = {}
                props["last_chapter"] = chapter_number
                if "mention_chapters" not in props:
                    props["mention_chapters"] = []
                if chapter_number not in props["mention_chapters"]:
                    props["mention_chapters"].append(chapter_number)
                item.properties = json.dumps(props, ensure_ascii=False)
                result["updated"] += 1
                result["items"].append({"name": name, "action": "updated"})
        else:
            # 创建新条目
            new_item = WorldItem(
                novel_id=novel_id,
                category=category,
                name=name,
                description=f"[第{chapter_number}章] {description}",
                properties=json.dumps({
                    "first_chapter": chapter_number,
                    "last_chapter": chapter_number,
                    "mention_chapters": [chapter_number],
                    "source": "auto_observer",
                }, ensure_ascii=False),
            )
            db.add(new_item)
            db.flush()
            name_index[key] = new_item
            result["created"] += 1
            result["items"].append({"name": name, "action": "created"})

    db.commit()
    return result


def enrich_world_from_events(
    db: Session,
    novel_id: str,
    chapter_number: int,
    events: list[dict],
) -> dict:
    """从 Chapter.events 中提取地点/物品信息补充 WorldItem

    events 格式: [{"type": "...", "description": "...", "involved_characters": [...]}]
    """
    result = {"created": 0, "updated": 0}

    if not events:
        return result

    existing = db.query(WorldItem).filter_by(novel_id=novel_id).all()
    name_index = {item.name.strip().lower(): item for item in existing}

    # 从事件类型中识别地点/物品相关
    location_keywords = {"地点", "场景", "到达", "进入", "离开", "前往", "抵达"}  # noqa: F841
    item_keywords = {"获得", "物品", "道具", "武器", "功法", "秘籍", "丹药", "装备"}  # noqa: F841

    for ev in events:
        if not isinstance(ev, dict):
            continue
        desc = ev.get("description", "")
        ev_type = ev.get("type", "")  # noqa: F841

        # 尝试提取事件中提到的关键名词（已有的 WorldItem 名称匹配）
        for name, item in list(name_index.items()):
            if item.name in desc:
                try:
                    props = json.loads(item.properties) if item.properties else {}
                except (json.JSONDecodeError, TypeError):
                    props = {}
                if "mention_chapters" not in props:
                    props["mention_chapters"] = []
                if chapter_number not in props["mention_chapters"]:
                    props["mention_chapters"].append(chapter_number)
                    props["last_chapter"] = chapter_number
                    item.properties = json.dumps(props, ensure_ascii=False)
                    result["updated"] += 1

    if result["updated"] > 0:
        db.commit()

    return result


def rebuild_world_from_chapters(
    db: Session,
    novel_id: str,
    observer_facts_by_chapter: Optional[dict[int, list[dict]]] = None,
) -> dict:
    """从所有章节批量重建世界地图

    如果不提供 observer_facts_by_chapter，则从 events 中提取。
    """
    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .filter(Chapter.content.isnot(None), Chapter.content != "")
        .order_by(Chapter.number)
        .all()
    )

    total = {"created": 0, "updated": 0, "chapters_processed": 0}

    for ch in chapters:
        # 从 events 中更新
        if ch.events:
            try:
                events = json.loads(ch.events) if isinstance(ch.events, str) else ch.events
                ev_result = enrich_world_from_events(db, novel_id, ch.number, events)
                total["updated"] += ev_result["updated"]
            except (json.JSONDecodeError, TypeError):
                pass

        # 如果有 observer facts 则一并使用
        if observer_facts_by_chapter and ch.number in observer_facts_by_chapter:
            facts = observer_facts_by_chapter[ch.number]
            fact_result = enrich_world_from_facts(db, novel_id, ch.number, facts)
            total["created"] += fact_result["created"]
            total["updated"] += fact_result["updated"]

        total["chapters_processed"] += 1

    return total
