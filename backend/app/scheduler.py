"""APScheduler 定时任务框架

集中管理所有定时任务：
- 发布调度（按章发布）
- 数据采集（每日平台数据）
- 学习 Agent（热门采集 + 拆书学习 + 提示词优化）
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def _build_jobstore():
    """优先使用 SQLAlchemy 持久化，失败回退内存"""
    try:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from app.db.connection import engine
        return SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")
    except Exception as e:
        logger.warning("SQLAlchemyJobStore 初始化失败，回退 MemoryJobStore: %s", e)
        from apscheduler.jobstores.memory import MemoryJobStore
        return MemoryJobStore()


def get_scheduler() -> AsyncIOScheduler:
    """获取全局调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            jobstores={"default": _build_jobstore()},
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 600,
            },
        )
    return _scheduler


def start_scheduler() -> None:
    """启动调度器（在 lifespan 中调用）"""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler 已启动")


def shutdown_scheduler() -> None:
    """关闭调度器"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler 已关闭")
    _scheduler = None


# ── 定时任务注册 ──────────────────────────────────────────────────

def register_default_jobs() -> None:
    """注册默认的定时任务（仅注册，不立即执行）"""
    scheduler = get_scheduler()

    # 数据采集：每天 6:00
    if not scheduler.get_job("daily_data_collect"):
        scheduler.add_job(
            _job_daily_data_collect,
            trigger="cron", hour=6, minute=0,
            id="daily_data_collect",
            name="每日平台数据采集",
            replace_existing=True,
        )

    # 热门采集：每天 8:00
    if not scheduler.get_job("daily_hot_crawl"):
        scheduler.add_job(
            _job_daily_hot_crawl,
            trigger="cron", hour=8, minute=0,
            id="daily_hot_crawl",
            name="每日热门小说采集",
            replace_existing=True,
        )

    # 拆书学习：每周一 3:00
    if not scheduler.get_job("weekly_learn"):
        scheduler.add_job(
            _job_weekly_learn,
            trigger="cron", day_of_week="mon", hour=3, minute=0,
            id="weekly_learn",
            name="每周拆书学习",
            replace_existing=True,
        )

    # 提示词优化：每周日 4:00
    if not scheduler.get_job("weekly_prompt_opt"):
        scheduler.add_job(
            _job_weekly_prompt_opt,
            trigger="cron", day_of_week="sun", hour=4, minute=0,
            id="weekly_prompt_opt",
            name="每周提示词优化",
            replace_existing=True,
        )

    logger.info("已注册 %d 个默认定时任务", len(scheduler.get_jobs()))


# ── 任务实现 ─────────────────────────────────────────────────────

async def _job_daily_data_collect():
    logger.info("[定时] 每日数据采集开始")
    try:
        from app.services.data.collector import DataCollector
        collector = DataCollector()
        result = await collector.collect_all_scheduled()
        logger.info("[定时] 每日数据采集完成: %s", result)
    except Exception as e:
        logger.exception("[定时] 每日数据采集失败: %s", e)


async def _job_daily_hot_crawl():
    logger.info("[定时] 每日热门采集开始")
    try:
        from app.services.learning.hot_crawler import crawl_all_platforms
        result = await crawl_all_platforms()
        logger.info("[定时] 每日热门采集完成: %s", result)
    except Exception as e:
        logger.exception("[定时] 每日热门采集失败: %s", e)


async def _job_weekly_learn():
    logger.info("[定时] 每周拆书学习开始")
    try:
        from app.services.learning.knowledge_extractor import extract_knowledge_from_recent
        result = await extract_knowledge_from_recent(limit=10)
        logger.info("[定时] 每周拆书学习完成: 提取 %d 条知识", len(result))
    except Exception as e:
        logger.exception("[定时] 每周拆书学习失败: %s", e)


async def _job_weekly_prompt_opt():
    logger.info("[定时] 每周提示词优化开始")
    try:
        from app.services.learning.prompt_optimizer import optimize_prompts
        result = await optimize_prompts()
        logger.info("[定时] 每周提示词优化完成: 优化 %d 项", len(result))
    except Exception as e:
        logger.exception("[定时] 每周提示词优化失败: %s", e)
