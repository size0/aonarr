"""真相文件 API — 7 维度长期记忆系统"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.novel import Novel, TRUTH_FILE_KEYS
from app.services.truth.truth_manager import TruthFileManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/novels/{novel_id}/truth", tags=["truth-files"])


# ── Schemas ─────────────────────────────────────────────────────

class TruthFileUpdate(BaseModel):
    content: Optional[str] = None
    data_json: Optional[dict] = None
    last_chapter: Optional[int] = None


# ── 元信息 ──────────────────────────────────────────────────────

@router.get("/keys")
def list_truth_keys():
    """列出所有真相文件 key 及中文名"""
    names = {
        "current_state": "世界状态",
        "particle_ledger": "资源账本",
        "pending_hooks": "伏笔追踪",
        "chapter_summaries": "章节摘要",
        "subplot_board": "支线进度板",
        "emotional_arcs": "情感弧线",
        "character_matrix": "角色交互矩阵",
    }
    return [{"key": k, "name": names.get(k, k)} for k in TRUTH_FILE_KEYS]


# ── CRUD ────────────────────────────────────────────────────────

@router.get("")
def list_truth_files(novel_id: str, db: Session = Depends(get_db)):
    """列出小说的全部真相文件（自动初始化缺失的）"""
    _ensure_novel(novel_id, db)
    mgr = TruthFileManager(db)
    return mgr.ensure_truth_files(novel_id)


@router.get("/{file_key}")
def get_truth_file(novel_id: str, file_key: str, db: Session = Depends(get_db)):
    """获取单个真相文件"""
    _ensure_novel(novel_id, db)
    _validate_key(file_key)
    mgr = TruthFileManager(db)
    result = mgr.get_truth_file(novel_id, file_key)
    if not result:
        # 自动创建
        mgr.ensure_truth_files(novel_id)
        result = mgr.get_truth_file(novel_id, file_key)
    if not result:
        raise HTTPException(404, f"真相文件不存在: {file_key}")
    return result


@router.put("/{file_key}")
def update_truth_file(
    novel_id: str, file_key: str, body: TruthFileUpdate,
    db: Session = Depends(get_db),
):
    """手动更新真相文件内容"""
    _ensure_novel(novel_id, db)
    _validate_key(file_key)
    mgr = TruthFileManager(db)
    try:
        return mgr.update_truth_file(
            novel_id, file_key,
            content=body.content,
            data_json=body.data_json,
            last_chapter=body.last_chapter,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── LLM 提取 ───────────────────────────────────────────────────

@router.post("/extract/{chapter_number}")
async def extract_truth(
    novel_id: str, chapter_number: int,
    db: Session = Depends(get_db),
):
    """从指定章节提取事实，增量更新全部真相文件"""
    _ensure_novel(novel_id, db)
    mgr = TruthFileManager(db)
    try:
        result = await mgr.extract_and_update(novel_id, chapter_number)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@router.get("/snapshot/context")
def get_context_snapshot(novel_id: str, db: Session = Depends(get_db)):
    """返回所有真相文件的结构化数据快照（供 ContextBuilder 使用）"""
    _ensure_novel(novel_id, db)
    mgr = TruthFileManager(db)
    return mgr.get_context_snapshot(novel_id)


@router.get("/snapshot/markdown")
def get_markdown_snapshot(novel_id: str, db: Session = Depends(get_db)):
    """返回所有真相文件的 markdown 拼接（供 prompt 注入）"""
    _ensure_novel(novel_id, db)
    mgr = TruthFileManager(db)
    return {"markdown": mgr.get_markdown_snapshot(novel_id)}


# ── 辅助 ────────────────────────────────────────────────────────

def _ensure_novel(novel_id: str, db: Session):
    if not db.query(Novel).filter_by(id=novel_id).first():
        raise HTTPException(404, "小说不存在")


def _validate_key(file_key: str):
    if file_key not in TRUTH_FILE_KEYS:
        raise HTTPException(400, f"无效的 file_key: {file_key}，可选: {TRUTH_FILE_KEYS}")
