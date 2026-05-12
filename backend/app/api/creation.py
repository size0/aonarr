"""创作引擎 API 路由 — 大纲/章节生成/SSE流式/全托管"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.services.creation.outline_generator import OutlineGenerator
from app.services.creation.chapter_writer import ChapterWriter
from app.services.creation.post_pipeline import PostPipeline
from app.services.creation.autopilot import AutopilotDaemon, get_autopilot_status, get_autopilot_stream
from app.services.creation.novel_bootstrapper import NovelBootstrapper

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/creation", tags=["creation"])


# ── Schemas ──────────────────────────────────────────────────────

class OutlineRequest(BaseModel):
    premise: str
    genre: str = "玄幻"
    synopsis: str = ""
    world_setting: str = ""
    target_chapters: int = 200


class ChapterGenerateRequest(BaseModel):
    beats: Optional[list[dict]] = None


class AutopilotStartRequest(BaseModel):
    start_chapter: int = 1
    end_chapter: int = 10
    auto_beats: bool = True


class TitleOptimizeRequest(BaseModel):
    title: str
    genre: str = ""
    synopsis: str = ""
    num_candidates: int = 5


# ── 新建初始化（世界观+人物+大纲）─────────────────────────────────

@router.get("/{novel_id}/bootstrap")
async def bootstrap_novel(novel_id: str, db: Session = Depends(get_db)):
    """SSE 流式初始化新小说：自动生成世界观→人物→大纲"""

    async def event_generator():
        bootstrapper = NovelBootstrapper(db)
        async for event_json in bootstrapper.bootstrap_stream(novel_id):
            yield f"data: {event_json}\n\n"
        yield "data: {\"stage\":\"done\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 初始化状态查询 ─────────────────────────────────────────────────

@router.get("/{novel_id}/bootstrap/status")
def get_bootstrap_status(novel_id: str, db: Session = Depends(get_db)):
    """查询小说初始化各阶段的数据状态"""
    from app.models.novel import Novel, Character, WorldItem, OutlineNode
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")

    world_count = db.query(WorldItem).filter_by(novel_id=novel_id).count()
    char_count = db.query(Character).filter_by(novel_id=novel_id).count()
    outline_count = db.query(OutlineNode).filter_by(novel_id=novel_id).count()

    # 获取角色和大纲的摘要数据
    characters_data = []
    for ch in db.query(Character).filter_by(novel_id=novel_id).limit(10).all():
        characters_data.append({
            "name": ch.name, "role": ch.role,
            "description": (ch.description or "")[:60],
            "traits": ch.traits if hasattr(ch, "traits") and ch.traits else [],
        })

    outline_data = []
    for node in db.query(OutlineNode).filter_by(novel_id=novel_id, parent_id=None).order_by(OutlineNode.sort_order).limit(8).all():
        children = db.query(OutlineNode).filter_by(parent_id=node.id).order_by(OutlineNode.sort_order).limit(5).all()
        outline_data.append({
            "title": node.title, "summary": node.summary or "",
            "chapters": [{"title": c.title, "summary": c.summary or ""} for c in children],
        })

    return {
        "novel_id": novel_id,
        "title": novel.title,
        "stages": {
            "world": {
                "status": "done" if world_count > 0 or novel.world_setting else "empty",
                "count": world_count,
                "has_setting": bool(novel.world_setting),
            },
            "characters": {
                "status": "done" if char_count > 0 else "empty",
                "count": char_count,
                "data": characters_data,
            },
            "outline": {
                "status": "done" if outline_count > 0 else "empty",
                "count": outline_count,
                "data": {"volumes": outline_data} if outline_data else None,
            },
        },
    }


# ── 单阶段重新生成 ─────────────────────────────────────────────────

@router.post("/{novel_id}/bootstrap/{stage}/regenerate")
async def regenerate_bootstrap_stage(
    novel_id: str, stage: str, db: Session = Depends(get_db),
):
    """重新生成单个初始化阶段：world / characters / outline"""
    if stage not in ("world", "characters", "outline"):
        raise HTTPException(400, f"无效阶段: {stage}，可选: world, characters, outline")
    bootstrapper = NovelBootstrapper(db)
    try:
        result = await bootstrapper.regenerate_stage(novel_id, stage)
        return result
    except ValueError as e:
        if "不存在" in str(e):
            raise HTTPException(404, str(e))
        logger.exception(f"重新生成 {stage} 失败 (ValueError)")
        raise HTTPException(500, f"生成失败: {str(e)[:200]}")
    except Exception as e:
        logger.exception(f"重新生成 {stage} 失败")
        raise HTTPException(500, f"生成失败: {str(e)[:200]}")


# ── 大纲 ─────────────────────────────────────────────────────────

@router.post("/{novel_id}/outline")
async def generate_outline(novel_id: str, req: OutlineRequest, db: Session = Depends(get_db)):
    """生成宏观大纲并持久化到 outline_nodes"""
    gen = OutlineGenerator(db)
    outline = await gen.generate_macro_outline(
        novel_id,
        premise=req.premise,
        genre=req.genre,
        synopsis=req.synopsis,
        world_setting=req.world_setting,
        target_chapters=req.target_chapters,
    )
    # 持久化到 DB（复用 NovelBootstrapper 的保存逻辑）
    from app.services.creation.novel_bootstrapper import NovelBootstrapper
    bootstrapper = NovelBootstrapper(db)
    from app.models.novel import OutlineNode
    db.query(OutlineNode).filter_by(novel_id=novel_id).delete()
    db.flush()
    saved_count = bootstrapper._save_outline(novel_id, outline)
    db.commit()
    return {"novel_id": novel_id, "outline": outline, "saved_count": saved_count}


@router.post("/{novel_id}/chapter/{number}/beats")
async def generate_beats(novel_id: str, number: int, db: Session = Depends(get_db)):
    """为指定章节生成节拍"""
    from app.services.creation.context_builder import ContextBuilder
    ctx = ContextBuilder(db).build(novel_id, number)
    tv = ctx.to_template_vars()

    gen = OutlineGenerator(db)
    beats = await gen.generate_chapter_beats(
        novel_id, number,
        outline=tv.get("outline", ""),
        previous_summaries=tv.get("previous_summaries", ""),
        characters=tv.get("characters", ""),
        active_foreshadows=tv.get("foreshadows", ""),
    )
    return {"novel_id": novel_id, "chapter_number": number, "beats": beats}


# ── 章节规划（plan → compose） ────────────────────────────────────

class PlanRequest(BaseModel):
    author_intent: str = ""
    current_focus: str = ""


@router.post("/{novel_id}/chapter/{number}/plan")
async def plan_chapter(
    novel_id: str, number: int, req: PlanRequest = PlanRequest(),
    db: Session = Depends(get_db),
):
    """生成本章写作计划（Planner + Composer）"""
    from app.services.creation.planner import Planner
    from app.services.creation.composer import Composer

    planner = Planner(db)
    plan = await planner.plan(
        novel_id, number,
        author_intent=req.author_intent,
        current_focus=req.current_focus,
    )

    composer = Composer(db)
    composed = composer.compose(novel_id, number, plan)

    return {
        "novel_id": novel_id,
        "chapter_number": number,
        "plan": plan,
        "composed": {
            "chapter_intent": composed.get("chapter_intent", ""),
            "pov_character": composed.get("pov_character", ""),
            "location": composed.get("location", ""),
            "tone": composed.get("tone", ""),
            "constraints": composed.get("constraints", []),
            "beats": composed.get("beats", []),
        },
    }


# ── 章节生成 ─────────────────────────────────────────────────────

class IntentGenerateRequest(BaseModel):
    author_intent: str = ""
    current_focus: str = ""
    beats: Optional[list[dict]] = None
    mode: str = "creative"
    enable_settlement: bool = True
    use_planner: bool = True


@router.post("/{novel_id}/chapter/{number}/generate")
async def generate_chapter(
    novel_id: str, number: int,
    req: ChapterGenerateRequest = ChapterGenerateRequest(),
    db: Session = Depends(get_db),
):
    """非流式生成章节"""
    writer = ChapterWriter(db)
    content = await writer.generate_chapter(novel_id, number, beats=req.beats)
    return {
        "novel_id": novel_id,
        "chapter_number": number,
        "content": content,
        "word_count": len(content),
    }


@router.post("/{novel_id}/chapter/{number}/generate-v2")
async def generate_chapter_v2(
    novel_id: str, number: int,
    req: IntentGenerateRequest = IntentGenerateRequest(),
    db: Session = Depends(get_db),
):
    """plan → compose → write 全链路章节生成（SSE 流式）"""

    async def event_generator():
        beats = req.beats
        composed = None
        use_plan = req.use_planner and not beats

        # Step 1: Planner
        if use_plan:
            from app.services.creation.planner import Planner
            from app.services.creation.composer import Composer

            yield f"data: {json.dumps({'type': 'plan_start'}, ensure_ascii=False)}\n\n"

            planner = Planner(db)
            plan = await planner.plan(
                novel_id, number,
                author_intent=req.author_intent,
                current_focus=req.current_focus,
            )
            composer = Composer(db)
            composed = composer.compose(novel_id, number, plan)

            beats = composed.get("beats", [])

            yield f"data: {json.dumps({'type': 'plan_done', 'intent': plan.get('chapter_intent', ''), 'beats_count': len(beats)}, ensure_ascii=False)}\n\n"

        # Step 2: ChapterWriter — 传入完整 Composer 上下文
        writer = ChapterWriter(db)
        async for event_json in writer.generate_chapter_stream(
            novel_id, number,
            beats=beats,
            mode=req.mode,
            enable_settlement=req.enable_settlement,
            composed_context=composed if use_plan else None,
        ):
            yield f"data: {event_json}\n\n"
        yield "data: {\"type\":\"done\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{novel_id}/chapter/{number}/stream")
async def stream_chapter(
    novel_id: str, number: int,
    db: Session = Depends(get_db),
):
    """SSE 流式生成章节"""

    async def event_generator():
        writer = ChapterWriter(db)
        async for event_json in writer.generate_chapter_stream(novel_id, number):
            yield f"data: {event_json}\n\n"
        yield "data: {\"type\":\"done\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 章后管线 ─────────────────────────────────────────────────────

@router.post("/{novel_id}/chapter/{number}/post-pipeline")
async def run_post_pipeline(novel_id: str, number: int, db: Session = Depends(get_db)):
    """手动触发章后管线"""
    pipeline = PostPipeline(db)
    try:
        result = await pipeline.run(novel_id, number)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"novel_id": novel_id, "chapter_number": number, "result": result}


# ── 全托管 ───────────────────────────────────────────────────────

@router.post("/{novel_id}/autopilot/start")
async def autopilot_start(
    novel_id: str, req: AutopilotStartRequest, db: Session = Depends(get_db),
):
    """启动全托管写作"""
    daemon = AutopilotDaemon(db)
    try:
        status = await daemon.start(
            novel_id,
            start_chapter=req.start_chapter,
            end_chapter=req.end_chapter,
            auto_beats=req.auto_beats,
        )
        return status.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{novel_id}/autopilot/stop")
async def autopilot_stop(novel_id: str, db: Session = Depends(get_db)):
    """停止全托管写作"""
    daemon = AutopilotDaemon(db)
    try:
        status = daemon.stop(novel_id)
        return status.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{novel_id}/autopilot/pause")
async def autopilot_pause(novel_id: str, db: Session = Depends(get_db)):
    """暂停全托管写作"""
    daemon = AutopilotDaemon(db)
    try:
        status = daemon.pause(novel_id)
        return status.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{novel_id}/autopilot/resume")
async def autopilot_resume(novel_id: str, db: Session = Depends(get_db)):
    """恢复全托管写作"""
    daemon = AutopilotDaemon(db)
    try:
        status = daemon.resume(novel_id)
        return status.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{novel_id}/autopilot/resume-checkpoint")
async def autopilot_resume_checkpoint(novel_id: str, db: Session = Depends(get_db)):
    """从 DB 检查点恢复中断的托管写作（进程重启后使用）"""
    daemon = AutopilotDaemon(db)
    try:
        status = await daemon.resume_from_checkpoint(novel_id)
        return status.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{novel_id}/autopilot/status")
async def autopilot_status(novel_id: str):
    """查询全托管写作状态"""
    status = get_autopilot_status(novel_id)
    return status.to_dict()


@router.get("/{novel_id}/autopilot/stream")
async def autopilot_stream(novel_id: str):
    """全托管写作 SSE 流式输出 — 实时推送章节生成事件"""
    import asyncio
    q = get_autopilot_stream(novel_id)
    if not q:
        raise HTTPException(404, "没有运行中的托管任务")

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30)
                yield f"data: {event}\n\n"
                # 检查是否结束信号
                try:
                    ev = json.loads(event)
                    if ev.get("type") in ("autopilot_done", "error"):
                        break
                except (json.JSONDecodeError, TypeError):
                    pass
            except asyncio.TimeoutError:
                yield "data: {\"type\":\"heartbeat\"}\n\n"
            except Exception:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 书名优化器 ──────────────────────────────────────────────────

@router.post("/title/optimize")
async def optimize_title(req: TitleOptimizeRequest, db: Session = Depends(get_db)):
    """AI 书名优化 — 四维拆解公式"""
    from app.services.creation.title_optimizer import TitleOptimizer
    optimizer = TitleOptimizer(db)
    try:
        result = await optimizer.optimize(
            req.title,
            genre=req.genre,
            synopsis=req.synopsis,
            num_candidates=req.num_candidates,
        )
        return result.to_dict()
    except Exception as e:
        logger.exception("书名优化失败")
        raise HTTPException(500, f"优化失败: {str(e)[:200]}")
