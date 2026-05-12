"""角色 CRUD API"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.novel import Novel, Character, Chapter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/novels/{novel_id}/characters", tags=["characters"])


# ── Schemas ─────────────────────────────────────────────────────

class CharacterCreate(BaseModel):
    name: str
    role: str = "supporting"  # protagonist / antagonist / supporting
    description: str = ""
    traits: list[str] = []
    relationships: list[dict] = []
    first_appearance: int = 0


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    traits: Optional[list[str]] = None
    relationships: Optional[list[dict]] = None
    first_appearance: Optional[int] = None


# ── CRUD ────────────────────────────────────────────────────────

@router.get("")
def list_characters(novel_id: str, db: Session = Depends(get_db)):
    """列出小说的所有角色"""
    _ensure_novel(novel_id, db)
    rows = (
        db.query(Character)
        .filter_by(novel_id=novel_id)
        .order_by(Character.first_appearance, Character.created_at)
        .all()
    )
    return [_to_dict(r) for r in rows]


@router.get("/{character_id}")
def get_character(novel_id: str, character_id: str, db: Session = Depends(get_db)):
    """获取单个角色详情"""
    row = db.query(Character).filter_by(id=character_id, novel_id=novel_id).first()
    if not row:
        raise HTTPException(404, "角色不存在")
    return _to_dict(row)


@router.post("", status_code=201)
def create_character(novel_id: str, body: CharacterCreate, db: Session = Depends(get_db)):
    """创建角色"""
    _ensure_novel(novel_id, db)

    valid_roles = {"protagonist", "antagonist", "supporting"}
    if body.role not in valid_roles:
        raise HTTPException(400, f"角色类型必须为: {valid_roles}")

    row = Character(
        novel_id=novel_id,
        name=body.name,
        role=body.role,
        description=body.description,
        traits=json.dumps(body.traits, ensure_ascii=False),
        relationships=json.dumps(body.relationships, ensure_ascii=False),
        first_appearance=body.first_appearance,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.patch("/{character_id}")
def update_character(
    novel_id: str, character_id: str, body: CharacterUpdate, db: Session = Depends(get_db),
):
    """更新角色"""
    row = db.query(Character).filter_by(id=character_id, novel_id=novel_id).first()
    if not row:
        raise HTTPException(404, "角色不存在")

    if body.name is not None:
        row.name = body.name
    if body.role is not None:
        row.role = body.role
    if body.description is not None:
        row.description = body.description
    if body.traits is not None:
        row.traits = json.dumps(body.traits, ensure_ascii=False)
    if body.relationships is not None:
        row.relationships = json.dumps(body.relationships, ensure_ascii=False)
    if body.first_appearance is not None:
        row.first_appearance = body.first_appearance

    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.delete("/{character_id}")
def delete_character(novel_id: str, character_id: str, db: Session = Depends(get_db)):
    """删除角色"""
    count = db.query(Character).filter_by(id=character_id, novel_id=novel_id).delete()
    db.commit()
    if count == 0:
        raise HTTPException(404, "角色不存在")
    return {"ok": True}


# ── 批量回填关系 ─────────────────────────────────────────────────

@router.post("/rebuild-relations")
async def rebuild_relations(novel_id: str, db: Session = Depends(get_db)):
    """从已有章节批量重新提取并回填角色关系（适用于历史数据修复）"""
    _ensure_novel(novel_id, db)

    from app.services.creation.character_state_updater import CharacterStateUpdater
    from app.services.creation.observer import Observer

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
    updater = CharacterStateUpdater(db)
    total_relations = 0
    chapter_results = []

    for ch in chapters:
        try:
            facts = await observer.extract_facts(novel_id, ch.number, ch.content)
            relation_facts = [f for f in facts if f.get("category") == "relations"]

            # 保底：从 entities 提取
            if not relation_facts and ch.entities:
                try:
                    entities = json.loads(ch.entities) if isinstance(ch.entities, str) else ch.entities
                    entity_names = [e.get("name", "") for e in entities if isinstance(e, dict) and e.get("name")]
                    for ent in entities:
                        if not isinstance(ent, dict):
                            continue
                        name = ent.get("name", "")
                        action = ent.get("action", "")
                        state_change = ent.get("state_change", "")
                        if not name:
                            continue
                        for other in entity_names:
                            if other != name and other in (action + state_change):
                                facts.append({
                                    "category": "relations",
                                    "subject": name,
                                    "predicate": action[:30] if action else "互动",
                                    "object": other,
                                    "detail": state_change[:30] if state_change else action[:30],
                                    "confidence": 0.75,
                                })
                except (json.JSONDecodeError, TypeError):
                    pass

            result = updater.update_from_facts(novel_id, ch.number, facts)
            rels_updated = result.get("relations_updated", 0)
            total_relations += rels_updated
            chapter_results.append({
                "chapter": ch.number,
                "facts": len(facts),
                "relations": sum(1 for f in facts if f.get("category") == "relations"),
                "updated": rels_updated,
            })
        except Exception as e:
            chapter_results.append({
                "chapter": ch.number,
                "error": str(e)[:100],
            })

    return {
        "novel_id": novel_id,
        "chapters_processed": len(chapters),
        "total_relations_updated": total_relations,
        "details": chapter_results,
    }


# ── helpers ─────────────────────────────────────────────────────

def _ensure_novel(novel_id: str, db: Session):
    if not db.query(Novel).filter_by(id=novel_id).first():
        raise HTTPException(404, "小说不存在")


def _to_dict(row: Character) -> dict:
    def _safe_json(s: str) -> list:
        try:
            return json.loads(s) if s else []
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "id": row.id,
        "novel_id": row.novel_id,
        "name": row.name,
        "role": row.role,
        "description": row.description,
        "traits": _safe_json(row.traits),
        "relationships": _safe_json(row.relationships),
        "first_appearance": row.first_appearance,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
