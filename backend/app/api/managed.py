"""Track F · Managed Agents · /managed 路由

只放 Track F 命名空间下的端点。Phase 1 仅暴露审稿端点。
后续 Claude 在此基础上追加 events / book / review 等端点。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.services.inspiration.editor_mode import MuyuEditor, ReviewResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/managed", tags=["managed-agents"])


@router.post(
    "/books/{book_id}/chapter/{chapter_number}/review",
    response_model=ReviewResult,
    summary="墨语主编审稿（Track F · Week 1）",
)
async def review_chapter(
    book_id: str,
    chapter_number: int,
    db: Session = Depends(get_db),
) -> ReviewResult:
    """对指定章节进行全维度审稿，返回 ReviewResult。"""
    editor = MuyuEditor(db, event_store=None)
    try:
        return await editor.review_chapter(book_id, chapter_number)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("review_chapter 失败 book=%s chapter=%s", book_id, chapter_number)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"审稿失败: {e}",
        ) from e
