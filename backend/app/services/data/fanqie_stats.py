"""番茄小说作者后台 API 数据采集

使用 httpx 直接调用番茄 API（无需 Playwright），依赖 LoginStateManager 存储的 cookies。

API 端点:
  - book_list: 获取作者所有作品列表 + 基础数据
  - book_common_v1: 获取单本书的详细统计 (stats_type=1 日维度)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx

from app.db.connection import SessionLocal
from app.models.publishing import PlatformStats
from app.services.publishing.login_manager import LoginStateManager

logger = logging.getLogger(__name__)

# ── API 端点 ──────────────────────────────────────────────────────

FANQIE_BOOK_LIST_API = "https://fanqienovel.com/api/author/stats/book_list/v0/"
FANQIE_BOOK_STATS_API = "https://fanqienovel.com/api/author/stats/book_common_v1/v0/"

COMMON_PARAMS = {
    "aid": "2503",
    "app_name": "muye_novel",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://fanqienovel.com/main/writer/data",
}


class FanqieStatsCollector:
    """通过 API 直接采集番茄作者后台数据"""

    def __init__(self):
        self.login_mgr = LoginStateManager("fanqie")

    def _get_cookie_header(self) -> str | None:
        """从 LoginStateManager 提取 cookie 字符串"""
        state = self.login_mgr.load_state()
        if not state or not state.get("cookies"):
            return None
        cookies = state["cookies"]
        # Playwright state cookies 格式: [{name, value, domain, ...}, ...]
        parts = []
        for c in cookies:
            if "fanqienovel.com" in c.get("domain", ""):
                parts.append(f"{c['name']}={c['value']}")
        return "; ".join(parts) if parts else None

    async def fetch_book_list(self) -> dict:
        """获取作者所有作品列表 + 基础统计"""
        cookie_header = self._get_cookie_header()
        if not cookie_header:
            return {"ok": False, "error": "番茄登录态不可用，请先在发布中心配置登录"}

        headers = {**HEADERS, "Cookie": cookie_header}
        params = {
            **COMMON_PARAMS,
            "page_count": "-1",
            "page_index": "0",
            "image_fmt_list": "160x214",
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(FANQIE_BOOK_LIST_API, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            if data.get("code") != 0:
                msg = data.get("message", "未知错误")
                logger.warning("番茄 book_list API 返回错误: %s", msg)
                return {"ok": False, "error": f"API 错误: {msg}"}

            books_raw = data.get("data", {}).get("stats_book_list", []) or data.get("data", {}).get("book_list", [])
            books = []
            for b in books_raw:
                # 封面：优先 thumb_url_list[0].main_url
                cover = ""
                thumb_list = b.get("thumb_url_list", [])
                if thumb_list and isinstance(thumb_list, list):
                    cover = thumb_list[0].get("main_url", "") if isinstance(thumb_list[0], dict) else ""
                if not cover:
                    cover = b.get("cover_url", "") or b.get("thumb_url", "") or b.get("thumb_uri", "")

                # read_count 可能是字符串
                read_count = b.get("read_count", 0)
                if isinstance(read_count, str):
                    read_count = int(read_count) if read_count.isdigit() else 0

                # creation_status: 1=连载 2=完结
                cs = b.get("creation_status", 0)
                cs_name = {1: "\u8FDE\u8F7D\u4E2D", 2: "\u5DF2\u5B8C\u7ED3"}.get(cs, b.get("creation_status_name", ""))

                books.append({
                    "book_id": str(b.get("book_id", "")),
                    "title": b.get("book_name", ""),
                    "cover_url": cover,
                    "word_count": int(b.get("word_number", 0) or b.get("word_count", 0)),
                    "read_count": read_count,
                    "favorite_count": int(b.get("favorite_count", 0) or b.get("follow_count", 0)),
                    "comment_count": int(b.get("comment_count", 0)),
                    "chapter_count": int(b.get("chapter_count", 0) or b.get("serial_count", 0)),
                    "creation_status": cs_name,
                    "category": b.get("category", "") or b.get("rank_name", ""),
                    "last_chapter_time": b.get("last_chapter_time", ""),
                })

            logger.info("番茄 book_list: 获取 %d 本书", len(books))
            return {"ok": True, "books": books}

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return {"ok": False, "error": "登录态已过期，请重新登录"}
            return {"ok": False, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.error("fetch_book_list 失败: %s", e)
            return {"ok": False, "error": str(e)}

    async def fetch_book_stats(self, book_id: str, stats_type: int = 1) -> dict:
        """获取单本书的详细统计

        番茄 book_common_v1 返回的是当前快照指标，不是日历史数据。
        包含: reader_uv_daily, shelf_cnt_daily, read_completion_rate, pursue_read_rate, rank_cat 等
        """
        cookie_header = self._get_cookie_header()
        if not cookie_header:
            return {"ok": False, "error": "\u767B\u5F55\u6001\u4E0D\u53EF\u7528"}

        headers = {**HEADERS, "Cookie": cookie_header}
        params = {
            **COMMON_PARAMS,
            "book_id": book_id,
            "stats_type": str(stats_type),
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(FANQIE_BOOK_STATS_API, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            if data.get("code") != 0:
                return {"ok": False, "error": data.get("message", "API \u9519\u8BEF")}

            sd = data.get("data", {})

            def _safe_int(v):
                if isinstance(v, int):
                    return v
                if isinstance(v, str):
                    return int(v) if v.lstrip("-").isdigit() else 0
                return 0

            stats = {
                "book_name": sd.get("book_name", ""),
                "reader_uv_daily": _safe_int(sd.get("reader_uv_daily", 0)),
                "reader_uv_daily_incr": sd.get("reader_uv_daily_incr", "0"),
                "reader_uv_14day": _safe_int(sd.get("reader_uv_14day_cnt", 0)),
                "reader_uv_14day_incr": sd.get("reader_uv_14day_incr", "0"),
                "shelf_cnt_daily": _safe_int(sd.get("shelf_cnt_daily", 0)),
                "shelf_cnt_daily_incr": sd.get("shelf_cnt_daily_incr", "0"),
                "read_completion_rate": sd.get("read_completion_rate", "0"),
                "pursue_read_rate": sd.get("pursue_read_rate", "0"),
                "mark_score": sd.get("mark_score", "0"),
                "mark_score_incr": sd.get("mark_score_incr", "0"),
                "rank_cat": _safe_int(sd.get("rank_cat", 0)),
                "risk_rate": _safe_int(sd.get("risk_rate", 0)),
                "main_intro": sd.get("main_intro", ""),
                "sub_intro": sd.get("sub_intro", ""),
                "update_time": sd.get("update_time", ""),
                "stats_col_time": sd.get("stats_col_time", ""),
            }

            return {"ok": True, "book_id": book_id, "stats": stats}

        except Exception as e:
            logger.error("fetch_book_stats(%s) \u5931\u8D25: %s", book_id, e)
            return {"ok": False, "error": str(e)}

    async def collect_and_save(self) -> dict:
        """采集所有书并写入 PlatformStats 表"""
        book_list_result = await self.fetch_book_list()
        if not book_list_result.get("ok"):
            return book_list_result

        books = book_list_result["books"]
        db = SessionLocal()
        saved = 0
        try:
            today = date.today()
            for book in books:
                book_id = book["book_id"]
                # 用 book_id 作为 novel_id（番茄侧 ID）
                existing = db.query(PlatformStats).filter(
                    PlatformStats.novel_id == book_id,
                    PlatformStats.platform == "fanqie",
                    PlatformStats.stat_date == today,
                ).first()

                reads = book.get("read_count", 0)
                favorites = book.get("favorite_count", 0)
                comments = book.get("comment_count", 0)

                if existing:
                    existing.reads = reads
                    existing.favorites = favorites
                    existing.comments = comments
                    existing.collected_at = datetime.now(tz=timezone.utc)
                else:
                    record = PlatformStats(
                        novel_id=book_id,
                        platform="fanqie",
                        stat_date=today,
                        reads=reads,
                        favorites=favorites,
                        comments=comments,
                        recommends=0,
                    )
                    db.add(record)
                    saved += 1

            db.commit()
            logger.info("番茄数据采集完成: %d 本, 新增 %d 条", len(books), saved)
            return {"ok": True, "books_count": len(books), "saved": saved}

        except Exception as e:
            db.rollback()
            logger.error("save fanqie stats failed: %s", e)
            return {"ok": False, "error": str(e)}
        finally:
            db.close()
