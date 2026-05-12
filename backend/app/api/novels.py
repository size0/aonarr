"""小说 CRUD API 路由"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.novel import Novel, Chapter
from app.schemas.novel import (
    NovelCreate, NovelUpdate, NovelDTO,
    ChapterCreate, ChapterUpdate, ChapterDTO,
)

router = APIRouter(prefix="/novels", tags=["novels"])


# ── Novel CRUD ────────────────────────────────────────────────────

@router.get("/", response_model=list[NovelDTO])
def list_novels(db: Session = Depends(get_db)):
    novels = db.query(Novel).order_by(Novel.updated_at.desc()).all()
    return [_novel_to_dto(n) for n in novels]


@router.post("/", response_model=NovelDTO, status_code=201)
def create_novel(body: NovelCreate, db: Session = Depends(get_db)):
    novel = Novel(
        id=str(uuid.uuid4()),
        title=body.title,
        genre=body.genre,
        tags=json.dumps(body.tags, ensure_ascii=False),
        synopsis=body.synopsis,
        premise=body.premise,
        world_setting=body.world_setting,
        target_word_count=body.target_word_count,
        target_chapter_count=body.target_chapter_count,
        words_per_chapter=body.words_per_chapter,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    return _novel_to_dto(novel)


@router.get("/{novel_id}", response_model=NovelDTO)
def get_novel(novel_id: str, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    return _novel_to_dto(novel)


@router.patch("/{novel_id}", response_model=NovelDTO)
def update_novel(novel_id: str, body: NovelUpdate, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    updates = body.model_dump(exclude_unset=True)
    if "tags" in updates:
        updates["tags"] = json.dumps(updates["tags"], ensure_ascii=False)
    for k, v in updates.items():
        setattr(novel, k, v)
    novel.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(novel)
    return _novel_to_dto(novel)


@router.delete("/{novel_id}", status_code=204)
def delete_novel(novel_id: str, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    db.delete(novel)
    db.commit()


# ── Chapter CRUD ──────────────────────────────────────────────────

@router.get("/{novel_id}/chapters", response_model=list[ChapterDTO])
def list_chapters(novel_id: str, db: Session = Depends(get_db)):
    chapters = db.query(Chapter).filter_by(novel_id=novel_id).order_by(Chapter.number).all()
    return [_chapter_to_dto(c) for c in chapters]


@router.post("/{novel_id}/chapters", response_model=ChapterDTO, status_code=201)
def create_chapter(novel_id: str, body: ChapterCreate, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    chapter = Chapter(
        id=str(uuid.uuid4()),
        novel_id=novel_id,
        number=body.number,
        title=body.title,
        content=body.content,
        word_count=len(body.content),
    )
    db.add(chapter)
    novel.chapter_count += 1
    novel.current_word_count += chapter.word_count
    db.commit()
    db.refresh(chapter)
    return _chapter_to_dto(chapter)


@router.get("/{novel_id}/chapters/{chapter_id}", response_model=ChapterDTO)
def get_chapter(novel_id: str, chapter_id: str, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter_by(id=chapter_id, novel_id=novel_id).first()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    return _chapter_to_dto(chapter)


@router.patch("/{novel_id}/chapters/{chapter_id}", response_model=ChapterDTO)
def update_chapter(novel_id: str, chapter_id: str, body: ChapterUpdate, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter_by(id=chapter_id, novel_id=novel_id).first()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    novel = db.query(Novel).filter_by(id=novel_id).first()
    old_word_count = chapter.word_count or 0
    if body.title is not None:
        chapter.title = body.title
    if body.content is not None:
        chapter.content = body.content
        chapter.word_count = len(body.content)
        if novel:
            novel.current_word_count += (chapter.word_count - old_word_count)
        # 正文变更 → 清空旧提取产物，标记下游待刷新
        chapter.summary = None
        chapter.events = None
        chapter.entities = None
        chapter.foreshadows = None
        chapter.tension_score = None
        chapter.status = "pipeline_pending"
    if body.status is not None:
        chapter.status = body.status
    chapter.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(chapter)
    return _chapter_to_dto(chapter)


# ── Character CRUD 已迁移到 characters.py（支持 relationships / first_appearance）──


# ── 转换工具 ──────────────────────────────────────────────────────

def _novel_to_dto(n: Novel) -> NovelDTO:
    return NovelDTO(
        id=n.id, title=n.title, genre=n.genre,
        tags=json.loads(n.tags) if n.tags else [],
        synopsis=n.synopsis, premise=n.premise,
        world_setting=n.world_setting,
        target_word_count=n.target_word_count,
        target_chapter_count=n.target_chapter_count,
        words_per_chapter=n.words_per_chapter,
        current_word_count=n.current_word_count,
        chapter_count=n.chapter_count,
        status=n.status,
        auto_approve_mode=n.auto_approve_mode,
        created_at=n.created_at, updated_at=n.updated_at,
    )


def _chapter_to_dto(c: Chapter) -> ChapterDTO:
    return ChapterDTO(
        id=c.id, novel_id=c.novel_id, number=c.number,
        title=c.title, content=c.content, summary=c.summary,
        word_count=c.word_count, status=c.status,
        tension_score=c.tension_score, model_used=c.model_used,
        created_at=c.created_at, updated_at=c.updated_at,
    )


