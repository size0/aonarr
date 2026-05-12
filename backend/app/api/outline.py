"""大纲编辑器 API 路由"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.novel import Novel, OutlineNode

router = APIRouter(prefix="/novels/{novel_id}/outline", tags=["outline"])
logger = logging.getLogger(__name__)


# ── Schemas ─────────────────────────────────────────────────────

class OutlineNodeCreate(BaseModel):
    parent_id: Optional[str] = None
    level: str = "chapter"
    title: str = ""
    summary: str = ""
    sort_order: int = 0
    metadata_json: str = "{}"


class OutlineNodeUpdate(BaseModel):
    parent_id: Optional[str] = None
    level: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    sort_order: Optional[int] = None
    metadata_json: Optional[str] = None


class ReorderItem(BaseModel):
    id: str
    sort_order: int
    parent_id: Optional[str] = None


class ReorderRequest(BaseModel):
    items: list[ReorderItem]


# ── Helpers ─────────────────────────────────────────────────────

def _get_novel_or_404(novel_id: str, db: Session) -> Novel:
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    return novel


def _node_to_dict(node: OutlineNode) -> dict:
    return {
        "id": node.id,
        "novel_id": node.novel_id,
        "parent_id": node.parent_id,
        "level": node.level,
        "title": node.title,
        "summary": node.summary,
        "sort_order": node.sort_order,
        "metadata_json": json.loads(node.metadata_json) if node.metadata_json else {},
        "created_at": node.created_at.isoformat() if node.created_at else None,
    }


def _build_tree(nodes: list[OutlineNode]) -> list[dict]:
    """将扁平节点列表构建为嵌套树"""
    node_map: dict[str, dict] = {}
    for n in nodes:
        d = _node_to_dict(n)
        d["children"] = []
        node_map[n.id] = d

    roots: list[dict] = []
    for n in nodes:
        d = node_map[n.id]
        if n.parent_id and n.parent_id in node_map:
            node_map[n.parent_id]["children"].append(d)
        else:
            roots.append(d)

    return roots


# ── Routes ──────────────────────────────────────────────────────

@router.get("")
def get_outline(novel_id: str, flat: bool = False, db: Session = Depends(get_db)):
    """获取大纲树 (默认嵌套树, flat=true 返回扁平列表)"""
    _get_novel_or_404(novel_id, db)
    nodes = (
        db.query(OutlineNode)
        .filter_by(novel_id=novel_id)
        .order_by(OutlineNode.sort_order)
        .all()
    )
    if flat:
        return [_node_to_dict(n) for n in nodes]
    return _build_tree(nodes)


@router.post("", status_code=201)
def create_node(novel_id: str, body: OutlineNodeCreate, db: Session = Depends(get_db)):
    """创建大纲节点"""
    _get_novel_or_404(novel_id, db)

    # 验证 parent 存在
    if body.parent_id:
        parent = db.query(OutlineNode).filter_by(id=body.parent_id, novel_id=novel_id).first()
        if not parent:
            raise HTTPException(400, "父节点不存在")

    # 自动计算 sort_order (追加到末尾)
    sort_order = body.sort_order
    if sort_order == 0:
        max_order = (
            db.query(OutlineNode.sort_order)
            .filter_by(novel_id=novel_id, parent_id=body.parent_id)
            .order_by(OutlineNode.sort_order.desc())
            .first()
        )
        sort_order = (max_order[0] + 1) if max_order else 0

    node = OutlineNode(
        novel_id=novel_id,
        parent_id=body.parent_id,
        level=body.level,
        title=body.title,
        summary=body.summary,
        sort_order=sort_order,
        metadata_json=body.metadata_json,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return _node_to_dict(node)


@router.patch("/{node_id}")
def update_node(novel_id: str, node_id: str, body: OutlineNodeUpdate, db: Session = Depends(get_db)):
    """更新大纲节点"""
    _get_novel_or_404(novel_id, db)
    node = db.query(OutlineNode).filter_by(id=node_id, novel_id=novel_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")

    if body.parent_id is not None:
        if body.parent_id == node_id:
            raise HTTPException(400, "节点不能成为自己的子节点")
        if body.parent_id != "":
            parent = db.query(OutlineNode).filter_by(id=body.parent_id, novel_id=novel_id).first()
            if not parent:
                raise HTTPException(400, "父节点不存在")
            node.parent_id = body.parent_id
        else:
            node.parent_id = None

    if body.level is not None:
        node.level = body.level
    if body.title is not None:
        node.title = body.title
    if body.summary is not None:
        node.summary = body.summary
    if body.sort_order is not None:
        node.sort_order = body.sort_order
    if body.metadata_json is not None:
        node.metadata_json = body.metadata_json

    db.commit()
    db.refresh(node)
    return _node_to_dict(node)


@router.delete("/{node_id}", status_code=204)
def delete_node(novel_id: str, node_id: str, db: Session = Depends(get_db)):
    """删除大纲节点 (级联删除子节点)"""
    _get_novel_or_404(novel_id, db)
    node = db.query(OutlineNode).filter_by(id=node_id, novel_id=novel_id).first()
    if not node:
        raise HTTPException(404, "节点不存在")

    # 递归删除子节点
    _delete_children(db, novel_id, node_id)
    db.delete(node)
    db.commit()


def _delete_children(db: Session, novel_id: str, parent_id: str):
    """递归删除所有子节点"""
    children = db.query(OutlineNode).filter_by(novel_id=novel_id, parent_id=parent_id).all()
    for child in children:
        _delete_children(db, novel_id, child.id)
        db.delete(child)


@router.post("/reorder")
def reorder_nodes(novel_id: str, body: ReorderRequest, db: Session = Depends(get_db)):
    """批量更新节点排序和父节点"""
    _get_novel_or_404(novel_id, db)

    for item in body.items:
        node = db.query(OutlineNode).filter_by(id=item.id, novel_id=novel_id).first()
        if node:
            node.sort_order = item.sort_order
            if item.parent_id is not None:
                node.parent_id = item.parent_id if item.parent_id else None

    db.commit()
    return {"ok": True, "updated": len(body.items)}
