"""提示词加载器 — 从 DB 读取激活的提示词模板

各服务通过 get_prompt(stage, name=None) 获取提示词内容。
如果指定 name 则精确匹配，否则返回该阶段的第一个活跃模板。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.prompt import PromptTemplate

logger = logging.getLogger(__name__)


class PromptLoader:
    """从 DB 加载提示词模板"""

    def __init__(self, db: Session):
        self.db = db

    def get_prompt(self, stage: str, name: Optional[str] = None) -> Optional[str]:
        """获取指定阶段的提示词内容

        Args:
            stage: 阶段名 (chapter_writing, outline_planning, etc.)
            name: 精确匹配的模板名，None 则取该阶段第一个活跃模板

        Returns:
            提示词内容字符串，未找到则返回 None
        """
        query = self.db.query(PromptTemplate).filter_by(stage=stage, is_active=True)
        if name:
            row = query.filter_by(name=name).first()
        else:
            row = query.order_by(PromptTemplate.updated_at.desc()).first()

        if row:
            logger.debug("加载提示词: stage=%s name=%s (%d chars)", stage, row.name, len(row.content))
            return row.content
        return None

    def get_prompt_by_name(self, stage: str, name: str) -> Optional[str]:
        """按 name 精确获取"""
        return self.get_prompt(stage, name=name)

    def get_all_for_stage(self, stage: str) -> list[dict]:
        """获取某阶段所有活跃模板"""
        rows = (
            self.db.query(PromptTemplate)
            .filter_by(stage=stage, is_active=True)
            .order_by(PromptTemplate.updated_at.desc())
            .all()
        )
        return [
            {"id": r.id, "name": r.name, "content": r.content, "description": r.description}
            for r in rows
        ]

    def list_stages(self) -> dict[str, int]:
        """返回各阶段活跃模板数量"""
        from sqlalchemy import func
        rows = (
            self.db.query(PromptTemplate.stage, func.count())
            .filter_by(is_active=True)
            .group_by(PromptTemplate.stage)
            .all()
        )
        return {stage: count for stage, count in rows}
