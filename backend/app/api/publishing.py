"""发布引擎 API 路由"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.publishing import PublishJob
from app.services.publishing.login_manager import LoginStateManager
from app.services.publishing.scheduler import PublishScheduler
from app.services.data.collector import DataCollector
from app.services.data.predictor import ReadPredictor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/publishing", tags=["publishing"])


# ── Pydantic schemas ─────────────────────────────────────────────

class ScheduleRequest(BaseModel):
    novel_id: str
    platform: Literal["fanqie", "qidian"]
    chapter_ids: list[str] | None = None
    scheduled_at: datetime | None = None
    mode: Literal["save_draft", "publish"] = "publish"


class LoginCaptureRequest(BaseModel):
    platform: Literal["fanqie", "qidian"]
    timeout_seconds: int = 300


class CollectRequest(BaseModel):
    novel_id: str
    platform: Literal["fanqie", "qidian"] | None = None


class PredictRequest(BaseModel):
    novel_id: str
    platform: Literal["fanqie", "qidian"]
    days_ahead: int = 7


# ── 发布任务 ─────────────────────────────────────────────────────

@router.get("/jobs")
def list_publish_jobs(
    novel_id: str | None = Query(None),
    platform: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """列出发布任务"""
    q = db.query(PublishJob).order_by(PublishJob.created_at.desc())
    if novel_id:
        q = q.filter(PublishJob.novel_id == novel_id)
    if platform:
        q = q.filter(PublishJob.platform == platform)
    if status:
        q = q.filter(PublishJob.status == status)
    jobs = q.limit(limit).all()
    return [
        {
            "id": j.id,
            "novel_id": j.novel_id,
            "chapter_id": j.chapter_id,
            "platform": j.platform,
            "status": j.status,
            "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
            "published_at": j.published_at.isoformat() if j.published_at else None,
            "retry_count": j.retry_count,
            "error_message": j.error_message,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@router.post("/schedule", status_code=201)
def schedule_publish(req: ScheduleRequest, db: Session = Depends(get_db)):
    """创建发布任务（立即或定时）"""
    # 获取待发布章节列表
    if req.chapter_ids:
        chapter_ids = req.chapter_ids
    else:
        from sqlalchemy import text
        rows = db.execute(
            text("SELECT id FROM chapters WHERE novel_id = :nid ORDER BY number"),
            {"nid": req.novel_id},
        ).fetchall()
        chapter_ids = [r[0] for r in rows]

    if not chapter_ids:
        raise HTTPException(status_code=400, detail="没有可发布的章节")

    created_jobs = []
    scheduler = PublishScheduler.get_instance()

    for cid in chapter_ids:
        job = PublishJob(
            novel_id=req.novel_id,
            chapter_id=cid,
            platform=req.platform,
            status="pending",
            scheduled_at=req.scheduled_at,
        )
        db.add(job)
        db.flush()

        scheduler.add_job(job.id, req.scheduled_at)
        created_jobs.append({
            "id": job.id,
            "chapter_id": cid,
            "platform": req.platform,
            "scheduled_at": req.scheduled_at.isoformat() if req.scheduled_at else None,
        })

    db.commit()
    return {
        "status": "scheduled",
        "count": len(created_jobs),
        "jobs": created_jobs,
    }


@router.delete("/jobs/{job_id}")
def cancel_publish_job(job_id: str, db: Session = Depends(get_db)):
    """取消发布任务"""
    job = db.query(PublishJob).filter(PublishJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status not in ("pending",):
        raise HTTPException(status_code=400, detail=f"任务状态为 {job.status}，无法取消")

    scheduler = PublishScheduler.get_instance()
    scheduler.remove_job(job_id)
    job.status = "cancelled"
    db.commit()
    return {"status": "cancelled", "job_id": job_id}


@router.post("/jobs/{job_id}/retry")
def retry_publish_job(job_id: str, db: Session = Depends(get_db)):
    """重试失败的发布任务"""
    job = db.query(PublishJob).filter(PublishJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status != "failed":
        raise HTTPException(status_code=400, detail=f"仅失败任务可重试，当前状态: {job.status}")

    job.status = "pending"
    job.error_message = ""
    db.commit()

    scheduler = PublishScheduler.get_instance()
    scheduler.add_job(job.id, None)
    return {"status": "pending", "job_id": job_id, "message": "已加入重试队列"}


# ── 平台与登录态 ─────────────────────────────────────────────────

PLATFORM_META = {
    "fanqie": {"name": "番茄小说", "url": "https://fanqienovel.com"},
    "qidian": {"name": "起点中文网", "url": "https://write.qq.com"},
}


@router.get("/platforms")
def list_platforms():
    """支持的发布平台及其登录态状态"""
    results = []
    for pid, meta in PLATFORM_META.items():
        sm = LoginStateManager(pid)
        st = sm.get_status()
        results.append({
            "id": pid,
            "name": meta["name"],
            "url": meta["url"],
            "login_ready": st["ready"],
            "login_status": st["message"],
            "modified_at": st.get("modified_at"),
        })
    return results


@router.get("/platforms/{platform}/login-status")
def get_login_status(platform: str):
    """获取指定平台的登录态详情"""
    if platform not in PLATFORM_META:
        raise HTTPException(status_code=404, detail=f"不支持的平台: {platform}")
    sm = LoginStateManager(platform)
    return sm.get_status()


@router.post("/platforms/{platform}/capture-login")
async def capture_login(platform: str, timeout_seconds: int = 300):
    """触发浏览器登录态采集（会打开浏览器窗口）"""
    if platform not in PLATFORM_META:
        raise HTTPException(status_code=404, detail=f"不支持的平台: {platform}")

    if platform == "fanqie":
        from app.services.publishing.fanqie_publisher import FanqiePublisher
        publisher = FanqiePublisher()
    else:
        from app.services.publishing.qidian_publisher import QidianPublisher
        publisher = QidianPublisher()

    try:
        result = await publisher.capture_login_state(timeout_seconds=timeout_seconds)
        return result
    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e))
    except Exception as e:
        import traceback
        logger.error(f"登录态采集异常: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        detail = f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__} (无详细信息)"
        raise HTTPException(status_code=500, detail=detail)


@router.delete("/platforms/{platform}/login")
def clear_login(platform: str):
    """清除平台登录态"""
    if platform not in PLATFORM_META:
        raise HTTPException(status_code=404, detail=f"不支持的平台: {platform}")
    sm = LoginStateManager(platform)
    return sm.clear_state()


# ── 数据采集与统计 ───────────────────────────────────────────────

@router.get("/stats/{novel_id}")
def get_platform_stats(
    novel_id: str,
    platform: str | None = Query(None),
    limit: int = Query(30, le=90),
):
    """获取作品在各平台的历史数据"""
    collector = DataCollector()
    history = collector.get_history(novel_id, platform=platform, limit=limit)
    return {"novel_id": novel_id, "records": history, "count": len(history)}


@router.post("/stats/collect")
async def trigger_collect(req: CollectRequest):
    """触发数据采集"""
    collector = DataCollector()
    if req.platform:
        result = await collector.collect(req.novel_id, req.platform)
    else:
        result = await collector.collect_all(req.novel_id)
    return result


@router.post("/stats/predict")
def predict_reads(req: PredictRequest):
    """预测阅读量趋势"""
    predictor = ReadPredictor()
    return predictor.predict(
        novel_id=req.novel_id,
        platform=req.platform,
        days_ahead=req.days_ahead,
    )


# ── 调度器状态 ───────────────────────────────────────────────────

@router.get("/scheduler/status")
def scheduler_status():
    """获取调度器状态"""
    scheduler = PublishScheduler.get_instance()
    return {
        "running": scheduler._started,
        "scheduled_jobs": scheduler.get_scheduled_jobs(),
    }
