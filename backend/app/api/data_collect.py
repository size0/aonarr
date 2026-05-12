"""数据采集 API 路由 — 数据概览 / 章节级统计 / 番茄API采集"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.models.novel import Novel, Chapter
from app.models.publishing import PlatformStats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["data"])


# ── 数据概览 ────────────────────────────────────────────────────

@router.get("/overview")
def data_overview(
    novel_id: str | None = Query(None, description="按小说筛选"),
    platform: str | None = Query(None),
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
):
    """数据概览：总阅读/收藏/推荐/评论 + 每日趋势"""
    since = date.today() - timedelta(days=days)
    q = db.query(PlatformStats).filter(PlatformStats.stat_date >= since)
    if novel_id:
        q = q.filter(PlatformStats.novel_id == novel_id)
    if platform:
        q = q.filter(PlatformStats.platform == platform)

    records = q.order_by(PlatformStats.stat_date.asc()).all()

    # 汇总
    total_reads = sum(r.reads for r in records)
    total_favorites = sum(r.favorites for r in records)
    total_recommends = sum(r.recommends for r in records)
    total_comments = sum(r.comments for r in records)
    total_revenue = sum(r.revenue or 0 for r in records)

    # 按日聚合
    daily: dict[str, dict] = {}
    for r in records:
        d = r.stat_date.isoformat()
        if d not in daily:
            daily[d] = {"date": d, "reads": 0, "favorites": 0, "recommends": 0, "comments": 0, "revenue": 0}
        daily[d]["reads"] += r.reads
        daily[d]["favorites"] += r.favorites
        daily[d]["recommends"] += r.recommends
        daily[d]["comments"] += r.comments
        daily[d]["revenue"] += r.revenue or 0

    # 填充缺失日期（0 值）
    trend = []
    current = since
    today = date.today()
    while current <= today:
        d = current.isoformat()
        trend.append(daily.get(d, {"date": d, "reads": 0, "favorites": 0, "recommends": 0, "comments": 0, "revenue": 0}))
        current += timedelta(days=1)

    return {
        "period_days": days,
        "totals": {
            "reads": total_reads,
            "favorites": total_favorites,
            "recommends": total_recommends,
            "comments": total_comments,
            "revenue": round(total_revenue, 2),
        },
        "trend": trend,
        "data_points": len(records),
    }


# ── 章节级统计 ──────────────────────────────────────────────────

@router.get("/chapter-stats")
def chapter_stats(
    novel_id: str = Query(..., description="小说ID"),
    db: Session = Depends(get_db),
):
    """章节级数据：各章字数/状态/张力分，用于漏斗和柱状图"""
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")

    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .order_by(Chapter.number)
        .all()
    )

    items = []
    cumulative_words = 0
    for ch in chapters:
        cumulative_words += ch.word_count or 0
        items.append({
            "number": ch.number,
            "title": ch.title or f"第{ch.number}章",
            "word_count": ch.word_count or 0,
            "cumulative_words": cumulative_words,
            "status": ch.status,
            "tension_score": ch.tension_score or 0,
        })

    return {
        "novel_id": novel_id,
        "novel_title": novel.title,
        "total_chapters": len(chapters),
        "total_words": novel.current_word_count or cumulative_words,
        "chapters": items,
    }


# ── 平台历史 ────────────────────────────────────────────────────

@router.get("/history")
def stat_history(
    novel_id: str = Query(...),
    platform: str | None = Query(None),
    limit: int = Query(60, le=365),
    db: Session = Depends(get_db),
):
    """获取指定小说的平台历史采集数据"""
    q = db.query(PlatformStats).filter(PlatformStats.novel_id == novel_id)
    if platform:
        q = q.filter(PlatformStats.platform == platform)
    records = q.order_by(PlatformStats.stat_date.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "platform": r.platform,
            "stat_date": r.stat_date.isoformat(),
            "reads": r.reads,
            "favorites": r.favorites,
            "recommends": r.recommends,
            "comments": r.comments,
            "rank": r.rank,
            "revenue": r.revenue,
        }
        for r in records
    ]


# ── 作品列表摘要 ────────────────────────────────────────────────

@router.get("/novels-summary")
def novels_summary(db: Session = Depends(get_db)):
    """返回所有作品的简要统计，供看板下拉选择"""
    novels = db.query(Novel).order_by(Novel.updated_at.desc()).all()
    result = []
    for n in novels:
        latest = (
            db.query(PlatformStats)
            .filter_by(novel_id=n.id)
            .order_by(PlatformStats.stat_date.desc())
            .first()
        )
        result.append({
            "id": n.id,
            "title": n.title,
            "genre": n.genre,
            "chapter_count": n.chapter_count,
            "word_count": n.current_word_count,
            "status": n.status,
            "latest_reads": latest.reads if latest else 0,
            "latest_favorites": latest.favorites if latest else 0,
        })
    return result


# ── 番茄 API 数据 ─────────────────────────────────────────────────

@router.get("/fanqie-books")
async def fanqie_books():
    """直接调用番茄 API 获取作者书单 + 数据（需已配置登录态）"""
    from app.services.data.fanqie_stats import FanqieStatsCollector
    collector = FanqieStatsCollector()
    result = await collector.fetch_book_list()
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "获取失败"))
    return result


@router.get("/fanqie-book-stats/{book_id}")
async def fanqie_book_stats(book_id: str, stats_type: int = Query(1, ge=1, le=2)):
    """获取单本书详细统计 (stats_type: 1=日维度, 2=章维度)"""
    from app.services.data.fanqie_stats import FanqieStatsCollector
    collector = FanqieStatsCollector()
    result = await collector.fetch_book_stats(book_id, stats_type)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "获取失败"))
    return result


@router.post("/trigger-collect")
async def trigger_collect():
    """同步触发番茄数据采集，直接返回结果"""
    from app.services.data.fanqie_stats import FanqieStatsCollector

    collector = FanqieStatsCollector()
    result = await collector.collect_and_save()
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "采集失败"))
    return result


@router.post("/import-cookies")
async def import_cookies(body: dict):
    """手动导入番茄 cookies（从浏览器 DevTools 复制的 cookie 字符串）

    body: { "platform": "fanqie", "cookie_string": "sessionid=xxx; sid_tt=yyy; ..." }
    """
    from app.services.publishing.login_manager import LoginStateManager

    platform = body.get("platform", "fanqie")
    cookie_str = body.get("cookie_string", "").strip()
    if not cookie_str:
        raise HTTPException(400, "cookie_string 不能为空")

    # 解析 "k1=v1; k2=v2" 格式为 Playwright-compatible cookies list
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".fanqienovel.com" if platform == "fanqie" else ".qidian.com",
            "path": "/",
        })

    if not cookies:
        raise HTTPException(400, "未解析出有效 cookie")

    sm = LoginStateManager(platform)
    sm.save_state(cookies)
    logger.info("手动导入 %s cookies: %d 个", platform, len(cookies))
    return {"ok": True, "message": f"已导入 {len(cookies)} 个 cookie", "status": sm.get_status()}


@router.get("/fanqie-debug")
async def fanqie_debug():
    """调试：查看番茄 API 原始响应结构"""
    import httpx
    from app.services.data.fanqie_stats import (
        FanqieStatsCollector, FANQIE_BOOK_LIST_API, COMMON_PARAMS, HEADERS,
    )
    collector = FanqieStatsCollector()
    cookie_header = collector._get_cookie_header()
    if not cookie_header:
        return {"error": "no cookies"}

    headers = {**HEADERS, "Cookie": cookie_header}
    params = {**COMMON_PARAMS, "page_count": "-1", "page_index": "0"}

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(FANQIE_BOOK_LIST_API, params=params, headers=headers)
        raw = resp.json()

    # 返回原始结构的 keys 和前几层
    def summarize(obj, depth=0):
        if depth > 2:
            return str(type(obj).__name__)
        if isinstance(obj, dict):
            return {k: summarize(v, depth + 1) for k, v in list(obj.items())[:20]}
        if isinstance(obj, list):
            return [summarize(obj[0], depth + 1)] if obj else []
        return obj

    # Also get first book's actual fields
    books = raw.get("data", {}).get("stats_book_list", []) or raw.get("data", {}).get("book_list", [])
    first_book = books[0] if books else {}
    first_book_id = str(first_book.get("book_id", "")) if first_book else ""

    # Also probe book_common_v1
    stats_raw = None
    if first_book_id:
        from app.services.data.fanqie_stats import FANQIE_BOOK_STATS_API
        async with httpx.AsyncClient(timeout=20) as client2:
            resp2 = await client2.get(FANQIE_BOOK_STATS_API, params={**COMMON_PARAMS, "book_id": first_book_id, "stats_type": "1"}, headers=headers)
            stats_raw = resp2.json()

    return {"status_code": resp.status_code, "code": raw.get("code"),
            "books_count": len(books),
            "first_book_keys": list(first_book.keys()) if first_book else [],
            "first_book": first_book,
            "stats_keys": list(stats_raw.keys()) if stats_raw and isinstance(stats_raw, dict) else None,
            "stats_data_keys": list(stats_raw.get("data", {}).keys()) if stats_raw else None,
            "stats_data": stats_raw.get("data") if stats_raw else None}


@router.get("/cookie-status")
def cookie_status():
    """检查各平台 cookie/登录态状态"""
    from app.services.publishing.login_manager import LoginStateManager

    result = {}
    for p in ("fanqie", "qidian"):
        sm = LoginStateManager(p)
        result[p] = sm.get_status()
    return result
