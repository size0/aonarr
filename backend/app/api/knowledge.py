"""知识图谱三元组 API + 题材 Agent API"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.services.world.knowledge_graph import KnowledgeGraphService
from app.services.creation.theme.theme_registry import get_theme_registry

router = APIRouter(tags=["knowledge"])


# ==================== Schemas ====================

class TripleCreate(BaseModel):
    subject_id: str
    predicate: str
    object_id: str
    subject_type: str = "character"
    object_type: str = "character"
    description: str = ""
    confidence: float = 1.0
    source_chapter: Optional[int] = None

class TripleUpdate(BaseModel):
    predicate: Optional[str] = None
    description: Optional[str] = None
    confidence: Optional[float] = None
    is_active: Optional[bool] = None

class TripleOut(BaseModel):
    id: str
    subject_id: str
    subject_type: str
    predicate: str
    object_id: str
    object_type: str
    description: str
    confidence: float
    source_type: str
    source_chapter: Optional[int]
    first_appearance: Optional[int]
    related_chapters: str
    is_active: bool

    class Config:
        from_attributes = True


# ==================== Triple CRUD ====================

@router.get("/novels/{novel_id}/knowledge-graph")
def list_triples(
    novel_id: str,
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    """获取小说的所有知识三元组"""
    kg = KnowledgeGraphService(db)
    triples = kg.get_by_novel(novel_id, active_only=active_only)
    return [TripleOut.model_validate(t) for t in triples]


@router.get("/novels/{novel_id}/knowledge-graph/entity/{entity_name}")
def get_entity_triples(
    novel_id: str,
    entity_name: str,
    db: Session = Depends(get_db),
):
    """获取实体的一度关系网络"""
    kg = KnowledgeGraphService(db)
    triples = kg.get_by_entity(novel_id, entity_name)
    return [TripleOut.model_validate(t) for t in triples]


@router.get("/novels/{novel_id}/knowledge-graph/stats")
def get_graph_stats(novel_id: str, db: Session = Depends(get_db)):
    """获取知识图谱统计"""
    kg = KnowledgeGraphService(db)
    return kg.get_stats(novel_id)


@router.post("/novels/{novel_id}/knowledge-graph")
def create_triple(
    novel_id: str,
    body: TripleCreate,
    db: Session = Depends(get_db),
):
    """手动创建三元组"""
    kg = KnowledgeGraphService(db)
    t = kg.create_triple(
        novel_id=novel_id,
        subject_id=body.subject_id,
        predicate=body.predicate,
        object_id=body.object_id,
        subject_type=body.subject_type,
        object_type=body.object_type,
        description=body.description,
        confidence=body.confidence,
        source_type="manual",
        source_chapter=body.source_chapter,
    )
    db.commit()
    return TripleOut.model_validate(t)


@router.patch("/novels/{novel_id}/knowledge-graph/{triple_id}")
def update_triple(
    novel_id: str,
    triple_id: str,
    body: TripleUpdate,
    db: Session = Depends(get_db),
):
    """更新三元组"""
    from app.models.novel import KnowledgeTriple
    t = db.query(KnowledgeTriple).filter_by(id=triple_id, novel_id=novel_id).first()
    if not t:
        raise HTTPException(404, "Triple not found")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(t, key, val)
    db.commit()
    return TripleOut.model_validate(t)


@router.delete("/novels/{novel_id}/knowledge-graph/{triple_id}")
def delete_triple(
    novel_id: str,
    triple_id: str,
    hard: bool = False,
    db: Session = Depends(get_db),
):
    """删除三元组（默认软删除）"""
    kg = KnowledgeGraphService(db)
    ok = kg.hard_delete(triple_id) if hard else kg.delete_triple(triple_id)
    if not ok:
        raise HTTPException(404, "Triple not found")
    db.commit()
    return {"deleted": triple_id}


@router.post("/novels/{novel_id}/knowledge-graph/rebuild")
def rebuild_triples(novel_id: str, db: Session = Depends(get_db)):
    """从已有章节批量重建知识图谱三元组"""
    from app.models.novel import Chapter
    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .filter(Chapter.events != "[]", Chapter.events != "", Chapter.events.isnot(None))
        .order_by(Chapter.number)
        .all()
    )
    kg = KnowledgeGraphService(db)
    total = 0
    for ch in chapters:
        # 尝试从 Observer facts 或章节 entities/events 重建
        import json
        facts_by_cat: dict[str, list] = {}
        # 从章节 entities 构建 characters 事实
        if ch.entities:
            try:
                entities = json.loads(ch.entities) if isinstance(ch.entities, str) else ch.entities
                facts_by_cat["characters"] = [
                    {"name": e.get("name", ""), "trait": e.get("action", "")}
                    for e in entities if isinstance(e, dict)
                ]
            except (json.JSONDecodeError, TypeError):
                pass
        # 从章节 events 构建关系
        if ch.events:
            try:
                events = json.loads(ch.events) if isinstance(ch.events, str) else ch.events
                for ev in events:
                    if isinstance(ev, dict) and ev.get("involved_characters"):
                        chars = ev["involved_characters"]
                        if isinstance(chars, list) and len(chars) >= 2:
                            facts_by_cat.setdefault("relations", []).append({
                                "subject": chars[0],
                                "object": chars[1],
                                "type": ev.get("description", "互动")[:30],
                            })
            except (json.JSONDecodeError, TypeError):
                pass

        if facts_by_cat:
            total += kg.extract_from_observer_facts(novel_id, ch.number, facts_by_cat)

    db.commit()
    return {"rebuilt": total, "chapters_processed": len(chapters)}


# ==================== Theme Agent API ====================

@router.get("/theme-agents")
def list_theme_agents():
    """列出所有已注册的题材 Agent"""
    registry = get_theme_registry()
    return registry.list_genres()


@router.get("/theme-agents/{genre_key}")
def get_theme_agent_detail(genre_key: str):
    """获取题材 Agent 详细信息"""
    registry = get_theme_registry()
    agent = registry.get(genre_key)
    if not agent:
        raise HTTPException(404, f"Theme agent '{genre_key}' not found")
    return {
        "key": agent.genre_key,
        "name": agent.genre_name,
        "description": agent.description,
        "system_persona": agent.get_system_persona(),
        "writing_rules": agent.get_writing_rules(),
        "beat_templates": [
            {"keywords": bt.keywords, "priority": bt.priority, "beats_count": len(bt.beats)}
            for bt in agent.get_beat_templates()
        ],
        "custom_focus_keys": list(agent.get_custom_focus_instructions().keys()),
    }


@router.get("/theme-agents/{genre_key}/directives")
def get_theme_directives(
    genre_key: str,
    novel_id: str = "",
    chapter_number: int = 1,
    outline: str = "",
):
    """获取题材上下文指令"""
    registry = get_theme_registry()
    agent = registry.get(genre_key)
    if not agent:
        raise HTTPException(404, f"Theme agent '{genre_key}' not found")
    directives = agent.get_context_directives(novel_id, chapter_number, outline)
    return {
        "text": directives.to_context_text(),
        "world_rules": directives.world_rules,
        "atmosphere": directives.atmosphere,
        "taboos": directives.taboos,
        "tropes_to_use": directives.tropes_to_use,
        "tropes_to_avoid": directives.tropes_to_avoid,
    }
