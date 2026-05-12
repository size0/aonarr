"""世界观条目 CRUD API"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.novel import Novel, WorldItem

router = APIRouter(tags=["world"])
logger = logging.getLogger(__name__)


# ── Schemas ──────────────────────────────────────────────────

class WorldItemCreate(BaseModel):
    category: str  # location / faction / item / rule / history
    name: str
    description: str = ""
    properties: dict = {}


class WorldItemUpdate(BaseModel):
    category: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[dict] = None


def _serialize(item: WorldItem) -> dict:
    return {
        "id": item.id,
        "novel_id": item.novel_id,
        "category": item.category,
        "name": item.name,
        "description": item.description,
        "properties": json.loads(item.properties) if item.properties else {},
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


# ── Routes ───────────────────────────────────────────────────

@router.get("/novels/{novel_id}/world")
def list_world_items(novel_id: str, category: str | None = None, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    q = db.query(WorldItem).filter_by(novel_id=novel_id)
    if category:
        q = q.filter(WorldItem.category == category)
    items = q.order_by(WorldItem.created_at.desc()).all()
    return [_serialize(i) for i in items]


@router.post("/novels/{novel_id}/world", status_code=201)
def create_world_item(novel_id: str, body: WorldItemCreate, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    item = WorldItem(
        novel_id=novel_id,
        category=body.category,
        name=body.name,
        description=body.description,
        properties=json.dumps(body.properties, ensure_ascii=False),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.get("/novels/{novel_id}/world/{item_id}")
def get_world_item(novel_id: str, item_id: str, db: Session = Depends(get_db)):
    item = db.query(WorldItem).filter_by(id=item_id, novel_id=novel_id).first()
    if not item:
        raise HTTPException(404, "世界观条目不存在")
    return _serialize(item)


@router.patch("/novels/{novel_id}/world/{item_id}")
def update_world_item(novel_id: str, item_id: str, body: WorldItemUpdate, db: Session = Depends(get_db)):
    item = db.query(WorldItem).filter_by(id=item_id, novel_id=novel_id).first()
    if not item:
        raise HTTPException(404, "世界观条目不存在")
    if body.category is not None:
        item.category = body.category
    if body.name is not None:
        item.name = body.name
    if body.description is not None:
        item.description = body.description
    if body.properties is not None:
        item.properties = json.dumps(body.properties, ensure_ascii=False)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.delete("/novels/{novel_id}/world/{item_id}", status_code=204)
def delete_world_item(novel_id: str, item_id: str, db: Session = Depends(get_db)):
    count = db.query(WorldItem).filter_by(id=item_id, novel_id=novel_id).delete()
    if not count:
        raise HTTPException(404, "世界观条目不存在")
    db.commit()


# ═══════════════════════════════════════════════════════════════
# 时间线 — 从章节 events / MemoryIndex 自动聚合
# ═══════════════════════════════════════════════════════════════

@router.get("/novels/{novel_id}/timeline")
def get_timeline(
    novel_id: str,
    importance: str | None = None,
    db: Session = Depends(get_db),
):
    """获取全书时间线（从章节元数据自动聚合）"""
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")

    from app.services.world.timeline import build_timeline
    tl = build_timeline(db, novel_id, importance_filter=importance)
    return tl.to_dict()


# ═══════════════════════════════════════════════════════════════
# 百科全书 — 从 characters / world / entities 自动聚合
# ═══════════════════════════════════════════════════════════════

@router.get("/novels/{novel_id}/encyclopedia")
def get_encyclopedia(novel_id: str, db: Session = Depends(get_db)):
    """获取全书百科（角色+世界观+提及实体 自动聚合）"""
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")

    from app.services.world.encyclopedia import build_encyclopedia
    enc = build_encyclopedia(db, novel_id)
    return enc.to_dict()


# ═══════════════════════════════════════════════════════════════
# 世界地图批量重建 — 从已有章节 Observer facts 回填 WorldItem
# ═══════════════════════════════════════════════════════════════

@router.post("/novels/{novel_id}/world/rebuild")
async def rebuild_world(novel_id: str, db: Session = Depends(get_db)):
    """从已有章节批量重建世界地图（调 Observer LLM 提取 facts）"""
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")

    from app.models.novel import Chapter
    from app.services.creation.observer import Observer
    from app.services.world.world_enricher import enrich_world_from_facts, enrich_world_from_events

    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .filter(Chapter.content.isnot(None), Chapter.content != "")
        .order_by(Chapter.number)
        .all()
    )
    if not chapters:
        raise HTTPException(400, "没有可用章节")

    observer = Observer(db)
    total = {"created": 0, "updated": 0, "chapters": []}

    for ch in chapters:
        ch_result = {"chapter": ch.number, "created": 0, "updated": 0}
        try:
            # Observer 提取 facts
            facts = await observer.extract_facts(novel_id, ch.number, ch.content)
            fact_r = enrich_world_from_facts(db, novel_id, ch.number, facts)
            ch_result["created"] += fact_r["created"]
            ch_result["updated"] += fact_r["updated"]
        except Exception as e:
            ch_result["error"] = str(e)[:100]

        # 从 events 补充
        if ch.events:
            try:
                events = json.loads(ch.events) if isinstance(ch.events, str) else ch.events
                ev_r = enrich_world_from_events(db, novel_id, ch.number, events)
                ch_result["updated"] += ev_r["updated"]
            except Exception:
                pass

        total["created"] += ch_result["created"]
        total["updated"] += ch_result["updated"]
        total["chapters"].append(ch_result)

    return {
        "novel_id": novel_id,
        "chapters_processed": len(chapters),
        "world_items_created": total["created"],
        "world_items_updated": total["updated"],
        "details": total["chapters"],
    }
