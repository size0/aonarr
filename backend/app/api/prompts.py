"""提示词模板 CRUD API"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.prompt import PromptTemplate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prompts", tags=["prompts"])


# ── Schemas ─────────────────────────────────────────────────────

class PromptCreate(BaseModel):
    stage: str
    name: str
    content: str = ""
    description: str = ""
    is_active: bool = True


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PromptOut(BaseModel):
    id: str
    stage: str
    name: str
    content: str
    description: str
    version: int
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ── 阶段元信息 ─────────────────────────────────────────────────

STAGE_META = {
    "chapter_writing": {"label": "章节生成", "icon": "📝", "color": "#3b82f6", "bg": "#dbeafe"},
    "outline_planning": {"label": "大纲规划", "icon": "📑", "color": "#22c55e", "bg": "#dcfce7"},
    "post_chapter_pipeline": {"label": "章后管线", "icon": "🔄", "color": "#0ea5e9", "bg": "#e0f2fe"},
    "audit_review": {"label": "质量审核", "icon": "🔍", "color": "#f59e0b", "bg": "#fef3c7"},
    "style_detection": {"label": "文风检测", "icon": "🎨", "color": "#ec4899", "bg": "#fce7f3"},
    "book_analysis_extract": {"label": "拆书提取", "icon": "📖", "color": "#8b5cf6", "bg": "#ede9fe"},
    "book_analysis_deep": {"label": "深度分析", "icon": "🔬", "color": "#6366f1", "bg": "#e0e7ff"},
    "context_build": {"label": "上下文构建", "icon": "🧠", "color": "#6366f1", "bg": "#e0e7ff"},
    "learning_agent": {"label": "学习Agent", "icon": "🤖", "color": "#14b8a6", "bg": "#ccfbf1"},
    "prompt_optimization": {"label": "润色优化", "icon": "✨", "color": "#ec4899", "bg": "#fce7f3"},
    "prediction": {"label": "数据预测", "icon": "📈", "color": "#f97316", "bg": "#ffedd5"},
}


@router.get("/stages")
def list_stages():
    """返回所有可用阶段及其元信息"""
    return STAGE_META


# ── CRUD ────────────────────────────────────────────────────────

@router.get("")
def list_prompts(
    stage: Optional[str] = Query(None, description="按阶段筛选"),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """列出所有提示词模板"""
    q = db.query(PromptTemplate).order_by(
        PromptTemplate.stage, PromptTemplate.version.desc()
    )
    if stage:
        q = q.filter(PromptTemplate.stage == stage)
    if active_only:
        q = q.filter(PromptTemplate.is_active.is_(True))
    rows = q.all()
    return [_to_dict(r) for r in rows]


@router.get("/{prompt_id}")
def get_prompt(prompt_id: str, db: Session = Depends(get_db)):
    """获取单个提示词详情"""
    row = db.query(PromptTemplate).filter_by(id=prompt_id).first()
    if not row:
        raise HTTPException(404, "提示词模板不存在")
    return _to_dict(row)


@router.post("", status_code=201)
def create_prompt(body: PromptCreate, db: Session = Depends(get_db)):
    """创建新提示词模板"""
    if body.stage not in STAGE_META:
        raise HTTPException(400, f"未知阶段: {body.stage}，可用阶段: {list(STAGE_META.keys())}")

    row = PromptTemplate(
        stage=body.stage,
        name=body.name,
        content=body.content,
        description=body.description,
        is_active=body.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.patch("/{prompt_id}")
def update_prompt(prompt_id: str, body: PromptUpdate, db: Session = Depends(get_db)):
    """更新提示词模板 (内容变更自动版本+1)"""
    row = db.query(PromptTemplate).filter_by(id=prompt_id).first()
    if not row:
        raise HTTPException(404, "提示词模板不存在")

    content_changed = False
    if body.name is not None:
        row.name = body.name
    if body.content is not None and body.content != row.content:
        row.content = body.content
        content_changed = True
    if body.description is not None:
        row.description = body.description
    if body.is_active is not None:
        row.is_active = body.is_active

    if content_changed:
        row.version += 1

    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.delete("/{prompt_id}")
def delete_prompt(prompt_id: str, db: Session = Depends(get_db)):
    """删除提示词模板"""
    count = db.query(PromptTemplate).filter_by(id=prompt_id).delete()
    db.commit()
    if count == 0:
        raise HTTPException(404, "提示词模板不存在")
    return {"ok": True}


@router.post("/{prompt_id}/duplicate")
def duplicate_prompt(prompt_id: str, db: Session = Depends(get_db)):
    """复制一个提示词模板"""
    src = db.query(PromptTemplate).filter_by(id=prompt_id).first()
    if not src:
        raise HTTPException(404, "源模板不存在")

    new = PromptTemplate(
        stage=src.stage,
        name=f"{src.name} (副本)",
        content=src.content,
        description=src.description,
        is_active=False,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return _to_dict(new)


# ── helpers ─────────────────────────────────────────────────────

def _to_dict(row: PromptTemplate) -> dict:
    return {
        "id": row.id,
        "stage": row.stage,
        "name": row.name,
        "content": row.content,
        "description": row.description,
        "version": row.version,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }
