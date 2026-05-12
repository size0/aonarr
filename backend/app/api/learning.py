"""学习 Agent API 路由"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from datetime import datetime as _dt

from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from sqlalchemy import func

from app.db.connection import get_db, DATA_DIR
from app.models.learning import HotNovelMeta, HotNovelChapter, KnowledgeEntry, OptimizationLog

COVER_DIR = DATA_DIR / "covers"

router = APIRouter(prefix="/learning", tags=["learning"])
logger = logging.getLogger(__name__)

# 任务互斥锁 —— 同一类型任务不允许并发运行
_task_locks: dict[str, threading.Lock] = {
    "crawl": threading.Lock(),
    "learn": threading.Lock(),
    "optimize": threading.Lock(),
    "cover": threading.Lock(),
}

# ── 活动日志（内存环形缓冲） ──────────────────────────────────

_activity_log: deque[dict] = deque(maxlen=200)


def push_activity(msg: str, level: str = "info"):
    """全局推送一条活动日志"""
    _activity_log.append({
        "ts": _dt.now().strftime("%H:%M:%S"),
        "level": level,
        "msg": msg,
    })


@router.get("/activity-log")
def get_activity_log(since: int = Query(0, description="返回索引 > since 的日志")):
    """获取活动日志（轮询用）"""
    logs = list(_activity_log)
    if since > 0:
        logs = logs[since:] if since < len(logs) else []
    return {"total": len(_activity_log), "logs": logs}


# ── 番茄登录状态（复用发布中心登录态）──────────────────────────

@router.get("/fanqie/login-status")
async def fanqie_login_status():
    """检查番茄登录状态（读取发布中心 LoginStateManager）"""
    from app.services.learning.fanqie_direct import FanqieSession
    cookies = FanqieSession.get_cookies()
    if cookies:
        return {"logged_in": True, "cookie_count": len(cookies), "msg": "已通过发布中心登录"}
    return {"logged_in": False, "msg": "未登录，请在发布中心配置番茄登录态"}


# ── 统计 ───────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """返回学习中心各模块的统计"""
    knowledge_count = db.query(func.count(KnowledgeEntry.id)).scalar() or 0
    hot_novel_count = db.query(func.count(HotNovelMeta.id)).scalar() or 0
    chapter_count = db.query(func.count(HotNovelChapter.id)).scalar() or 0
    opt_log_count = db.query(func.count(OptimizationLog.id)).scalar() or 0

    crawling_count = (
        db.query(func.count(HotNovelMeta.id))
        .filter(HotNovelMeta.status == "crawling")
        .scalar() or 0
    )
    done_count = (
        db.query(func.count(HotNovelMeta.id))
        .filter(HotNovelMeta.status == "done")
        .scalar() or 0
    )

    last_crawl = (
        db.query(func.max(HotNovelMeta.crawled_at)).scalar()
    )

    return {
        "knowledge_count": knowledge_count,
        "hot_novel_count": hot_novel_count,
        "chapter_count": chapter_count,
        "opt_log_count": opt_log_count,
        "crawling_count": crawling_count,
        "done_count": done_count,
        "last_crawl_at": last_crawl.isoformat() if last_crawl else None,
    }


# ── 知识库 ──────────────────────────────────────────────────────

@router.get("/knowledge")
def list_knowledge(
    category: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """知识库列表"""
    q = db.query(KnowledgeEntry).order_by(KnowledgeEntry.quality_score.desc())
    if category:
        q = q.filter(KnowledgeEntry.category == category)
    rows = q.limit(limit).all()
    return [
        {
            "id": r.id,
            "category": r.category,
            "title": r.title,
            "content": json.loads(r.content) if r.content else {},
            "source_novel_id": r.source_novel_id,
            "source_file": r.source_file or "",
            "tags": json.loads(r.tags) if r.tags else [],
            "quality_score": r.quality_score,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/knowledge/categories")
def list_knowledge_categories(db: Session = Depends(get_db)):
    """知识库分类统计"""
    rows = (
        db.query(KnowledgeEntry.category, func.count(KnowledgeEntry.id))
        .group_by(KnowledgeEntry.category)
        .order_by(func.count(KnowledgeEntry.id).desc())
        .all()
    )
    return [{"category": cat, "count": cnt} for cat, cnt in rows]


@router.get("/knowledge/search")
def search_knowledge(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    category: str | None = Query(None),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """按标题/标签搜索知识库"""
    query = db.query(KnowledgeEntry).filter(
        (KnowledgeEntry.title.contains(q)) | (KnowledgeEntry.tags.contains(q))
    )
    if category:
        query = query.filter(KnowledgeEntry.category == category)
    rows = query.order_by(KnowledgeEntry.quality_score.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "category": r.category,
            "title": r.title,
            "tags": json.loads(r.tags) if r.tags else [],
            "quality_score": r.quality_score,
            "source_file": r.source_file or "",
        }
        for r in rows
    ]


@router.get("/knowledge/{entry_id}")
def get_knowledge_entry(entry_id: str, db: Session = Depends(get_db)):
    """知识条目详情"""
    entry = db.query(KnowledgeEntry).filter_by(id=entry_id).first()
    if not entry:
        raise HTTPException(404, "知识条目不存在")
    return {
        "id": entry.id,
        "category": entry.category,
        "title": entry.title,
        "content": json.loads(entry.content) if entry.content else {},
        "source_novel_id": entry.source_novel_id,
        "source_file": entry.source_file or "",
        "tags": json.loads(entry.tags) if entry.tags else [],
        "quality_score": entry.quality_score,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
    }


@router.delete("/knowledge/{entry_id}", status_code=204)
def delete_knowledge_entry(entry_id: str, db: Session = Depends(get_db)):
    """删除知识条目"""
    count = db.query(KnowledgeEntry).filter_by(id=entry_id).delete()
    if not count:
        raise HTTPException(404, "知识条目不存在")
    db.commit()


# ── 热门小说 ────────────────────────────────────────────────────

@router.get("/hot-novels")
def list_hot_novels(
    platform: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """热门小说元数据列表"""
    q = db.query(HotNovelMeta).order_by(HotNovelMeta.crawled_at.desc())
    if platform:
        q = q.filter(HotNovelMeta.platform == platform)
    rows = q.limit(limit).all()
    return [
        {
            "id": r.id,
            "platform": r.platform,
            "source_book_id": r.source_book_id,
            "title": r.title,
            "author": r.author,
            "genre": r.genre,
            "tags": json.loads(r.tags) if r.tags else [],
            "word_count": r.word_count,
            "chapter_count": r.chapter_count,
            "rating": r.rating,
            "read_count": r.read_count,
            "bookshelf_count": r.bookshelf_count,
            "created_at_source": r.created_at_source or "",
            "synopsis": r.synopsis[:200] if r.synopsis else "",
            "cover_url": r.cover_url or "",
            "rank_info": json.loads(r.rank_info) if r.rank_info else {},
            "source_url": r.source_url,
            "status": r.status,
            "crawled_at": r.crawled_at.isoformat() if r.crawled_at else None,
        }
        for r in rows
    ]


@router.get("/hot-novels/{novel_id}/chapters")
def list_novel_chapters(
    novel_id: str,
    db: Session = Depends(get_db),
):
    """返回某热门小说已采集的章节列表（不含正文）"""
    chapters = (
        db.query(HotNovelChapter)
        .filter_by(novel_id=novel_id)
        .order_by(HotNovelChapter.chapter_number)
        .all()
    )
    return [
        {
            "id": c.id,
            "chapter_number": c.chapter_number,
            "title": c.title,
            "word_count": c.word_count,
        }
        for c in chapters
    ]


@router.get("/hot-novels/{novel_id}/chapters/{chapter_id}")
def get_chapter_content(
    novel_id: str,
    chapter_id: str,
    db: Session = Depends(get_db),
):
    """返回某章节的完整正文"""
    ch = (
        db.query(HotNovelChapter)
        .filter_by(id=chapter_id, novel_id=novel_id)
        .first()
    )
    if not ch:
        raise HTTPException(404, "章节不存在")
    return {
        "id": ch.id,
        "chapter_number": ch.chapter_number,
        "title": ch.title,
        "content": ch.content,
        "word_count": ch.word_count,
    }


# ── 封面代理 ────────────────────────────────────────────────────

@router.get("/covers/{filename}")
def serve_cover(filename: str):
    """提供本地缓存的封面图片"""
    safe_name = filename.replace("..", "").replace("/", "").replace("\\", "")
    path = COVER_DIR / safe_name
    if not path.exists():
        raise HTTPException(404, "封面不存在")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/cover-proxy")
async def cover_proxy(url: str = Query(..., description="远程封面URL")):
    """代理远程封面图片，绕过防盗链"""
    import httpx
    if not url.startswith("http"):
        raise HTTPException(400, "无效URL")
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Referer": ""})
            if resp.status_code != 200:
                raise HTTPException(502, "远程图片获取失败")
            ct = resp.headers.get("content-type", "image/jpeg")
            from fastapi.responses import Response
            return Response(content=resp.content, media_type=ct,
                            headers={"Cache-Control": "public, max-age=86400"})
    except httpx.HTTPError:
        raise HTTPException(502, "远程图片获取失败")


# ── 优化日志 ────────────────────────────────────────────────────

@router.get("/optimization-logs")
def list_optimization_logs(
    limit: int = Query(30, le=100),
    db: Session = Depends(get_db),
):
    """优化日志"""
    rows = (
        db.query(OptimizationLog)
        .order_by(OptimizationLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "target": r.target,
            "description": r.description,
            "before_snapshot": json.loads(r.before_snapshot) if r.before_snapshot else {},
            "after_snapshot": json.loads(r.after_snapshot) if r.after_snapshot else {},
            "improvement_score": r.improvement_score,
            "applied": r.applied,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/optimization-logs/{log_id}/apply")
def apply_optimization(log_id: str, db: Session = Depends(get_db)):
    """标记优化为已应用"""
    log = db.query(OptimizationLog).filter_by(id=log_id).first()
    if not log:
        raise HTTPException(404, "优化日志不存在")
    log.applied = True
    db.commit()
    return {"ok": True, "log_id": log_id}


# ── 教程导入 ──────────────────────────────────────────────────────

@router.post("/tutorial/scan")
async def scan_tutorials(
    base_dir: str = Query(..., description="教程根目录绝对路径"),
):
    """扫描教程目录，返回可导入文件列表（不执行导入）"""
    from app.services.learning.tutorial_importer import scan_tutorial_dir
    files = scan_tutorial_dir(base_dir)
    # 按分类统计
    cat_stats: dict[str, int] = {}
    for f in files:
        cat_stats[f["category"]] = cat_stats.get(f["category"], 0) + 1
    return {
        "total": len(files),
        "by_category": cat_stats,
        "files": files[:200],  # 前端预览最多 200 条
    }


@router.post("/tutorial/import")
async def import_tutorials(
    background_tasks: BackgroundTasks,
    base_dir: str = Query(..., description="教程根目录绝对路径"),
    use_llm: bool = Query(True, description="是否用 LLM 提取结构化知识"),
    max_files: int = Query(100, ge=1, le=2000),
):
    """批量导入教程文件到知识库（后台异步执行）"""
    background_tasks.add_task(_run_tutorial_import, base_dir, use_llm, max_files)
    return {"status": "triggered", "message": f"教程导入任务已加入后台队列 (max={max_files})"}


@router.post("/tutorial/import-file")
async def import_single_tutorial(
    file_path: str = Query(..., description="单个教程文件绝对路径"),
    category: str | None = Query(None),
    use_llm: bool = Query(True),
):
    """导入单个教程文件到知识库（同步）"""
    from app.services.learning.tutorial_importer import import_file
    result = await import_file(file_path, category, use_llm)
    if result is None:
        raise HTTPException(400, "导入失败：文件不存在或内容过短")
    return result


# ── 手动触发 ────────────────────────────────────────────────────

@router.post("/trigger-cover-download")
async def trigger_cover_download(background_tasks: BackgroundTasks):
    """为已采集但封面缺失/过期的小说重新下载封面"""
    if not _task_locks["cover"].acquire(blocking=False):
        raise HTTPException(409, "封面下载任务正在运行中，请勿重复触发")
    push_activity("🖼️ 封面下载任务启动")
    background_tasks.add_task(_guarded_run, "cover", _run_cover_download)
    return {"status": "triggered", "message": "封面下载任务已加入后台队列"}


@router.post("/trigger-crawl")
async def trigger_crawl(background_tasks: BackgroundTasks):
    """手动触发热门采集"""
    if not _task_locks["crawl"].acquire(blocking=False):
        raise HTTPException(409, "热门采集任务正在运行中，请勿重复触发")
    push_activity("📡 热门采集任务启动")
    background_tasks.add_task(_guarded_run, "crawl", _run_crawl)
    return {"status": "triggered", "message": "热门采集任务已加入后台队列"}


@router.post("/trigger-learn")
async def trigger_learn(background_tasks: BackgroundTasks):
    """手动触发拆书学习"""
    if not _task_locks["learn"].acquire(blocking=False):
        raise HTTPException(409, "知识提取任务正在运行中，请勿重复触发")
    push_activity("🧠 知识提取任务启动")
    background_tasks.add_task(_guarded_run, "learn", _run_learn)
    return {"status": "triggered", "message": "知识提取任务已加入后台队列"}


@router.post("/trigger-optimize")
async def trigger_optimize(background_tasks: BackgroundTasks):
    """手动触发提示词优化"""
    if not _task_locks["optimize"].acquire(blocking=False):
        raise HTTPException(409, "提示词优化任务正在运行中，请勿重复触发")
    push_activity("⚡ 提示词优化任务启动")
    background_tasks.add_task(_guarded_run, "optimize", _run_optimize)
    return {"status": "triggered", "message": "提示词优化任务已加入后台队列"}


# ── 后台任务包装 ────────────────────────────────────────────────

def _guarded_run(task_key: str, fn):
    """包装器：确保任务结束后释放互斥锁"""
    try:
        fn()
    finally:
        _task_locks[task_key].release()


def _run_tutorial_import(base_dir: str, use_llm: bool, max_files: int):
    loop = asyncio.new_event_loop()
    try:
        from app.services.learning.tutorial_importer import import_batch
        result = loop.run_until_complete(import_batch(base_dir, use_llm=use_llm, max_files=max_files))
        logger.info("教程导入完成: %s", result)
    except Exception as e:
        logger.exception("教程导入失败: %s", e)
    finally:
        loop.close()


def _run_cover_download():
    """为已有远程封面 URL 的小说下载封面到本地"""
    import httpx
    from app.db.connection import SessionLocal
    from app.services.learning.hot_crawler import _download_cover

    loop = asyncio.new_event_loop()
    db = SessionLocal()
    try:
        rows = (
            db.query(HotNovelMeta)
            .filter(
                HotNovelMeta.cover_url != "",
                ~HotNovelMeta.cover_url.like("/api/%"),
                HotNovelMeta.source_book_id != "",
            )
            .all()
        )
        logger.info("需要下载封面的小说: %d 本", len(rows))
        push_activity(f"🖼️ 需下载封面: {len(rows)} 本")

        async def _batch():
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                done = 0
                for i, row in enumerate(rows):
                    local = await _download_cover(client, row.cover_url, row.source_book_id)
                    if local:
                        row.cover_url = local
                        done += 1
                    if (i + 1) % 10 == 0:
                        push_activity(f"🖼️ 封面进度: {i+1}/{len(rows)} (成功 {done})")
                db.commit()
                push_activity(f"✅ 封面下载完成: {done}/{len(rows)}")
                logger.info("封面下载完成: %d/%d", done, len(rows))

        loop.run_until_complete(_batch())
    except Exception as e:
        push_activity(f"❌ 封面下载失败: {e}", "error")
        logger.exception("封面下载失败: %s", e)
    finally:
        db.close()
        loop.close()


def _run_crawl():
    loop = asyncio.new_event_loop()
    try:
        from app.services.learning.hot_crawler import crawl_all_platforms
        push_activity("📡 开始采集热门小说...")
        loop.run_until_complete(crawl_all_platforms())
        push_activity("✅ 热门小说采集完成")
    except Exception as e:
        push_activity(f"❌ 热门采集失败: {e}", "error")
        logger.exception("热门采集失败: %s", e)
    finally:
        loop.close()


def _run_learn():
    loop = asyncio.new_event_loop()
    try:
        from app.services.learning.knowledge_extractor import extract_knowledge_from_recent
        push_activity("🧠 开始知识提取...")
        loop.run_until_complete(extract_knowledge_from_recent())
        push_activity("✅ 知识提取完成")
    except Exception as e:
        push_activity(f"❌ 知识提取失败: {e}", "error")
        logger.exception("知识提取失败: %s", e)
    finally:
        loop.close()


def _run_optimize():
    loop = asyncio.new_event_loop()
    try:
        from app.services.learning.prompt_optimizer import optimize_prompts
        push_activity("⚡ 开始提示词优化...")
        loop.run_until_complete(optimize_prompts())
        push_activity("✅ 提示词优化完成")
    except Exception as e:
        push_activity(f"❌ 提示词优化失败: {e}", "error")
        logger.exception("提示词优化失败: %s", e)
    finally:
        loop.close()
