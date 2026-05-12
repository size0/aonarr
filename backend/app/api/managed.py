"""Track F · Managed Agents · /managed 路由

只放 Track F 命名空间下的端点。
- review_chapter   Claude-A (Week 1)
- get_events       Phase 1 wrap (Coordinator)
- daemon 控制      Claude-C (Week 3)
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import SessionLocal, get_db
from app.models.book_state import BookState
from app.services.agents import DaemonPool, get_default_pool
from app.services.events.event_store import EventStore
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
    session_id: str | None = Query(default=None, description="可选事件 session_id，传入则写事件"),
    db: Session = Depends(get_db),
) -> ReviewResult:
    """对指定章节进行全维度审稿，返回 ReviewResult。

    - 不传 ``session_id``: 不写事件流，仅返回结果（与 Week 1 默认行为一致）
    - 传 ``session_id``: 经 ``EventStore`` 写入 ``review_started`` / ``review_completed`` /
      ``hard_rule_violation`` 等事件
    """
    event_store = EventStore(db) if session_id else None
    editor = MuyuEditor(db, event_store=event_store)
    try:
        return await editor.review_chapter(book_id, chapter_number, session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("review_chapter 失败 book=%s chapter=%s", book_id, chapter_number)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"审稿失败: {e}",
        ) from e


@router.get(
    "/books/{book_id}/events",
    summary="读取本书事件流（Phase 1 验收 API）",
)
async def get_events(
    book_id: str,
    session_id: str = Query(..., description="session_id"),
    from_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    types: str | None = Query(default=None, description="逗号分隔的 event_type 白名单"),
    chapter_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """返回某 book / session 的事件切片，按 seq 升序。

    Response 形如::

        {
            "book_id": "...",
            "session_id": "...",
            "count": 12,
            "events": [ {id, seq, event_type, actor, payload, ...}, ... ]
        }
    """
    store = EventStore(db)
    type_filter = [t.strip() for t in types.split(",") if t.strip()] if types else None
    try:
        events = await store.get_events(
            book_id=book_id,
            session_id=session_id,
            from_seq=from_seq,
            limit=limit,
            types=type_filter,
            chapter_number=chapter_number,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("get_events 失败 book=%s session=%s", book_id, session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取事件失败: {e}",
        ) from e

    return {
        "book_id": book_id,
        "session_id": session_id,
        "count": len(events),
        "events": [e.to_dict() for e in events],
    }


@router.post(
    "/books/{book_id}/sessions",
    summary="创建新 session（用于事件流隔离）",
)
async def create_session(
    book_id: str,
    branch_name: str = Query(default="main"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """创建顶层（非 fork）session。返回 ``{session_id}``。"""
    store = EventStore(db)
    try:
        sid = await store.create_session(book_id=book_id, branch_name=branch_name)
    except Exception as e:  # noqa: BLE001
        logger.exception("create_session 失败 book=%s", book_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建 session 失败: {e}",
        ) from e
    return {"session_id": sid, "book_id": book_id, "branch_name": branch_name}


# ── daemon 控制（Track F · Week 3） ──────────────────────


def _get_pool() -> DaemonPool:
    """供 Depends 使用：返回进程内默认 DaemonPool。"""
    return get_default_pool(session_factory=SessionLocal)


class DaemonStartReq(BaseModel):
    session_id: str
    start_chapter: int
    end_chapter: int
    priority: int = 5
    heartbeat_interval: float = 5.0


@router.post(
    "/books/{book_id}/daemon/start",
    summary="启动 BookProductionDaemon",
)
async def start_daemon(
    book_id: str,
    body: DaemonStartReq,
    pool: DaemonPool = Depends(_get_pool),
) -> dict[str, Any]:
    try:
        daemon = await pool.spawn(
            book_id=book_id,
            session_id=body.session_id,
            start_chapter=body.start_chapter,
            end_chapter=body.end_chapter,
            priority=body.priority,
            heartbeat_interval=body.heartbeat_interval,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return daemon.status()


@router.post(
    "/books/{book_id}/daemon/pause",
    summary="暂停 daemon",
)
async def pause_daemon(
    book_id: str,
    pool: DaemonPool = Depends(_get_pool),
) -> dict[str, Any]:
    try:
        await pool.pause(book_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return pool.get(book_id).status()  # type: ignore[union-attr]


@router.post(
    "/books/{book_id}/daemon/resume",
    summary="恢复 daemon",
)
async def resume_daemon(
    book_id: str,
    pool: DaemonPool = Depends(_get_pool),
) -> dict[str, Any]:
    try:
        await pool.resume(book_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return pool.get(book_id).status()  # type: ignore[union-attr]


@router.post(
    "/books/{book_id}/daemon/stop",
    summary="停止 daemon",
)
async def stop_daemon(
    book_id: str,
    wait: bool = Query(default=True),
    timeout: float = Query(default=10.0, ge=0.1, le=60.0),
    pool: DaemonPool = Depends(_get_pool),
) -> dict[str, Any]:
    try:
        await pool.stop(book_id, wait=wait, timeout=timeout)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    daemon = pool.get(book_id)
    return daemon.status() if daemon else {"book_id": book_id, "state": "stopped"}


@router.get(
    "/books/{book_id}/state",
    summary="读取 BookState 行",
)
async def get_book_state(
    book_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.query(BookState).filter_by(book_id=book_id).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BookState not found for {book_id}",
        )
    return row.to_dict()


@router.get(
    "/daemons",
    summary="列出所有 daemon 当前状态",
)
async def list_daemons(
    pool: DaemonPool = Depends(_get_pool),
) -> dict[str, Any]:
    return {
        "stats": pool.stats(),
        "daemons": pool.list_states(),
    }
