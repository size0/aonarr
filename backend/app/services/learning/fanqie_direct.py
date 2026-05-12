"""番茄小说直连采集 — 不依赖任何外部服务

通过番茄小说官方 Web API 直接搜索、获取详情、下载封面和章节内容。
完全自包含，只需要网络即可。

支持登录获取正文:
  - 手机号 + 密码登录
  - Cookie 导入（从浏览器）
  - Cookie 持久化到本地文件

API 端点（逆向自 fanqienovel.com 前端）:
  - 登录: 通过 passport SSO
  - 书库: /api/author/library/book_list/v0/
  - 详情: /page/{book_id}  (HTML 页面中提取 JSON)
  - 章节目录: /api/reader/directory/detail
  - 章节内容: /api/reader/full (需登录态)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ── 常量 ───────────────────────────────────────────────────────────

FANQIE_BASE = "https://fanqienovel.com"
FANQIE_LIBRARY_API = f"{FANQIE_BASE}/api/author/library/book_list/v0/"
FANQIE_DIRECTORY_API = f"{FANQIE_BASE}/api/reader/directory/detail"
FANQIE_CONTENT_API = f"{FANQIE_BASE}/api/reader/full"
# 移动端批量内容 API — 不走字体加密，直接返回明文
FANQIE_BATCH_CONTENT_API = f"{FANQIE_BASE}/reading/reader/batch_full/v"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"{FANQIE_BASE}/",
}

# 番茄书库品类ID（从 fanqienovel.com 前端提取）
# gender: 0=男频, 1=女频, -1=全部
# category_id: 各品类ID
LIBRARY_CATEGORIES = [
    # 男频热门
    {"gender": 0, "category_id": -1, "label": "男频-全部"},
    {"gender": 0, "category_id": 7, "label": "男频-玄幻"},
    {"gender": 0, "category_id": 1, "label": "男频-都市"},
    {"gender": 0, "category_id": 8, "label": "男频-科幻"},
    {"gender": 0, "category_id": 6, "label": "男频-历史"},
    {"gender": 0, "category_id": 4, "label": "男频-游戏"},
    {"gender": 0, "category_id": 3, "label": "男频-悬疑"},
    {"gender": 0, "category_id": 5, "label": "男频-仙侠"},
    # 女频热门
    {"gender": 1, "category_id": -1, "label": "女频-全部"},
    {"gender": 1, "category_id": 10, "label": "女频-古言"},
    {"gender": 1, "category_id": 11, "label": "女频-现言"},
    {"gender": 1, "category_id": 12, "label": "女频-幻想"},
]

# 书库每页条数
LIBRARY_PAGE_SIZE = 50
# 每品类最多翻页
LIBRARY_MAX_PAGES = 3
# 请求间隔(秒)
CRAWL_DELAY = 1.5


# ── 登录管理 — 复用发布中心的登录态 ─────────────────────────────

class FanqieSession:
    """番茄小说登录态管理

    直接复用发布中心 LoginStateManager("fanqie") 保存的 Playwright cookies，
    不需要重复登录。发布中心登录一次，采集模块自动获得登录态。
    """

    @classmethod
    def is_logged_in(cls) -> bool:
        return bool(cls.get_cookies())

    @classmethod
    def get_cookies(cls) -> dict[str, str]:
        """从发布中心 LoginStateManager 读取 fanqie cookies"""
        try:
            from app.services.publishing.login_manager import LoginStateManager
            mgr = LoginStateManager("fanqie")
            state = mgr.load_state()
            if not state or not state.get("cookies"):
                return {}
            # Playwright cookies 格式: [{name, value, domain, ...}, ...]
            cookies: dict[str, str] = {}
            for c in state["cookies"]:
                if isinstance(c, dict) and "fanqienovel.com" in c.get("domain", ""):
                    cookies[c["name"]] = c["value"]
            return cookies
        except Exception as e:
            logger.debug("读取发布中心 cookie 失败: %s", e)
            return {}


# ── 字体加密处理 ──────────────────────────────────────────────────

def _safe_int(raw: Any) -> int:
    """安全解析数字，字体加密的返回 0"""
    if isinstance(raw, (int, float)):
        return int(raw)
    if not isinstance(raw, str):
        return 0
    cleaned = raw.replace(",", "").strip()
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        pass
    return 0


# ── 分品类采集（替代已下线的搜索 API）─────────────────────────────

async def search_fanqie(
    client: httpx.AsyncClient,
    keywords: list[str] | None = None,
    max_per_keyword: int = 60,
    progress_callback: Any = None,
) -> list[dict]:
    """通过番茄书库按品类遍历采集小说元数据

    注: 番茄已下线搜索 API，改为按品类 + 排序方式遍历书库。
    效果等同于搜索，覆盖所有主要品类。
    """
    seen_ids: set[str] = set()
    novels: list[dict] = []

    for cat in LIBRARY_CATEGORIES:
        try:
            for page_idx in range(LIBRARY_MAX_PAGES):
                # 每品类用两种排序: 0=热度, 3=新书
                for sort in [0, 3]:
                    resp = await client.get(
                        FANQIE_LIBRARY_API,
                        params={
                            "page_count": LIBRARY_PAGE_SIZE,
                            "page_index": page_idx,
                            "gender": cat["gender"],
                            "category_id": cat["category_id"],
                            "creation_status": -1,
                            "word_count": -1,
                            "book_type": -1,
                            "sort": sort,
                        },
                        headers=HEADERS,
                        timeout=15,
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    books = data.get("data", {}).get("book_list", [])
                    if not books:
                        continue

                    for b in books:
                        book_id = str(b.get("book_id", ""))
                        if not book_id or book_id in seen_ids:
                            continue
                        seen_ids.add(book_id)
                        novels.append(_parse_book_data(b, source="library"))

                    await asyncio.sleep(CRAWL_DELAY)

            msg = f"📚 品类 [{cat['label']}] 累计 {len(novels)} 本"
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        except Exception as e:
            logger.warning("品类 [%s] 异常: %s", cat["label"], e)
            continue

    msg = f"📡 番茄直连采集共 {len(novels)} 本 (去重)"
    logger.info(msg)
    if progress_callback:
        progress_callback(msg)
    return novels


# ── 书库浏览 ──────────────────────────────────────────────────────

async def browse_fanqie_library(
    client: httpx.AsyncClient,
    max_pages: int = LIBRARY_MAX_PAGES,
    progress_callback: Any = None,
) -> list[dict]:
    """通过番茄书库 API 获取热门书单"""
    novels: list[dict] = []
    seen_ids: set[str] = set()

    # 遍历不同性别分类
    for gender in [-1, 0, 1]:
        for page_idx in range(max_pages):
            try:
                resp = await client.get(
                    FANQIE_LIBRARY_API,
                    params={
                        "page_count": LIBRARY_PAGE_SIZE,
                        "page_index": page_idx,
                        "gender": gender,
                        "category_id": -1,
                        "creation_status": -1,
                        "word_count": -1,
                        "book_type": -1,
                        "sort": 0,  # 热度排序
                    },
                    headers=HEADERS,
                    timeout=15,
                )
                if resp.status_code != 200:
                    break

                data = resp.json()
                books = data.get("data", {}).get("book_list", [])
                if not books:
                    break

                for b in books:
                    book_id = str(b.get("book_id", ""))
                    if not book_id or book_id in seen_ids:
                        continue
                    seen_ids.add(book_id)
                    novels.append(_parse_book_data(b, source="library"))

                await asyncio.sleep(1.5)

            except Exception as e:
                logger.warning("书库 gender=%d page=%d 异常: %s", gender, page_idx, e)
                break

    msg = f"📖 番茄书库浏览共 {len(novels)} 本"
    logger.info(msg)
    if progress_callback:
        progress_callback(msg)
    return novels


# ── 书详情页解析 ──────────────────────────────────────────────────

async def get_book_detail(
    client: httpx.AsyncClient,
    book_id: str,
) -> dict | None:
    """从书详情页 HTML 中提取结构化信息"""
    try:
        resp = await client.get(
            f"{FANQIE_BASE}/page/{book_id}",
            headers={**HEADERS, "Accept": "text/html"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        html = resp.text

        # 提取 window.__INITIAL_DATA__ 或类似的 JSON
        m = re.search(r'window\.__INITIAL_(?:DATA|STATE)__\s*=\s*({.*?})\s*;', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                book_data = data.get("bookData", data.get("book", {}))
                if book_data:
                    return _parse_book_data(book_data, source="detail")
            except json.JSONDecodeError:
                pass

        # 备选：提取 meta 标签
        info: dict[str, str] = {}
        for tag in ["og:title", "og:description", "og:image"]:
            m2 = re.search(rf'<meta\s+property="{tag}"\s+content="([^"]*)"', html)
            if m2:
                info[tag] = m2.group(1)

        if info.get("og:title"):
            return {
                "platform": "fanqie",
                "source_book_id": book_id,
                "title": info.get("og:title", ""),
                "synopsis": info.get("og:description", ""),
                "cover_url": info.get("og:image", ""),
                "source_url": f"{FANQIE_BASE}/page/{book_id}",
                "author": "", "genre": "", "tags": [],
                "word_count": 0, "chapter_count": 0,
                "read_count": 0, "bookshelf_count": 0,
                "rating": None, "created_at_source": "",
            }

    except Exception as e:
        logger.warning("获取书详情失败 %s: %s", book_id, e)

    return None


# ── 章节目录 ──────────────────────────────────────────────────────

async def get_chapter_list(
    client: httpx.AsyncClient,
    book_id: str,
) -> list[dict]:
    """获取章节目录

    番茄目录 API 返回格式:
      data.allItemIds: ["chapterId1", "chapterId2", ...]
      data.chapterListWithVolume: [{volumeName, chapterList: [{chapterId, title}]}]
    兜底: 从书页 HTML 提取 /reader/{chapterId} 链接
    """
    try:
        resp = await client.get(
            FANQIE_DIRECTORY_API,
            params={"bookId": book_id},
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        data = resp.json().get("data", {})
        chapters: list[dict] = []

        # 方式1: chapterListWithVolume (带标题)
        # 结构: list[list[dict]]，每个 volume 是一个 list of chapter dicts
        # 每个 chapter dict: {itemId, title, needPay, volume_name, ...}
        vol_list = data.get("chapterListWithVolume", [])
        if vol_list:
            idx = 0
            for vol in vol_list:
                ch_items = vol if isinstance(vol, list) else vol.get("chapterList", [])
                for ch in ch_items:
                    if not isinstance(ch, dict):
                        continue
                    idx += 1
                    chapters.append({
                        "chapter_id": str(ch.get("itemId", "") or ch.get("chapterId", "")),
                        "chapter_number": idx,
                        "title": ch.get("title", f"第{idx}章"),
                    })
            if chapters:
                logger.info("章节目录(volume): book_id=%s, %d 章", book_id, len(chapters))
                return chapters

        # 方式2: allItemIds (只有ID，无标题)
        item_ids = data.get("allItemIds", [])
        if item_ids:
            for idx, cid in enumerate(item_ids, 1):
                chapters.append({
                    "chapter_id": str(cid),
                    "chapter_number": idx,
                    "title": f"第{idx}章",
                })
            logger.info("章节目录(itemIds): book_id=%s, %d 章", book_id, len(chapters))
            return chapters

        # 方式3: 兜底 — 从书页 HTML 提取
        return await _get_chapter_list_from_html(client, book_id)

    except Exception as e:
        logger.warning("获取章节目录失败 %s: %s", book_id, e)
        return []


async def _get_chapter_list_from_html(
    client: httpx.AsyncClient,
    book_id: str,
) -> list[dict]:
    """从书详情页 HTML 提取章节ID列表"""
    try:
        resp = await client.get(
            f"{FANQIE_BASE}/page/{book_id}",
            headers={**HEADERS, "Accept": "text/html"},
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        ch_ids = re.findall(r'/reader/(\d+)', resp.text)
        # 去重保序
        seen: set[str] = set()
        unique: list[str] = []
        for cid in ch_ids:
            if cid not in seen:
                seen.add(cid)
                unique.append(cid)

        chapters = [
            {"chapter_id": cid, "chapter_number": i + 1, "title": f"第{i+1}章"}
            for i, cid in enumerate(unique)
        ]
        logger.info("章节目录(HTML): book_id=%s, %d 章", book_id, len(chapters))
        return chapters

    except Exception as e:
        logger.warning("HTML提取章节失败 %s: %s", book_id, e)
        return []


# ── 章节内容（移动端明文 API） ──────────────────────────────────────

async def get_chapter_content_batch(
    client: httpx.AsyncClient,
    chapter_ids: list[str],
) -> dict[str, tuple[str, str]]:
    """批量获取章节明文内容（移动端 API，无字体加密）

    移植自 Tomato-Novel-Downloader 的 content_client.rs
    调用 /reading/reader/batch_full/v 接口，模拟安卓客户端请求。

    Returns:
        {chapter_id: (content_text, title)}
    """
    if not chapter_ids:
        return {}

    params = {
        "item_ids": ",".join(chapter_ids),
        "update_version_code": "0",
        "aid": "1967",
        "key_register_ts": "0",
        "device_platform": "android",
        "iid": "0",
        "epub": "0",
    }
    cookies = FanqieSession.get_cookies()
    try:
        resp = await client.get(
            FANQIE_BATCH_CONTENT_API,
            params=params,
            headers=HEADERS,
            cookies=cookies,
            timeout=20,
        )
        if resp.status_code != 200:
            logger.warning("batch_full API 返回 %d", resp.status_code)
            return {}

        data = resp.json()
        # 结构: {"code": 0, "data": {"chapter_id": {"content": "...", "title": "..."}}} 或类似
        root = data.get("data", data)
        if not isinstance(root, dict):
            return {}

        results = {}
        for cid, info in root.items():
            if not isinstance(info, dict):
                continue
            raw_content = info.get("content", "")
            title = info.get("title", "") or info.get("origin_chapter_title", "") or ""
            if not raw_content:
                continue
            # 清理 HTML 标签
            text = re.sub(r'<[^>]+>', '\n', raw_content)
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            content = '\n'.join(lines)
            if content:
                results[cid] = (content, title)

        return results

    except Exception as e:
        logger.warning("batch_full 请求失败: %s", e)
        return {}


async def get_chapter_content(
    client: httpx.AsyncClient,
    chapter_id: str,
) -> str:
    """获取单章正文（HTML 解析，可能含字体加密 PUA 字符）"""
    cookies = FanqieSession.get_cookies()
    try:
        resp = await client.get(
            f"{FANQIE_BASE}/reader/{chapter_id}",
            headers={**HEADERS, "Accept": "text/html"},
            cookies=cookies,
            timeout=15,
        )
        if resp.status_code != 200:
            return ""

        html = resp.text
        if not html:
            return ""

        m = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
        if not m:
            return ""

        raw = m.group(1)
        decoded = re.sub(r'\\u([0-9a-fA-F]{4})', lambda mm: chr(int(mm.group(1), 16)), raw)
        text = re.sub(r'<[^>]+>', '\n', decoded)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)

    except Exception as e:
        logger.debug("获取章节内容失败 %s: %s", chapter_id, e)
        return ""


# ── 解析工具 ──────────────────────────────────────────────────────

def _parse_book_data(b: dict, source: str = "") -> dict:
    """统一解析各 API 返回的书籍数据为标准格式"""
    book_id = str(b.get("book_id", "") or b.get("bookId", ""))

    # 标签处理
    tags_raw = b.get("tag", "") or b.get("tags", "")
    if isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if t]
    elif isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    else:
        tags = []

    return {
        "platform": "fanqie",
        "source_book_id": book_id,
        "title": b.get("book_name", "") or b.get("title", ""),
        "author": b.get("author", ""),
        "genre": b.get("category", "") or b.get("genre", ""),
        "tags": tags,
        "word_count": _safe_int(b.get("word_count", 0)),
        "chapter_count": _safe_int(b.get("serial_count", 0) or b.get("chapter_count", 0)),
        "read_count": _safe_int(b.get("read_count", 0) or b.get("read_count_all", 0)),
        "bookshelf_count": _safe_int(b.get("all_bookshelf_count", 0) or b.get("bookshelf_count", 0)),
        "rating": _safe_float(b.get("score", "")),
        "created_at_source": b.get("create_time", "") or b.get("created_at_source", ""),
        "synopsis": b.get("abstract", "") or b.get("book_abstract_v2", "") or b.get("synopsis", ""),
        "cover_url": b.get("thumb_url", "") or b.get("cover_url", ""),
        "source_url": f"{FANQIE_BASE}/page/{book_id}" if book_id else "",
    }


def _safe_float(raw: Any) -> float | None:
    """安全解析浮点数"""
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None
