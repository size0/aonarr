"""定时发布调度器 (APScheduler)"""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.orm import Session

from app.db.connection import SessionLocal
from app.models.publishing import PublishJob

logger = logging.getLogger(__name__)


class PublishScheduler:
    """管理定时发布任务的调度"""

    _instance: "PublishScheduler | None" = None

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self._started = False

    @classmethod
    def get_instance(cls) -> "PublishScheduler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self):
        """启动调度器"""
        if not self._started:
            self.scheduler.start()
            self._started = True
            logger.info("发布调度器已启动")
            self._restore_pending_jobs()

    def shutdown(self):
        """关闭调度器"""
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False
            logger.info("发布调度器已关闭")

    def _restore_pending_jobs(self):
        """恢复数据库中未执行的定时任务"""
        db = SessionLocal()
        try:
            pending_jobs = db.query(PublishJob).filter(
                PublishJob.status == "pending",
                PublishJob.scheduled_at.isnot(None),
            ).all()
            now = datetime.now(tz=timezone.utc)
            for job in pending_jobs:
                if job.scheduled_at and job.scheduled_at.replace(tzinfo=timezone.utc) > now:
                    self.add_job(job.id, job.scheduled_at)
                else:
                    # 已过时的任务立即执行
                    self.add_job(job.id, None)
            logger.info(f"恢复了 {len(pending_jobs)} 个待执行的发布任务")
        finally:
            db.close()

    def add_job(self, job_id: str, scheduled_at: datetime | None) -> str:
        """添加发布任务到调度器"""
        if scheduled_at:
            trigger = DateTrigger(run_date=scheduled_at)
        else:
            trigger = DateTrigger(run_date=datetime.now(tz=timezone.utc))

        scheduler_job_id = f"publish_{job_id}"

        # 移除已有同名任务
        existing = self.scheduler.get_job(scheduler_job_id)
        if existing:
            self.scheduler.remove_job(scheduler_job_id)

        self.scheduler.add_job(
            self._execute_publish,
            trigger=trigger,
            id=scheduler_job_id,
            args=[job_id],
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"发布任务已调度: {job_id} -> {scheduled_at or '立即执行'}")
        return scheduler_job_id

    def remove_job(self, job_id: str):
        """移除调度任务"""
        scheduler_job_id = f"publish_{job_id}"
        try:
            self.scheduler.remove_job(scheduler_job_id)
            logger.info(f"发布任务已取消: {job_id}")
        except Exception:
            pass

    async def _execute_publish(self, job_id: str):
        """执行发布任务"""
        db = SessionLocal()
        try:
            job = db.query(PublishJob).filter(PublishJob.id == job_id).first()
            if not job:
                logger.error(f"发布任务不存在: {job_id}")
                return

            if job.status not in ("pending", "failed"):
                logger.info(f"任务 {job_id} 状态为 {job.status}，跳过执行")
                return

            job.status = "publishing"
            db.commit()
            logger.info(f"开始执行发布任务: {job_id} (平台={job.platform})")

            try:
                result = await self._do_publish(job, db)

                if result["status"] == "success":
                    job.status = "success"
                    job.published_at = datetime.now(tz=timezone.utc)
                    job.error_message = ""
                else:
                    job.status = "failed"
                    job.error_message = result.get("message", "未知错误")
                    job.retry_count += 1

                    # 自动重试（最多 3 次）
                    if job.retry_count < 3:
                        logger.info(f"任务 {job_id} 将在 60s 后重试 (第{job.retry_count}次)")
                        self.add_job(job_id, datetime.now(tz=timezone.utc))

            except Exception as e:
                job.status = "failed"
                job.error_message = str(e)
                job.retry_count += 1
                logger.error(f"发布任务执行异常: {job_id}: {e}")

            db.commit()

        except Exception as e:
            logger.error(f"发布调度执行错误: {e}")
        finally:
            db.close()

    async def _do_publish(self, job: PublishJob, db: Session) -> dict:
        """根据平台选择对应发布器执行发布"""

        # 获取章节信息
        from sqlalchemy import text
        row = db.execute(
            text("SELECT title, content FROM chapters WHERE id = :cid"),
            {"cid": job.chapter_id},
        ).first()
        if not row:
            return {"status": "failed", "message": f"章节不存在: {job.chapter_id}"}

        chapter_title = row[0] or "未命名章节"
        chapter_content = row[1] or ""

        # 获取小说名
        novel_row = db.execute(
            text("SELECT title FROM novels WHERE id = :nid"),
            {"nid": job.novel_id},
        ).first()
        book_name = novel_row[0] if novel_row else "未命名作品"

        if job.platform == "fanqie":
            from app.services.publishing.fanqie_publisher import FanqiePublisher
            publisher = FanqiePublisher()
            return await publisher.publish_chapter(
                chapter_title=chapter_title,
                chapter_content=chapter_content,
                book_name=book_name,
                mode="publish",
            )
        elif job.platform == "qidian":
            from app.services.publishing.qidian_publisher import QidianPublisher
            publisher = QidianPublisher()
            return await publisher.publish_chapter(
                chapter_title=chapter_title,
                chapter_content=chapter_content,
                book_name=book_name,
                mode="publish",
            )
        else:
            return {"status": "failed", "message": f"不支持的平台: {job.platform}"}

    def get_scheduled_jobs(self) -> list[dict]:
        """列出当前调度中的任务"""
        if not self._started:
            return []
        jobs = []
        try:
            for job in self.scheduler.get_jobs():
                next_run = getattr(job, "next_run_time", None)
                jobs.append({
                    "id": job.id,
                    "next_run": next_run.isoformat() if next_run else None,
                    "args": job.args,
                })
        except Exception as e:
            logger.warning("获取调度任务列表失败: %s", e)
        return jobs
