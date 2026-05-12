"""热门小说采集 — 三通道采集

优先级:
  1. 本地直连番茄 API（搜索 + 书库浏览，无需外部服务）
  2. Tomato Downloader（可选增强，能解密章节正文）
  3. 番茄书库 API 兜底

步骤:
  1. book_list   — 从搜索 API / 书库列表 API 拿到书单元数据
  2. page detail — 解析书详情页 HTML，拿到章节目录
  3. reader      — 逐章抓取正文（优先 Tomato Downloader，回退直连）

写入 HotNovelMeta + HotNovelChapter 表。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote as urlquote

import httpx

from app.db.connection import SessionLocal, DATA_DIR
from app.models.learning import HotNovelMeta, HotNovelChapter
from app.api.learning import push_activity

COVER_DIR = DATA_DIR / "covers"
COVER_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


# ── 字体加密解码 ─────────────────────────────────────────────────

def _decode_font_number(raw: Any) -> int:
    """解码番茄字体加密数字。

    番茄 API 会把数字字段返回成私有 Unicode 字符（如 \ue49e\ue4b0\ue4b0），
    每次请求的映射表不同，但字符都在 PUA 区间 (\ue000-\uf8ff)。
    无法在没有字体文件的情况下精确解码，所以直接跳过这些字段返回 0。
    """
    if isinstance(raw, (int, float)):
        return int(raw)
    if not isinstance(raw, str):
        return 0
    # 如果是正常数字字符串
    cleaned = raw.replace(",", "").strip()
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        pass
    # 包含 PUA 字符 → 字体加密，无法解码，返回 0
    if any("\ue000" <= c <= "\uf8ff" for c in cleaned):
        logger.debug("字体加密数字跳过: %r", raw)
        return 0
    return 0


def _has_pua(text: str) -> bool:
    """检测文本是否包含 PUA 字体加密字符"""
    return any("\ue000" <= c <= "\uf8ff" for c in text)


def _parse_fanqie_book(raw: dict, rank_type: str, rank_index: int) -> dict | None:
    """Parse a Fanqie rank/list item into the normalized hot novel shape.

    Kept as a small compatibility helper for tests and older callers while the
    newer crawler uses fanqie_direct for most metadata collection.
    """
    if not isinstance(raw, dict) or not raw:
        return None
    data = raw.get("book_data") if isinstance(raw.get("book_data"), dict) else raw
    title = data.get("book_name") or data.get("bookName") or data.get("title") or ""
    book_id = str(data.get("book_id") or data.get("bookId") or data.get("id") or "")
    if not title:
        return None

    tags_raw = data.get("tag") or data.get("tags") or ""
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in re.split(r"[,，/、\s]+", tags_raw) if t.strip()]
    elif isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    else:
        tags = []

    genre = data.get("category") or data.get("genre") or data.get("category_name") or ""
    rating = data.get("score") or data.get("rating")
    try:
        rating = float(rating) if rating not in ("", None) else None
    except (TypeError, ValueError):
        rating = None

    return {
        "platform": "fanqie",
        "source_book_id": book_id,
        "title": title,
        "author": data.get("author") or data.get("author_name") or "",
        "genre": genre,
        "tags": tags,
        "word_count": _decode_font_number(data.get("word_number") or data.get("word_count") or 0),
        "chapter_count": _decode_font_number(data.get("chapter_count") or data.get("chapter_number") or 0),
        "read_count": _decode_font_number(data.get("read_count") or data.get("readNumber") or 0),
        "bookshelf_count": _decode_font_number(data.get("bookshelf_count") or data.get("add_bookshelf_count") or 0),
        "rating": rating,
        "created_at_source": data.get("creation_status") or data.get("creationStatus") or "",
        "synopsis": data.get("abstract") or data.get("description") or data.get("synopsis") or "",
        "cover_url": data.get("thumb_url") or data.get("thumbUrl") or data.get("cover_url") or "",
        "rank_info": {rank_type: rank_index},
        "source_url": f"https://fanqienovel.com/page/{book_id}" if book_id else "",
    }


def _parse_qidian_html(html: str, rank_type: str) -> list[dict]:
    """Parse a small subset of Qidian rank HTML used by the legacy tests."""
    if not html:
        return []
    blocks = re.findall(r'<div[^>]+class=["\'][^"\']*book-list[^"\']*["\'][^>]*>(.*?)</div>', html, flags=re.S | re.I)
    if not blocks:
        return []

    rows: list[dict] = []
    for idx, block in enumerate(blocks, 1):
        title_match = re.search(r'<h2[^>]*>\s*<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, flags=re.S | re.I)
        if not title_match:
            continue
        href, title_html = title_match.groups()
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        if not title:
            continue
        author_match = re.search(r'class=["\'][^"\']*author[^"\']*["\'][^>]*>.*?<a[^>]*>(.*?)</a>', block, flags=re.S | re.I)
        genre_match = re.search(r'class=["\'][^"\']*go-sub-type[^"\']*["\'][^>]*>(.*?)</a>', block, flags=re.S | re.I)
        author = re.sub(r"<[^>]+>", "", author_match.group(1)).strip() if author_match else ""
        genre = re.sub(r"<[^>]+>", "", genre_match.group(1)).strip() if genre_match else ""
        source_url = "https:" + href if href.startswith("//") else href
        rows.append({
            "platform": "qidian",
            "source_book_id": re.sub(r"\D+", "", href),
            "title": title,
            "author": author,
            "genre": genre,
            "tags": [],
            "word_count": 0,
            "chapter_count": 0,
            "read_count": 0,
            "bookshelf_count": 0,
            "rating": None,
            "created_at_source": "",
            "synopsis": "",
            "cover_url": "",
            "rank_info": {rank_type: idx},
            "source_url": source_url,
        })
    return rows


# ── 常量 ──────────────────────────────────────────────────────────

FANQIE_LIBRARY_API = "https://fanqienovel.com/api/author/library/book_list/v0/"
FANQIE_PAGE_URL = "https://fanqienovel.com/page/{book_id}"
FANQIE_READER_URL = "https://fanqienovel.com/reader/{chapter_id}"

# Tomato Downloader 开关 (ENABLE_TOMATO_DL=true/1/yes 启用；默认关闭)
ENABLE_TOMATO_DL = os.getenv("ENABLE_TOMATO_DL", "false").lower() in ("true", "1", "yes")
# Tomato Downloader Web UI（从环境变量读取）
TOMATO_DL_BASE = os.getenv("TOMATO_DL_BASE", "http://127.0.0.1:18424")
TOMATO_DL_PASSWORD = os.getenv("TOMATO_DL_PASSWORD", "")
# JSONL 数据直读（nginx 静态文件服务）
TOMATO_DATA_BASE = os.getenv("TOMATO_DATA_BASE", "http://127.0.0.1:18425")

# 搜索关键词列表 — 覆盖热门品类，优先抓新书/热度高的
HOT_SEARCH_KEYWORDS = [
    "玄幻", "都市", "科幻", "仙侠", "悬疑", "历史", "游戏",
    "末日", "穿越", "重生", "系统", "赘婿", "战神", "神豪",
    "修仙", "无敌", "高武", "诸天", "灵气复苏", "废材逆袭",
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
JSON_HEADERS = {**COMMON_HEADERS, "Accept": "application/json, text/plain, */*"}

# 每次采集最多抓取的书数 & 每本书最多抓取的章节数
MAX_BOOKS_PER_CRAWL = 50
MAX_PAGES = 5  # 最多翻 5 页 = 250 本
MAX_CHAPTERS_PER_BOOK = 30
# 请求间隔 (秒)，避免被限流
CRAWL_DELAY = 1.5
# Tomato Downloader 下载任务间隔 (秒)，避免限流
TD_DOWNLOAD_INTERVAL = 10  # 秒，自己服务器无需长等
MAX_BOOKS_PER_DOWNLOAD = 10


# ── Tomato Downloader 搜索通道（优先）─────────────────────────────

async def _tomato_dl_login(client: httpx.AsyncClient) -> bool:
    """登录 Tomato Downloader Web UI"""
    try:
        resp = await client.post(
            f"{TOMATO_DL_BASE}/api/login",
            json={"password": TOMATO_DL_PASSWORD},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                logger.info("Tomato Downloader 登录成功")
                return True
        logger.warning("Tomato Downloader 登录失败: %s", resp.text[:100])
        return False
    except Exception as e:
        logger.warning("Tomato Downloader 不可用: %s", e)
        return False


async def crawl_via_tomato_search(
    client: httpx.AsyncClient,
    keywords: list[str] | None = None,
    max_per_keyword: int = 60,
) -> list[dict]:
    """通过 Tomato Downloader 搜索 API 采集热门小说元数据（明文）"""
    if not await _tomato_dl_login(client):
        return []

    kw_list = keywords or HOT_SEARCH_KEYWORDS
    seen_ids: set[str] = set()
    novels: list[dict] = []

    for kw in kw_list:
        try:
            kw_items: list[dict] = []
            for page in range(1, 4):  # 翻 3 页，每页约 20 条
                resp = await client.get(
                    f"{TOMATO_DL_BASE}/api/search",
                    params={"q": kw, "page": page},
                    timeout=30,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                page_items = data.get("items", [])
                if not page_items:
                    break
                kw_items.extend(page_items)
                await asyncio.sleep(2)

            for item in kw_items[:max_per_keyword]:
                book_id = str(item.get("book_id", ""))
                if not book_id or book_id in seen_ids:
                    continue
                seen_ids.add(book_id)

                raw = item.get("raw", {})
                title = raw.get("book_name", "") or item.get("title", "")
                author = item.get("author", "") or raw.get("author", "")
                wc_raw = raw.get("word_count", "")
                sc_raw = raw.get("serial_count", "")
                # 阅读/收藏/评分
                rc_raw = raw.get("read_count_all", raw.get("read_count", ""))
                bs_raw = raw.get("all_bookshelf_count", "")
                score_raw = raw.get("score", "")
                created_src = raw.get("create_time", "")
                novels.append({
                    "platform": "fanqie",
                    "source_book_id": book_id,
                    "title": title,
                    "author": author,
                    "genre": raw.get("category", ""),
                    "tags": [t.strip() for t in raw.get("tag", "").split(",") if t.strip()] if raw.get("tag") else [],
                    "word_count": int(wc_raw) if str(wc_raw).isdigit() else 0,
                    "chapter_count": int(sc_raw) if str(sc_raw).isdigit() else 0,
                    "read_count": int(rc_raw) if str(rc_raw).isdigit() else 0,
                    "bookshelf_count": int(bs_raw) if str(bs_raw).isdigit() else 0,
                    "rating": float(score_raw) if score_raw and score_raw != "" else None,
                    "created_at_source": created_src,
                    "synopsis": raw.get("abstract", raw.get("book_abstract_v2", "")),
                    "cover_url": raw.get("thumb_url", ""),
                    "source_url": f"https://fanqienovel.com/page/{book_id}",
                })

            logger.info("搜索 [%s] 得到 %d 本 (累计 %d)", kw, len(kw_items), len(novels))
            await asyncio.sleep(3)

        except Exception as e:
            logger.warning("搜索 [%s] 失败: %s", kw, e)
            continue

    logger.info("Tomato Downloader 共采集 %d 本去重小说", len(novels))
    return novels


# ── 第 1 步: 书库列表（兜底）───────────────────────────────────────

async def crawl_fanqie_library(
    client: httpx.AsyncClient,
    page_count: int = MAX_BOOKS_PER_CRAWL,
    page_index: int = 0,
    gender: int = -1,
    category_id: int = -1,
    sort: int = 0,
) -> list[dict]:
    """从番茄书库 API 获取书单"""
    params = {
        "page_count": page_count,
        "page_index": page_index,
        "gender": gender,
        "category_id": category_id,
        "creation_status": -1,
        "word_count": -1,
        "book_type": -1,
        "sort": sort,
    }
    try:
        resp = await client.get(FANQIE_LIBRARY_API, params=params, headers=JSON_HEADERS)
        resp.raise_for_status()
        data = resp.json()
        books_raw = data.get("data", {}).get("book_list", [])
        novels: list[dict] = []
        for b in books_raw:
            book_id = str(b.get("book_id", ""))
            if not book_id:
                continue
            novels.append({
                "platform": "fanqie",
                "source_book_id": book_id,
                "title": b.get("book_name", ""),
                "author": b.get("author", ""),
                "genre": b.get("category", "") or b.get("creation_status_name", ""),
                "tags": [t for t in (b.get("tag", "") or "").split(",") if t],
                "word_count": _decode_font_number(b.get("word_count", 0)),
                "chapter_count": _decode_font_number(b.get("chapter_count", 0)),
                "synopsis": b.get("abstract", ""),
                "cover_url": b.get("thumb_url", ""),
                "source_url": f"https://fanqienovel.com/page/{book_id}",
            })
        logger.info("番茄书库采集到 %d 本 (page=%d)", len(novels), page_index)
        return novels
    except Exception as e:
        logger.error("番茄书库 API 失败: %s", e)
        return []


# ── Tomato Downloader 章节下载通道 ─────────────────────────────────

def _strip_html(html_content: str) -> str:
    """从 Tomato Downloader 的 HTML 内容中提取纯文本"""
    # 移除所有 HTML 标签
    text = re.sub(r'<[^>]+>', '\n', html_content)
    # 合并多余空行，保留段落结构
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)


async def _td_submit_download(
    client: httpx.AsyncClient,
    book_id: str,
) -> int | None:
    """向 Tomato Downloader 提交下载任务，返回 job_id"""
    try:
        resp = await client.post(
            f"{TOMATO_DL_BASE}/api/jobs",
            json={"book_id": str(book_id)},
            timeout=15,
        )
        if resp.status_code == 429:
            logger.warning("Tomato Downloader 限流，稍后再试")
            return None
        if resp.status_code != 200:
            logger.warning("提交下载任务失败: %d %s", resp.status_code, resp.text[:100])
            return None
        data = resp.json()
        job_id = data.get("id")
        logger.info("下载任务已提交: book_id=%s job_id=%s", book_id, job_id)
        return job_id
    except Exception as e:
        logger.warning("提交下载任务异常: %s", e)
        return None


async def _td_wait_job(
    client: httpx.AsyncClient,
    book_id: str,
    max_wait: int = 120,
    poll_interval: int = 3,
) -> bool:
    """等待 Tomato Downloader 下载任务完成"""
    for _ in range(max_wait // poll_interval):
        await asyncio.sleep(poll_interval)
        try:
            resp = await client.get(f"{TOMATO_DL_BASE}/api/jobs", timeout=10)
            jobs = resp.json().get("items", [])
            active = [j for j in jobs if j.get("book_id") == str(book_id)]
            if not active:
                # 任务已完成（从队列移除）
                return True
            job = active[0]
            state = job.get("state", "")
            progress = job.get("progress", {})
            saved = progress.get("saved_chapters", 0)
            total = progress.get("chapter_total", 0)
            logger.debug("下载进度: %s/%s state=%s", saved, total, state)
            if state in ("failed", "error"):
                logger.error("下载任务失败: %s", job.get("message", ""))
                return False
            # 如果前30章已下载完，提前返回（不等全书下完）
            if saved >= MAX_CHAPTERS_PER_BOOK:
                return True
        except Exception as e:
            logger.warning("查询下载进度失败: %s", e)
    logger.warning("等待下载超时: book_id=%s", book_id)
    return False


async def _td_list_downloaded(client: httpx.AsyncClient) -> list[dict]:
    """列出 Tomato Downloader 上已下载的书"""
    try:
        r = await client.get(f"{TOMATO_DL_BASE}/api/updates", timeout=30)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("no_updates", []) + data.get("updates", [])
    except Exception as e:
        logger.warning("TD list downloads 失败: %s", e)
        return []


async def _td_find_folder(
    client: httpx.AsyncClient,
    book_id: str,
) -> str | None:
    """找到 TD 下载目录名 — 优先 API，回退 nginx 目录猜测"""
    # 方法1: 从 TD preview 拿书名，拼目录名尝试 nginx（快）
    try:
        resp = await client.get(
            f"{TOMATO_DL_BASE}/api/preview/{book_id}", timeout=10,
        )
        if resp.status_code == 200:
            title = resp.json().get("book_name", "")
            if title:
                folder = f"{book_id}_{title}"
                check = await client.head(
                    f"{TOMATO_DATA_BASE}/{urlquote(folder, safe='')}/downloaded_chapters.jsonl",
                    timeout=5,
                )
                if check.status_code == 200:
                    return folder
    except Exception:
        pass

    # 方法3: 直接用 book_id 前缀试（有些目录只用 book_id）
    try:
        folder = str(book_id)
        check = await client.head(
            f"{TOMATO_DATA_BASE}/{urlquote(folder, safe='')}/downloaded_chapters.jsonl",
            timeout=5,
        )
        if check.status_code == 200:
            return folder
    except Exception:
        pass

    return None


async def _td_read_chapters(
    client: httpx.AsyncClient,
    book_id: str,
    max_chapters: int = MAX_CHAPTERS_PER_BOOK,
) -> list[dict]:
    """通过 HTTP 从 nginx 静态服务读取 TD 下载的 JSONL 明文章节"""
    try:
        folder = await _td_find_folder(client, book_id)
        if not folder:
            logger.debug("TD 未下载 book_id=%s", book_id)
            return []

        jsonl_url = f"{TOMATO_DATA_BASE}/{urlquote(folder, safe='')}/downloaded_chapters.jsonl"
        resp = await client.get(jsonl_url, timeout=30)
        if resp.status_code != 200:
            logger.warning("JSONL 读取失败 %d: %s", resp.status_code, jsonl_url)
            return []

        chapters = []
        for i, line in enumerate(resp.text.strip().split('\n')):
            if i >= max_chapters:
                break
            if not line.strip():
                continue
            try:
                ch = json.loads(line)
                content = _strip_html(ch.get("content", ""))
                if content:
                    chapters.append({
                        "chapter_number": i + 1,
                        "title": ch.get("title", f"第{i+1}章"),
                        "content": content,
                        "source_chapter_id": str(ch.get("id", "")),
                    })
            except json.JSONDecodeError:
                continue

        logger.info("HTTP 读取 book_id=%s 章节: %d 章", book_id, len(chapters))
        if chapters:
            push_activity(f"📚 TD 读取 {len(chapters)} 章明文章节 (book_id={book_id[:8]}...)")
        return chapters

    except Exception as e:
        logger.error("读取章节失败: %s", e)
        return []


async def _refresh_pua_metadata(
    td_client: httpx.AsyncClient,
    db,
    limit: int = 200,
) -> int:
    """用 TD preview API 修复 PUA 乱码的标题/作者"""
    # 分批加载而非全表 .all()，只扫有 source_book_id 的行
    batch_size = 500
    pua_rows: list[HotNovelMeta] = []
    offset = 0
    while len(pua_rows) < limit:
        batch = (
            db.query(HotNovelMeta)
            .filter(HotNovelMeta.source_book_id != "")
            .offset(offset).limit(batch_size)
            .all()
        )
        if not batch:
            break
        for r in batch:
            if _has_pua(r.title or "") or _has_pua(r.author or "") or _has_pua(r.synopsis or ""):
                pua_rows.append(r)
                if len(pua_rows) >= limit:
                    break
        offset += batch_size
    if not pua_rows:
        return 0
    push_activity(f"🔧 修复 {len(pua_rows)} 本 PUA 乱码元数据...")
    fixed = 0
    for i, row in enumerate(pua_rows):
        try:
            resp = await td_client.get(
                f"{TOMATO_DL_BASE}/api/preview/{row.source_book_id}",
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            new_title = data.get("book_name", "")
            new_author = data.get("author", "")
            if new_title and not _has_pua(new_title):
                row.title = new_title
            if new_author and not _has_pua(new_author):
                row.author = new_author
            desc = data.get("description", "")
            if desc and not _has_pua(desc):
                row.synopsis = desc
            if data.get("score"):
                try:
                    row.rating = float(data["score"])
                except (ValueError, TypeError):
                    pass
            wc = data.get("word_count")
            if wc and str(wc).isdigit():
                row.word_count = int(wc)
            cc = data.get("chapter_count")
            if cc and str(cc).isdigit():
                row.chapter_count = int(cc)
            fixed += 1
            if (i + 1) % 50 == 0:
                db.commit()
                push_activity(f"  ... 已修复 {i + 1}/{len(pua_rows)}")
        except Exception as e:
            logger.debug("preview 失败 %s: %s", row.source_book_id, e)
            continue
        await asyncio.sleep(0.3)

    db.commit()
    push_activity(f"✅ 修复 {fixed}/{len(pua_rows)} 本元数据")
    return fixed


# ── 采集子步骤 ────────────────────────────────────────────────────

META_REFRESH_INTERVAL = 6 * 3600          # 6h 内不重采元数据
MIN_SEARCH_BEFORE_LIBRARY = 100           # 搜索不足此数则补书库
MIN_CONTENT_LEN = 50                      # 章节正文最短有效长度
MAX_PUA_RATIO = 0.15                      # 字体解码后 PUA 残留比率上限
MIN_COVER_BYTES = 500                     # 封面文件最小有效字节


def _should_skip_meta(db) -> tuple[bool, int, float]:
    """增量检查：最近是否采集过。返回 (skip, pending_count, elapsed_s)。"""
    last = db.query(HotNovelMeta.crawled_at).order_by(
        HotNovelMeta.crawled_at.desc()
    ).first()
    pending = db.query(HotNovelMeta).filter(
        HotNovelMeta.status == "meta", HotNovelMeta.source_book_id != ""
    ).count()
    elapsed_s = 999999.0
    if last and last[0]:
        ts = last[0]
        now = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        elapsed_s = (now - ts).total_seconds()
    return elapsed_s < META_REFRESH_INTERVAL, pending, elapsed_s


async def _collect_novel_metadata(
    client: httpx.AsyncClient,
    td_client: httpx.AsyncClient,
) -> list[dict]:
    """三通道采集元数据：直连搜索 → TD 搜索 → 书库兜底。"""
    from app.services.learning.fanqie_direct import search_fanqie, browse_fanqie_library

    all_novels: list[dict] = []

    # 通道1: 本地直连番茄搜索
    try:
        push_activity("📡 通道1: 本地直连番茄搜索...")
        all_novels = await search_fanqie(client, progress_callback=push_activity)
        if all_novels:
            push_activity(f"✅ 本地直连搜索到 {len(all_novels)} 本")
    except Exception as e:
        push_activity(f"⚠️ 本地搜索失败: {e}", "warning")
        logger.warning("本地直连搜索失败: %s", e)

    # 补充: 本地书库浏览
    if len(all_novels) < MIN_SEARCH_BEFORE_LIBRARY:
        try:
            push_activity("📡 本地直连番茄书库浏览...")
            library_novels = await browse_fanqie_library(client, progress_callback=push_activity)
            existing_ids = {n["source_book_id"] for n in all_novels}
            new = [n for n in library_novels if n["source_book_id"] not in existing_ids]
            all_novels.extend(new)
            if new:
                push_activity(f"✅ 书库补充 {len(new)} 本 (总计 {len(all_novels)})")
        except Exception as e:
            logger.warning("书库浏览失败: %s", e)

    # 通道2: Tomato Downloader（可选增强，需 ENABLE_TOMATO_DL=true）
    if not all_novels and ENABLE_TOMATO_DL:
        try:
            push_activity("📡 通道2: 尝试 Tomato Downloader...")
            td_novels = await crawl_via_tomato_search(td_client)
            if td_novels:
                all_novels = td_novels
                push_activity(f"✅ Tomato Downloader 采集到 {len(td_novels)} 本")
        except Exception as e:
            push_activity(f"⚠️ Tomato Downloader 不可用: {e}", "warning")

    # 通道3: 番茄书库 API 兜底
    if not all_novels:
        push_activity("📡 通道3: 番茄书库 API 兜底...")
        for page_idx in range(MAX_PAGES):
            page_novels = await crawl_fanqie_library(client, page_index=page_idx)
            if not page_novels:
                break
            all_novels.extend(page_novels)
            await asyncio.sleep(CRAWL_DELAY)
        if all_novels:
            push_activity(f"✅ 书库兜底采集到 {len(all_novels)} 本")

    return all_novels


async def _fetch_chapters_for_book(
    client: httpx.AsyncClient,
    td_client: httpx.AsyncClient,
    td_available: bool,
    book_id: str,
    title: str,
    font_decoder,
    fetch_reader_chapter,
    get_chapter_list,
) -> list[dict]:
    """单本三方案章节抓取：A直连解码 → B TD读取 → C TD下载。"""
    chapters: list[dict] = []

    # 方案A: 直连 + 字体解码
    ch_list = await get_chapter_list(client, book_id)
    if ch_list:
        cap = min(len(ch_list), MAX_CHAPTERS_PER_BOOK)
        push_activity(f"🔤 [{title}] 直连字体解码 ({cap} 章)...")
        for ch_info in ch_list[:MAX_CHAPTERS_PER_BOOK]:
            try:
                content, page_title, ratio, _src, _warns = await fetch_reader_chapter(
                    client, ch_info["chapter_id"], decoder=font_decoder,
                )
                if content and len(content) > MIN_CONTENT_LEN and ratio <= MAX_PUA_RATIO:
                    chapters.append({
                        "chapter_number": ch_info["chapter_number"],
                        "title": ch_info["title"] or page_title,
                        "content": content,
                        "source_chapter_id": ch_info["chapter_id"],
                    })
            except Exception as e:
                logger.debug("字体解码章节失败 %s: %s", ch_info["chapter_id"], e)
            await asyncio.sleep(0.5)
        if chapters:
            push_activity(f"✅ [{title}] 字体解码成功: {len(chapters)} 章")

    # 方案B: TD 已下载的 JSONL
    if not chapters and td_available:
        push_activity(f"📚 [{title}] 回退 TD 读取...")
        chapters = await _td_read_chapters(td_client, book_id)

    # 方案C: TD 提交新下载
    if not chapters and td_available:
        push_activity(f"📡 [{title}] 回退 TD 下载...")
        job_id = await _td_submit_download(td_client, book_id)
        if job_id is not None:
            ok = await _td_wait_job(td_client, book_id)
            if ok:
                chapters = await _td_read_chapters(td_client, book_id)

    return chapters


def _save_chapters_to_db(db, novel_id: str, chapters: list[dict]) -> int:
    """去重写入章节，返回新增数。"""
    saved = 0
    for ch_info in chapters[:MAX_CHAPTERS_PER_BOOK]:
        existing = (
            db.query(HotNovelChapter)
            .filter_by(novel_id=novel_id, source_chapter_id=ch_info["source_chapter_id"])
            .first()
        )
        if existing:
            continue
        db.add(HotNovelChapter(
            novel_id=novel_id,
            source_chapter_id=ch_info["source_chapter_id"],
            chapter_number=ch_info["chapter_number"],
            title=ch_info.get("title", ""),
            content=ch_info["content"],
            word_count=len(ch_info["content"]),
        ))
        saved += 1
    return saved


# ── 统一采集入口 ─────────────────────────────────────────────────

async def crawl_all_platforms() -> dict[str, int]:
    """采集番茄书库 → 写入元数据 → 自动抓前 N 章正文

    优先级: 本地直连 → Tomato Downloader → 番茄书库兜底
    """
    db = SessionLocal()
    td_transport = httpx.AsyncHTTPTransport(retries=2)
    td_client = httpx.AsyncClient(
        transport=td_transport, timeout=60, follow_redirects=True,
    )
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            saved_meta = 0

            # ── 增量检查 ──
            skip_meta, pending, elapsed_s = _should_skip_meta(db)

            if skip_meta:
                push_activity(
                    f"📋 {int(elapsed_s // 60)} 分钟前已采集 "
                    f"(待下载 {pending} 本)，跳过元数据重采"
                )
            else:
                all_novels = await _collect_novel_metadata(client, td_client)
                await _download_covers_batch(client, all_novels)
                saved_meta = _save_novels(db, all_novels)
                push_activity(f"💾 元数据写入 {saved_meta} 本 (共采集 {len(all_novels)} 本)")
                logger.info("元数据写入 %d 本 (共采集 %d 本)", saved_meta, len(all_novels))

            # ── 下载章节正文 ──
            from app.services.learning.fanqie_direct import get_chapter_list, FanqieSession

            if FanqieSession.is_logged_in():
                push_activity("🍅 番茄已登录，章节内容可直接获取")
            else:
                push_activity("⚠️ 番茄未登录，章节获取可能为空（建议登录）", "warning")

            td_available = False
            if ENABLE_TOMATO_DL:
                td_available = await _tomato_dl_login(td_client)
                if td_available:
                    push_activity("🔗 Tomato Downloader 可用，用于章节下载")
                    await _refresh_pua_metadata(td_client, db)
                else:
                    push_activity("⚠️ Tomato Downloader 不可用，仅使用本地直连", "warning")
            else:
                push_activity("📖 使用本地直连获取章节（TD 已禁用）")

            meta_rows = (
                db.query(HotNovelMeta)
                .filter(HotNovelMeta.status == "meta", HotNovelMeta.source_book_id != "")
                .order_by(HotNovelMeta.crawled_at.desc())
                .limit(MAX_BOOKS_PER_DOWNLOAD)
                .all()
            )
            chapters_total = 0

            from scripts.fanqie_learning_scraper import FontShapeDecoder, fetch_reader_chapter
            font_decoder = FontShapeDecoder()

            for row in meta_rows:
                try:
                    row.status = "crawling"
                    db.commit()
                    push_activity(f"📖 正在采集 [{row.title}] 章节...")

                    chapters = await _fetch_chapters_for_book(
                        client, td_client, td_available,
                        row.source_book_id, row.title,
                        font_decoder, fetch_reader_chapter, get_chapter_list,
                    )

                    if not chapters:
                        row.status = "meta"
                        db.commit()
                        push_activity(f"⚠️ [{row.title}] 暂无可用章节", "warning")
                        continue

                    ch_saved = _save_chapters_to_db(db, row.id, chapters)
                    row.status = "done"
                    row.chapter_count = ch_saved or row.chapter_count
                    db.commit()
                    chapters_total += ch_saved
                    push_activity(f"✅ [{row.title}] 下载完成: {ch_saved} 章")
                    logger.info("书 [%s] 下载完成: %d 章", row.title, ch_saved)

                    await asyncio.sleep(TD_DOWNLOAD_INTERVAL)

                except Exception as e:
                    row.status = "failed"
                    db.commit()
                    push_activity(f"❌ [{row.title}] 下载失败: {e}", "error")
                    logger.error("下载 [%s] 失败: %s", row.title, e)

        push_activity(f"🎉 采集完成！元数据 {saved_meta} 本，章节 {chapters_total} 章")
        return {"fanqie": saved_meta, "chapters": chapters_total}

    finally:
        await td_client.aclose()
        db.close()


# ── 仅采集元数据 (轻量) ──────────────────────────────────────────

async def crawl_fanqie_hot(rank_types: list[str] | None = None) -> list[dict]:
    """兼容旧接口 — 仅采集书库列表元数据"""
    async with httpx.AsyncClient(timeout=30) as client:
        return await crawl_fanqie_library(client)


async def crawl_qidian_hot(rank_types: list[str] | None = None) -> list[dict]:
    """起点采集 — 暂保留空实现"""
    return []


# ── 封面下载 ───────────────────────────────────────────────────────

async def _download_cover(
    client: httpx.AsyncClient,
    cover_url: str,
    book_id: str,
) -> str:
    """下载封面到本地，返回本地 API 路径；失败则返回空字符串"""
    if not cover_url:
        return ""
    local_file = COVER_DIR / f"{book_id}.jpg"
    if local_file.exists() and local_file.stat().st_size > MIN_COVER_BYTES:
        return f"/api/v1/learning/covers/{book_id}.jpg"
    try:
        resp = await client.get(cover_url, timeout=15, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > MIN_COVER_BYTES:
            local_file.write_bytes(resp.content)
            logger.debug("封面已下载: %s → %s", book_id, local_file)
            return f"/api/v1/learning/covers/{book_id}.jpg"
    except Exception as e:
        logger.debug("下载封面失败 %s: %s", book_id, e)
    return ""


_COVER_CONCURRENCY = 8

async def _download_covers_batch(
    client: httpx.AsyncClient,
    novels: list[dict],
) -> None:
    """批量并发下载封面到本地并更新 cover_url 为本地路径"""
    sem = asyncio.Semaphore(_COVER_CONCURRENCY)

    async def _download_one(n: dict) -> None:
        remote_url = n.get("cover_url", "")
        book_id = n.get("source_book_id", "")
        if not remote_url or not book_id or remote_url.startswith("/api/"):
            return
        async with sem:
            local_path = await _download_cover(client, remote_url, book_id)
        if local_path:
            n["cover_url"] = local_path

    await asyncio.gather(*[_download_one(n) for n in novels], return_exceptions=True)


# ── 写入数据库 ───────────────────────────────────────────────────

def _save_novels(db, novels: list[dict]) -> int:
    """去重写入 HotNovelMeta"""
    saved = 0
    for n in novels:
        title = n.get("title", "")
        platform = n.get("platform", "")
        source_book_id = n.get("source_book_id", "")
        if not title or not platform:
            continue

        existing = (
            db.query(HotNovelMeta)
            .filter_by(platform=platform, source_book_id=source_book_id)
            .first()
        ) if source_book_id else (
            db.query(HotNovelMeta)
            .filter_by(platform=platform, title=title)
            .first()
        )

        if existing:
            existing.crawled_at = datetime.now(timezone.utc)
            if n.get("word_count"):
                existing.word_count = n["word_count"]
            if n.get("synopsis"):
                existing.synopsis = n["synopsis"]
            if n.get("cover_url"):
                existing.cover_url = n["cover_url"]
            if n.get("chapter_count"):
                existing.chapter_count = n["chapter_count"]
            if n.get("read_count"):
                existing.read_count = n["read_count"]
            if n.get("bookshelf_count"):
                existing.bookshelf_count = n["bookshelf_count"]
            if n.get("rating") is not None:
                existing.rating = n["rating"]
            if n.get("created_at_source"):
                existing.created_at_source = n["created_at_source"]
        else:
            row = HotNovelMeta(
                platform=platform,
                source_book_id=source_book_id,
                title=title,
                author=n.get("author", ""),
                genre=n.get("genre", ""),
                tags=json.dumps(n.get("tags", []), ensure_ascii=False),
                word_count=n.get("word_count", 0),
                chapter_count=n.get("chapter_count", 0),
                read_count=n.get("read_count", 0),
                bookshelf_count=n.get("bookshelf_count", 0),
                rating=n.get("rating"),
                created_at_source=n.get("created_at_source", ""),
                synopsis=n.get("synopsis", ""),
                cover_url=n.get("cover_url", ""),
                rank_info="{}",
                source_url=n.get("source_url", ""),
                status="meta",
            )
            db.add(row)
            saved += 1

    db.commit()
    return saved
