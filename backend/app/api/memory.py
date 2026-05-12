"""记忆与上下文 API 路由"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.novel import Novel, Chapter

router = APIRouter(prefix="/memory", tags=["memory"])
logger = logging.getLogger(__name__)


def _get_novel_or_404(novel_id: str, db: Session) -> Novel:
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    return novel


def _get_chapter_or_404(novel_id: str, number: int, db: Session) -> Chapter:
    ch = db.query(Chapter).filter_by(novel_id=novel_id, number=number).first()
    if not ch:
        raise HTTPException(404, f"章节 {number} 不存在")
    return ch


# ── 分层记忆编译 ──────────────────────────────────────────────────

@router.get("/{novel_id}/compiled/{chapter_number}")
def get_compiled_memory(novel_id: str, chapter_number: int, db: Session = Depends(get_db)):
    """获取指定章节的三层编译记忆"""
    _get_novel_or_404(novel_id, db)

    from app.services.creation.memory_compiler import MemoryCompiler
    compiler = MemoryCompiler(db)
    result = compiler.compile(novel_id, chapter_number)
    return result.to_dict()


# ── 记忆索引建立 ──────────────────────────────────────────────────

@router.post("/{novel_id}/chapters/{number}/index")
def index_chapter_memory(novel_id: str, number: int, db: Session = Depends(get_db)):
    """为指定章节建立记忆索引"""
    _get_novel_or_404(novel_id, db)
    chapter = _get_chapter_or_404(novel_id, number, db)

    from app.services.creation.memory_compiler import MemoryRetriever
    retriever = MemoryRetriever(db)
    count = retriever.index_chapter(novel_id, number, chapter)
    db.commit()
    return {"novel_id": novel_id, "chapter_number": number, "entries_indexed": count}


@router.post("/{novel_id}/index-all")
def index_all_chapters(novel_id: str, db: Session = Depends(get_db)):
    """为全书所有章节建立记忆索引"""
    _get_novel_or_404(novel_id, db)

    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .order_by(Chapter.number.asc())
        .all()
    )

    from app.services.creation.memory_compiler import MemoryRetriever
    retriever = MemoryRetriever(db)
    total = 0
    for ch in chapters:
        total += retriever.index_chapter(novel_id, ch.number, ch)
    db.commit()
    return {"novel_id": novel_id, "chapters_indexed": len(chapters), "total_entries": total}


# ── 记忆检索 ──────────────────────────────────────────────────────

@router.get("/{novel_id}/retrieve")
def retrieve_memory(
    novel_id: str,
    q: str = Query("", description="关键词查询"),
    types: str = Query("", description="条目类型，逗号分隔: fact,foreshadow,summary,event,character_change"),
    chapter_start: int = Query(0, description="章节范围起始"),
    chapter_end: int = Query(0, description="章节范围结束"),
    max_results: int = Query(20, ge=1, le=100),
    min_importance: int = Query(1, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """按相关性检索历史记忆"""
    _get_novel_or_404(novel_id, db)

    from app.services.creation.memory_compiler import MemoryRetriever
    retriever = MemoryRetriever(db)

    entry_types = [t.strip() for t in types.split(",") if t.strip()] if types else None
    chapter_range = (chapter_start, chapter_end) if chapter_start and chapter_end else None

    results = retriever.retrieve(
        novel_id,
        query=q,
        entry_types=entry_types,
        chapter_range=chapter_range,
        max_results=max_results,
        min_importance=min_importance,
    )
    return {"novel_id": novel_id, "query": q, "count": len(results), "entries": results}


# ── 缓存统计 ──────────────────────────────────────────────────────

@router.get("/{novel_id}/cache-stats")
def cache_stats(novel_id: str, db: Session = Depends(get_db)):
    """查看记忆缓存统计"""
    _get_novel_or_404(novel_id, db)

    from app.models.novel import MemoryCache, MemoryIndex
    caches = db.query(MemoryCache).filter_by(novel_id=novel_id).all()
    index_count = db.query(MemoryIndex).filter_by(novel_id=novel_id).count()

    cache_entries = []
    total_tokens = 0
    for c in caches:
        cache_entries.append({
            "layer": c.layer,
            "scope_key": c.scope_key,
            "sha256": c.sha256[:12] + "...",
            "token_count": c.token_count,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })
        total_tokens += c.token_count

    return {
        "novel_id": novel_id,
        "cache_count": len(caches),
        "cache_total_tokens": total_tokens,
        "index_count": index_count,
        "caches": cache_entries,
    }
