"""EventStore 实现 · Track F · Week 2 · Claude-B

按契约 §1.2 提供 5+1 个核心方法：
- append            事件写入（seq 单调）
- get_events        切片读取
- get_latest        某类型最新一条
- fork_session      从某事件点 fork 新 session（关键能力）
- stream            轮询式流式读取

设计选择：
- 项目使用同步 SQLAlchemy `Session`，所有 async 方法用 `asyncio.to_thread` 包裹底层 DB 操作。
- seq 单调通过 SQLite 的 `BEGIN IMMEDIATE` 事务（由 commit 触发写锁）保证；多进程并发由 SQLite WAL 处理。
- payload 原样存（不 base64、不压缩）；调用方自行决定是否完整读取大字段（如 draft_text）。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.models.events import Event, SessionRecord
from app.services.events import event_types as ET
from app.services.events.errors import (
    EventStoreError,
    InvalidForkError,
)

logger = logging.getLogger(__name__)


class EventStore:
    """事件流读写器。

    线程安全：
        所有公开方法在 worker 线程中使用 **短生命周期 session**（独立于外部 db），
        因此可以放心被 asyncio 并发调用而不需要锁。SQLite 通过 WAL + busy_timeout
        在内核层串行化 seq 写入。
    """

    def __init__(self, db: Session):
        # 外部 Session 仅用于：1) 提供 engine binding；2) 直接读取（如 get_session）
        # 写路径在 _new_session() 创建独立 session，避免多线程共享同一 Session。
        self.db = db
        bind = getattr(db, "bind", None) or db.get_bind()
        self._session_factory = sessionmaker(bind=bind, autoflush=False, autocommit=False)

    def _new_session(self) -> Session:
        return self._session_factory()

    # ── append ──────────────────────────────────────────────

    async def append(
        self,
        book_id: str,
        session_id: str,
        event_type: str,
        actor: str,
        payload: dict,
        chapter_number: int | None = None,
        parent_event_id: int | None = None,
    ) -> int:
        """追加事件，返回新事件 id。

        实现：
            在事务内 SELECT MAX(seq)+1，再 INSERT，commit。
            发生 IntegrityError（unique seq 冲突）时重试至多 3 次。
        """
        if not book_id or not session_id or not event_type or not actor:
            raise EventStoreError(
                "append() 缺少必填字段（book_id / session_id / event_type / actor）"
            )

        def _do_append() -> int:
            for attempt in range(5):
                ws = self._new_session()
                try:
                    parent_sid = self._lookup_parent_session(ws, session_id)
                    next_seq = self._next_seq(ws, session_id)
                    evt = Event(
                        book_id=book_id,
                        session_id=session_id,
                        parent_session_id=parent_sid,
                        seq=next_seq,
                        event_type=event_type,
                        actor=actor,
                        payload=dict(payload) if payload else {},
                        chapter_number=chapter_number,
                        parent_event_id=parent_event_id,
                    )
                    ws.add(evt)
                    ws.commit()
                    ws.refresh(evt)
                    return int(evt.id)
                except IntegrityError as e:
                    ws.rollback()
                    if attempt == 4:
                        raise EventStoreError(f"append 冲突重试用尽: {e}") from e
                    logger.debug("append seq 冲突，重试 %d/5", attempt + 1)
                except OperationalError as e:
                    ws.rollback()
                    raise EventStoreError(f"append 数据库错误: {e}") from e
                finally:
                    ws.close()
            raise EventStoreError("append 异常退出")

        return await asyncio.to_thread(_do_append)

    @staticmethod
    def _next_seq(session: Session, session_id: str) -> int:
        max_seq = (
            session.query(func.max(Event.seq))
            .filter(Event.session_id == session_id)
            .scalar()
        )
        return int(max_seq or 0) + 1

    @staticmethod
    def _lookup_parent_session(session: Session, session_id: str) -> str | None:
        rec = session.query(SessionRecord).filter_by(id=session_id).first()
        return rec.parent_session_id if rec else None

    # ── get_events ──────────────────────────────────────────

    async def get_events(
        self,
        book_id: str,
        session_id: str,
        from_seq: int = 0,
        limit: int = 100,
        types: list[str] | None = None,
        chapter_number: int | None = None,
    ) -> list[Event]:
        """切片读取事件，按 seq 升序。"""
        limit = max(1, min(int(limit), 1000))

        def _do_get() -> list[Event]:
            ws = self._new_session()
            try:
                stmt = (
                    select(Event)
                    .where(Event.book_id == book_id)
                    .where(Event.session_id == session_id)
                    .where(Event.seq >= from_seq)
                )
                if types:
                    stmt = stmt.where(Event.event_type.in_(list(types)))
                if chapter_number is not None:
                    stmt = stmt.where(Event.chapter_number == chapter_number)
                stmt = stmt.order_by(Event.seq.asc()).limit(limit)
                rows = list(ws.scalars(stmt).all())
                # 把 ORM 对象与 session 解耦（expunge），允许 ws.close 后仍可访问
                for r in rows:
                    ws.expunge(r)
                return rows
            finally:
                ws.close()

        return await asyncio.to_thread(_do_get)

    # ── get_latest ──────────────────────────────────────────

    async def get_latest(
        self,
        book_id: str,
        session_id: str,
        event_type: str,
    ) -> Event | None:
        """某 session 中某类型的最新一条事件（按 seq 倒序取首条）"""

        def _do_get() -> Event | None:
            ws = self._new_session()
            try:
                stmt = (
                    select(Event)
                    .where(Event.book_id == book_id)
                    .where(Event.session_id == session_id)
                    .where(Event.event_type == event_type)
                    .order_by(Event.seq.desc())
                    .limit(1)
                )
                row = ws.scalars(stmt).first()
                if row is not None:
                    ws.expunge(row)
                return row
            finally:
                ws.close()

        return await asyncio.to_thread(_do_get)

    # ── fork_session ────────────────────────────────────────

    async def fork_session(
        self,
        book_id: str,
        from_event_id: int,
        branch_name: str,
    ) -> str:
        """从指定事件点 fork 出新 session。

        - 校验 from_event_id 存在且属于 book_id
        - 创建新 SessionRecord，parent_session_id = 源 session
        - 在源 session 写一条 session_forked 事件（payload 含 new_session_id 等）
        """
        if not book_id or not branch_name:
            raise InvalidForkError("fork_session 需要 book_id 和 branch_name")
        if from_event_id is None or int(from_event_id) <= 0:
            raise InvalidForkError("from_event_id 必须为正整数")

        def _create_session_record_and_emit() -> str:
            ws = self._new_session()
            try:
                src_evt = ws.query(Event).filter_by(id=int(from_event_id)).first()
                if src_evt is None:
                    raise InvalidForkError(f"event {from_event_id} 不存在")
                if src_evt.book_id != book_id:
                    raise InvalidForkError(
                        f"event {from_event_id} 不属于 book {book_id}"
                    )
                source_session_id = src_evt.session_id
                src_chapter = src_evt.chapter_number

                new_session = SessionRecord(
                    book_id=book_id,
                    parent_session_id=source_session_id,
                    forked_at_event=int(from_event_id),
                    branch_name=branch_name,
                    status="active",
                )
                ws.add(new_session)
                ws.flush()
                new_session_id = new_session.id

                # 在源 session 写 session_forked 事件
                parent_sid = self._lookup_parent_session(ws, source_session_id)
                next_seq = self._next_seq(ws, source_session_id)
                forked_event = Event(
                    book_id=book_id,
                    session_id=source_session_id,
                    parent_session_id=parent_sid,
                    seq=next_seq,
                    event_type=ET.SESSION_FORKED,
                    actor="event_store",
                    payload={
                        "new_session_id": new_session_id,
                        "branch_name": branch_name,
                        "forked_at_event": int(from_event_id),
                    },
                    chapter_number=src_chapter,
                    parent_event_id=int(from_event_id),
                )
                ws.add(forked_event)
                ws.commit()
                return new_session_id
            finally:
                ws.close()

        try:
            return await asyncio.to_thread(_create_session_record_and_emit)
        except InvalidForkError:
            raise
        except Exception as e:
            raise EventStoreError(f"fork_session 失败: {e}") from e

    async def get_session(self, session_id: str) -> SessionRecord | None:
        """读取 SessionRecord（便于其他 Claude 检查 session 状态）"""

        def _do_get() -> SessionRecord | None:
            ws = self._new_session()
            try:
                rec = ws.query(SessionRecord).filter_by(id=session_id).first()
                if rec is not None:
                    ws.expunge(rec)
                return rec
            finally:
                ws.close()

        return await asyncio.to_thread(_do_get)

    async def create_session(
        self,
        book_id: str,
        branch_name: str = "main",
    ) -> str:
        """创建顶层（非 fork）session。返回 session_id。"""
        if not book_id:
            raise EventStoreError("create_session 需要 book_id")

        def _do_create() -> str:
            ws = self._new_session()
            try:
                rec = SessionRecord(
                    book_id=book_id,
                    parent_session_id=None,
                    forked_at_event=None,
                    branch_name=branch_name,
                    status="active",
                )
                ws.add(rec)
                ws.commit()
                ws.refresh(rec)
                return rec.id
            finally:
                ws.close()

        return await asyncio.to_thread(_do_create)

    # ── stream ──────────────────────────────────────────────

    async def stream(
        self,
        book_id: str,
        session_id: str,
        from_seq: int = 0,
        types: list[str] | None = None,
        poll_interval: float = 0.5,
    ) -> AsyncIterator[Event]:
        """SSE 风格轮询流。调用方负责退出（break / cancel）。"""
        last_seq = max(0, int(from_seq))
        while True:
            events = await self.get_events(
                book_id=book_id,
                session_id=session_id,
                from_seq=last_seq,
                limit=200,
                types=types,
            )
            for ev in events:
                yield ev
                last_seq = max(last_seq, int(ev.seq) + 1)
            if not events:
                await asyncio.sleep(poll_interval)
