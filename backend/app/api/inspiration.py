"""灵感助理 API — 对话式 AI 小说顾问（含 session 管理 + 记忆）"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.memory import ChatSession, ChatMessage as ChatMessageRow
from app.services.inspiration.engine import chat_stream

router = APIRouter(prefix="/inspiration", tags=["inspiration"])


# ── Pydantic 模型 ────────────────────────────────────────────────

class ChatMessageIn(BaseModel):
    role: str = "user"
    content: str = ""

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    messages: list[ChatMessageIn]

class SessionCreate(BaseModel):
    title: str = "新对话"

class SessionRename(BaseModel):
    title: str


# ── Session CRUD ─────────────────────────────────────────────────

@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)):
    """列出所有对话会话（按更新时间倒序）"""
    rows = (
        db.query(ChatSession)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "title": s.title,
            "message_count": s.message_count,
            "summary": s.summary[:100] if s.summary else "",
            "created_at": s.created_at.isoformat() if s.created_at else "",
            "updated_at": s.updated_at.isoformat() if s.updated_at else "",
        }
        for s in rows
    ]


@router.post("/sessions")
def create_session(req: SessionCreate, db: Session = Depends(get_db)):
    """创建新对话会话"""
    session = ChatSession(title=req.title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "title": session.title}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    """获取会话详情 + 消息历史"""
    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "会话不存在")
    msgs = (
        db.query(ChatMessageRow)
        .filter_by(session_id=session_id)
        .order_by(ChatMessageRow.turn_index)
        .all()
    )
    return {
        "id": session.id,
        "title": session.title,
        "summary": session.summary,
        "message_count": session.message_count,
        "messages": [
            {"role": m.role, "content": m.content, "turn_index": m.turn_index}
            for m in msgs
        ],
    }


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, req: SessionRename, db: Session = Depends(get_db)):
    """重命名会话"""
    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "会话不存在")
    session.title = req.title
    db.commit()
    return {"id": session.id, "title": session.title}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """删除会话及其消息"""
    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "会话不存在")
    db.query(ChatMessageRow).filter_by(session_id=session_id).delete()
    db.delete(session)
    db.commit()
    return {"ok": True}


# ── 对话（带持久化）──────────────────────────────────────────────

@router.post("/chat")
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """SSE 流式对话（自动持久化消息 + 记忆注入）

    - 首次对话可不传 session_id，自动创建
    - 返回 SSE 流，首条 event 含 session_id
    """
    # 获取或创建 session
    session = None
    if req.session_id:
        session = db.query(ChatSession).filter_by(id=req.session_id).first()

    if not session:
        session = ChatSession(title="新对话")
        db.add(session)
        db.commit()
        db.refresh(session)

    # 保存用户消息
    user_msg = req.messages[-1] if req.messages else None
    if user_msg and user_msg.role == "user":
        turn_idx = session.message_count
        row = ChatMessageRow(
            session_id=session.id,
            role="user",
            content=user_msg.content,
            turn_index=turn_idx,
        )
        db.add(row)
        session.message_count = turn_idx + 1
        db.commit()

    # 构建完整消息列表给 LLM
    all_msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    session_id = session.id

    async def event_generator():
        # 首条：发送 session_id
        yield f"data: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"

        full_response = []
        async for chunk in chat_stream(db, all_msgs, session_id=session_id):
            full_response.append(chunk)
            data = json.dumps({"content": chunk}, ensure_ascii=False)
            yield f"data: {data}\n\n"

        # 保存助理回复
        assistant_content = "".join(full_response)
        if assistant_content:
            db2 = db  # 复用同一个 db session
            turn_idx = (
                db2.query(ChatSession)
                .filter_by(id=session_id)
                .first()
            )
            if turn_idx:
                msg_row = ChatMessageRow(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    turn_index=turn_idx.message_count,
                )
                db2.add(msg_row)
                turn_idx.message_count += 1
                db2.commit()

                # 自动命名：首条消息时用用户输入前20字符做标题
                if turn_idx.message_count <= 2 and turn_idx.title == "新对话":
                    first_user = user_msg.content[:20] if user_msg else ""
                    if first_user:
                        turn_idx.title = first_user + ("..." if len(user_msg.content) > 20 else "")
                        db2.commit()

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 数据摘要 ─────────────────────────────────────────────────────

@router.get("/context-summary")
def get_context_summary(db: Session = Depends(get_db)):
    """返回当前数据摘要（前端显示用）"""
    from app.models.learning import HotNovelMeta
    total = db.query(HotNovelMeta).count()
    session_count = db.query(ChatSession).count()
    return {
        "total_novels": total,
        "session_count": session_count,
        "status": "ready" if total > 0 else "empty",
    }
