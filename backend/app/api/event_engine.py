"""职场破局编剧 Agent — API 路由

提供事件发动机的 HTTP 接口：
- POST /event-engine/generate  —— 生成单个事件蓝图
- GET  /event-engine/event-types —— 获取可用事件类型库
- GET  /event-engine/system-prompt —— 获取系统提示词（调试用）
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.llm.resolver import StageModelResolver
from app.services.creation.zhichang_event_engine import (
    ZhichangEventEngine,
    EventEngineInput,
    EVENT_TYPES,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/event-engine", tags=["event-engine"])


# ── Request/Response Schemas ────────────────────────────────────

class EventGenerateRequest(BaseModel):
    protagonist_name: str = "林舟"
    protagonist_role: str = "高级销售"
    stage: str = "生存期"  # 生存期 / 破局期 / 上位期
    existing_antagonists: List[str] = []
    last_event_result: str = ""
    conflict_direction: str = ""
    forbidden_elements: List[str] = []
    intensity: str = "高"  # 低 / 中 / 高
    chapter_number: int = 1
    novel_id: str = ""


class EventGenerateResponse(BaseModel):
    event_title: str
    conflict_cause: str
    antagonist_goal: str
    antagonist_method: str
    protagonist_surface: str
    protagonist_hidden: str
    key_evidence: str
    reversal_trigger: str
    antagonist_consequence: str
    protagonist_gain: str
    chapter_outline: str
    killer_line: str


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/generate", response_model=EventGenerateResponse)
async def generate_event(req: EventGenerateRequest, db: Session = Depends(get_db)):
    """调用事件发动机生成一个结构化事件蓝图

    使用 outline_planning 阶段绑定的 LLM（通常是高质量推理模型）。
    """
    # 构造输入
    input_data = EventEngineInput(
        protagonist_name=req.protagonist_name,
        protagonist_role=req.protagonist_role,
        stage=req.stage,
        existing_antagonists=req.existing_antagonists,
        last_event_result=req.last_event_result,
        conflict_direction=req.conflict_direction,
        forbidden_elements=req.forbidden_elements,
        intensity=req.intensity,
        chapter_number=req.chapter_number,
        novel_id=req.novel_id,
    )

    # 获取 LLM 客户端 — 使用 outline_planning 阶段的模型
    resolver = StageModelResolver(db)
    try:
        llm = resolver.get_llm_for_stage("outline_planning")
    except ValueError:
        # 兜底：无 LLM 配置时使用启发式
        llm = None

    # 创建引擎并生成
    engine = ZhichangEventEngine(llm_client=llm)
    blueprint = await engine.generate(input_data)

    return EventGenerateResponse(
        event_title=blueprint.event_title,
        conflict_cause=blueprint.conflict_cause,
        antagonist_goal=blueprint.antagonist_goal,
        antagonist_method=blueprint.antagonist_method,
        protagonist_surface=blueprint.protagonist_surface,
        protagonist_hidden=blueprint.protagonist_hidden,
        key_evidence=blueprint.key_evidence,
        reversal_trigger=blueprint.reversal_trigger,
        antagonist_consequence=blueprint.antagonist_consequence,
        protagonist_gain=blueprint.protagonist_gain,
        chapter_outline=blueprint.chapter_outline,
        killer_line=blueprint.killer_line,
    )


@router.get("/event-types")
def list_event_types():
    """获取内置事件类型库"""
    return {"event_types": EVENT_TYPES, "count": len(EVENT_TYPES)}


@router.get("/system-prompt")
def get_system_prompt():
    """获取事件发动机的系统提示词（调试用）"""
    return {"system_prompt": SYSTEM_PROMPT}
