"""回填 hot_novel_meta 中 title/author/synopsis 的番茄字体混淆。

思路:
  1. 合并 backend/data/fanqie_font_maps/*.json 中已有的 PUA->汉字映射作为基线
  2. 先用基线把 title/author/synopsis 解一遍，统计还剩多少 PUA
  3. 对仍然有 PUA 的行, 按书一次性从 reader 抓 woff2 字体, 用 FontShapeDecoder
     构建/扩充映射, 然后再次解码 title/author/synopsis
  4. 事务内 UPDATE 回 DB

运行: python -m scripts.fix_hot_novel_meta_pua --dry-run   # 先看改动
     python -m scripts.fix_hot_novel_meta_pua             # 正式回填
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.connection import SessionLocal  # noqa: E402
from app.models.learning import HotNovelChapter, HotNovelMeta  # noqa: E402
from app.services.learning.fanqie_direct import FANQIE_BASE, HEADERS, get_chapter_list  # noqa: E402
from scripts.fanqie_learning_scraper import FONT_CACHE_DIR, FontShapeDecoder, parse_reader_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fix_pua")


def _is_pua(c: str) -> bool:
    return "\ue000" <= c <= "\uf8ff"


def load_base_mapping() -> dict[str, str]:
    """合并所有已缓存的番茄字体映射作为基线。"""
    mapping: dict[str, str] = {}
    for path in sorted(FONT_CACHE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("skip broken font map %s: %s", path.name, exc)
            continue
        for hex_code, ch in (data.get("mapping") or {}).items():
            if not ch:
                continue
            try:
                key = chr(int(hex_code, 16))
            except ValueError:
                continue
            mapping.setdefault(key, ch)
    return mapping


def apply_mapping(text: str | None, mapping: dict[str, str]) -> tuple[str, int]:
    """用 mapping 替换 PUA; 返回 (新字符串, 剩余 PUA 数)."""
    if not text:
        return text or "", 0
    out_chars: list[str] = []
    remain = 0
    for ch in text:
        if _is_pua(ch):
            repl = mapping.get(ch)
            if repl:
                out_chars.append(repl)
            else:
                out_chars.append(ch)
                remain += 1
        else:
            out_chars.append(ch)
    return "".join(out_chars), remain


def count_pua(text: str | None) -> int:
    if not text:
        return 0
    return sum(1 for c in text if _is_pua(c))


async def fetch_font_bytes_for_book(
    client: httpx.AsyncClient, book_id: str
) -> bytes | None:
    """尝试为指定书抓一个带字体的 reader 页面, 返回首个 woff2 字节."""
    try:
        catalog = await get_chapter_list(client, book_id)
    except Exception as exc:
        logger.warning("book %s: get_chapter_list failed: %s", book_id, exc)
        return None
    if not catalog:
        return None

    for item in catalog[:8]:
        chapter_id = str(item.get("chapter_id") or "")
        if not chapter_id:
            continue
        try:
            resp = await client.get(
                f"{FANQIE_BASE}/reader/{chapter_id}",
                headers={**HEADERS, "Accept": "text/html"},
                timeout=20,
            )
        except Exception as exc:
            logger.warning("book %s chapter %s: reader fetch failed: %s", book_id, chapter_id, exc)
            continue
        if resp.status_code != 200:
            continue
        parsed = parse_reader_page(resp.text)
        if not parsed["font_urls"]:
            continue
        try:
            font_resp = await client.get(
                parsed["font_urls"][0],
                headers={**HEADERS, "Referer": f"{FANQIE_BASE}/reader/{chapter_id}"},
                timeout=20,
            )
        except Exception as exc:
            logger.warning("book %s: font download failed: %s", book_id, exc)
            continue
        if font_resp.status_code == 200 and font_resp.content:
            return font_resp.content
    return None


async def resolve_unknown_pua(
    unknown: set[str],
    meta_rows: list[HotNovelMeta],
    decoder: FontShapeDecoder,
    client: httpx.AsyncClient,
    max_books: int,
) -> dict[str, str]:
    """对剩余 PUA, 逐书抓字体并 OCR, 直到覆盖或达到 max_books."""
    resolved: dict[str, str] = {}
    tried = 0
    for row in meta_rows:
        if tried >= max_books:
            break
        remaining = unknown - resolved.keys()
        if not remaining:
            break
        # 只挑自己字段里仍有未解 PUA 的书
        own = set()
        for field in (row.title, row.author, row.synopsis):
            for ch in field or "":
                if _is_pua(ch) and ch in remaining:
                    own.add(ch)
        if not own:
            continue
        tried += 1
        font_bytes = await fetch_font_bytes_for_book(client, row.source_book_id)
        if not font_bytes:
            logger.info("book %s (%s): no font bytes obtained", row.source_book_id, row.title[:10])
            continue
        mapping = decoder.build_mapping(font_bytes, own)
        new_resolved = {k: v for k, v in mapping.items() if v and k in remaining}
        if new_resolved:
            resolved.update(new_resolved)
            logger.info(
                "book %s resolved %d new chars (total resolved=%d, remaining=%d)",
                row.source_book_id,
                len(new_resolved),
                len(resolved),
                len(unknown) - len(resolved),
            )
    return resolved


async def main_async(dry_run: bool, max_books: int, limit: int | None) -> None:
    base_mapping = load_base_mapping()
    logger.info("base mapping size: %d", len(base_mapping))

    session = SessionLocal()
    try:
        query = session.query(HotNovelMeta).filter(HotNovelMeta.platform == "fanqie")
        if limit:
            query = query.limit(limit)
        rows: list[HotNovelMeta] = query.all()
    finally:
        session.close()
    logger.info("scanning %d fanqie meta rows", len(rows))

    # Pass 1: 先用 base_mapping 做一遍, 收集仍未解析的 PUA
    pending: list[tuple[HotNovelMeta, dict[str, str]]] = []
    unknown: set[str] = set()
    for row in rows:
        new_title, _ = apply_mapping(row.title, base_mapping)
        new_author, _ = apply_mapping(row.author, base_mapping)
        new_syn, _ = apply_mapping(row.synopsis, base_mapping)
        pending.append(
            (row, {"title": new_title, "author": new_author, "synopsis": new_syn})
        )
        for text in (new_title, new_author, new_syn):
            for ch in text or "":
                if _is_pua(ch):
                    unknown.add(ch)
    logger.info("after base mapping: unresolved PUA chars=%d", len(unknown))

    # Pass 2: 对剩余 PUA 尝试抓字体扩充映射
    if unknown:
        decoder = FontShapeDecoder()
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            extra = await resolve_unknown_pua(
                unknown=unknown,
                meta_rows=[r for r, _ in pending],
                decoder=decoder,
                client=client,
                max_books=max_books,
            )
        if extra:
            base_mapping = {**base_mapping, **extra}
            logger.info("extended mapping with %d new chars; retry decoding", len(extra))
            for row, new_fields in pending:
                new_fields["title"], _ = apply_mapping(row.title, base_mapping)
                new_fields["author"], _ = apply_mapping(row.author, base_mapping)
                new_fields["synopsis"], _ = apply_mapping(row.synopsis, base_mapping)

    # 打印结果统计
    final_rows_with_pua = sum(
        1
        for _, f in pending
        if count_pua(f["title"]) or count_pua(f["author"]) or count_pua(f["synopsis"])
    )
    changed = 0
    for row, f in pending:
        if (
            f["title"] != (row.title or "")
            or f["author"] != (row.author or "")
            or f["synopsis"] != (row.synopsis or "")
        ):
            changed += 1
    logger.info(
        "rows_with_pua_remaining=%d  rows_changed=%d  total=%d",
        final_rows_with_pua,
        changed,
        len(rows),
    )

    if dry_run:
        logger.info("--dry-run: 不写回 DB; 样例预览:")
        for row, f in pending[:5]:
            logger.info(
                "  [%s] %r -> %r", row.source_book_id, row.title, f["title"]
            )
        return

    session = SessionLocal()
    try:
        for row, f in pending:
            row = session.merge(row)
            row.title = f["title"]
            row.author = f["author"]
            row.synopsis = f["synopsis"]
        session.commit()
        logger.info("committed %d rows", changed)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只预览, 不写回 DB")
    parser.add_argument(
        "--max-books",
        type=int,
        default=30,
        help="最多抓取多少本书的字体用于扩充 PUA 映射 (默认 30)",
    )
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 行 (调试)")
    args = parser.parse_args()
    asyncio.run(main_async(dry_run=args.dry_run, max_books=args.max_books, limit=args.limit))


if __name__ == "__main__":
    main()
