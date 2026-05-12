from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.learning.fanqie_direct import FANQIE_BASE, HEADERS, get_book_detail, get_chapter_list  # noqa: E402


PUA_LIMIT = 0.15
FONT_CACHE_DIR = BACKEND_ROOT / "data" / "fanqie_font_maps"


@dataclass
class ChapterResult:
    chapter_number: int
    title: str
    source_chapter_id: str
    content: str
    source: str
    word_count: int
    pua_ratio: float = 0.0
    skipped_reason: str = ""


@dataclass
class ScrapeResult:
    platform: str
    source_book_id: str
    title: str
    author: str = ""
    genre: str = ""
    tags: list[str] = field(default_factory=list)
    synopsis: str = ""
    cover_url: str = ""
    source_url: str = ""
    catalog_count: int = 0
    chapters: list[ChapterResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def pua_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for c in text if "\ue000" <= c <= "\uf8ff") / len(text)


def extract_book_id(raw: str) -> str | None:
    raw = raw.strip()
    if re.fullmatch(r"\d{8,}", raw):
        return raw
    for pattern in (r"/page/(\d+)", r"[?&]bookId=(\d+)", r"[?&]book_id=(\d+)", r"/book/(\d+)"):
        match = re.search(pattern, raw)
        if match:
            return match.group(1)
    return None


def extract_reader_chapter_id(raw: str) -> str | None:
    match = re.search(r"/reader/(\d+)", raw.strip())
    return match.group(1) if match else None


def clean_title(title: str) -> str:
    title = html.unescape(title).strip()
    title = re.sub(r"_番茄小说官网$", "", title)
    title = re.sub(r"完整版在线免费阅读_.*$", "", title)
    title = re.sub(r"在线免费阅读_番茄小说官网$", "", title)
    title = re.sub(r"小说_番茄小说官网$", "", title)
    return title.strip()


def _json_unescape(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace("\\u002F", "/").replace("\\/", "/")


def parse_book_page_meta(html_text: str, book_id: str) -> dict[str, Any]:
    normalized = html.unescape(html_text).replace("\\u002F", "/").replace("\\/", "/")
    meta: dict[str, Any] = {
        "platform": "fanqie",
        "source_book_id": book_id,
        "title": "",
        "author": "",
        "genre": "",
        "tags": [],
        "synopsis": "",
        "cover_url": "",
        "source_url": f"{FANQIE_BASE}/page/{book_id}",
    }

    for script_match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        flags=re.I | re.S,
    ):
        try:
            data = json.loads(html.unescape(script_match.group(1)).strip())
        except json.JSONDecodeError:
            continue
        headline = data.get("headline") or ""
        image = data.get("image")
        authors = data.get("author") or []
        if isinstance(authors, dict):
            authors = [authors]
        if headline and not meta["title"]:
            meta["title"] = clean_title(headline)
        if isinstance(image, list) and image and not meta["cover_url"]:
            meta["cover_url"] = str(image[0])
        elif isinstance(image, str) and not meta["cover_url"]:
            meta["cover_url"] = image
        if authors and isinstance(authors[0], dict) and not meta["author"]:
            meta["author"] = authors[0].get("name", "")

    title_match = re.search(r"<title>(.*?)</title>", normalized, flags=re.I | re.S)
    if title_match and not meta["title"]:
        meta["title"] = clean_title(title_match.group(1))

    book_name_match = re.search(r'"bookName"\s*:\s*"((?:[^"\\]|\\.)*)"', normalized)
    if book_name_match:
        meta["title"] = clean_title(_json_unescape(book_name_match.group(1))) or meta["title"]

    author_match = re.search(r'"authorName"\s*:\s*"((?:[^"\\]|\\.)*)"', normalized)
    if author_match:
        meta["author"] = _json_unescape(author_match.group(1)) or meta["author"]

    thumb_match = re.search(r'"thumbUrl"\s*:\s*"((?:[^"\\]|\\.)*)"', normalized)
    if thumb_match:
        meta["cover_url"] = _json_unescape(thumb_match.group(1)) or meta["cover_url"]

    description_match = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)',
        normalized,
        flags=re.I,
    )
    if description_match:
        meta["synopsis"] = html.unescape(description_match.group(1)).strip()

    keywords_match = re.search(
        r'<meta\s+name=["\']keywords["\']\s+content=["\']([^"\']*)',
        normalized,
        flags=re.I,
    )
    if keywords_match:
        keywords = [x.strip() for x in html.unescape(keywords_match.group(1)).split(",") if x.strip()]
        if keywords:
            meta["tags"] = keywords[:8]

    return meta


async def fetch_book_meta(client: httpx.AsyncClient, book_id: str) -> dict[str, Any]:
    detail = await get_book_detail(client, book_id)
    meta = dict(detail or {})
    try:
        response = await client.get(
            f"{FANQIE_BASE}/page/{book_id}",
            headers={**HEADERS, "Accept": "text/html"},
            timeout=20,
        )
        if response.status_code == 200:
            page_meta = parse_book_page_meta(response.text, book_id)
            for key, value in page_meta.items():
                if value and (not meta.get(key) or key in {"title", "cover_url", "author"}):
                    meta[key] = value
    except Exception as exc:  # pragma: no cover - network guard
        meta.setdefault("warnings", []).append(f"book page meta failed: {exc}")

    meta.setdefault("platform", "fanqie")
    meta.setdefault("source_book_id", book_id)
    meta.setdefault("source_url", f"{FANQIE_BASE}/page/{book_id}")
    meta.setdefault("title", "")
    meta.setdefault("author", "")
    meta.setdefault("genre", "")
    meta.setdefault("tags", [])
    meta.setdefault("synopsis", "")
    meta.setdefault("cover_url", "")
    return meta


async def resolve_book_id(client: httpx.AsyncClient, raw: str) -> str:
    book_id = extract_book_id(raw)
    if book_id:
        return book_id

    chapter_id = extract_reader_chapter_id(raw)
    if not chapter_id:
        raise ValueError("Please provide a Fanqie book id or /page/{book_id} URL.")

    response = await client.get(
        f"{FANQIE_BASE}/reader/{chapter_id}",
        headers={**HEADERS, "Accept": "text/html"},
        timeout=20,
    )
    for pattern in (r'"bookId"\s*:\s*"?(?P<id>\d+)"?', r'"book_id"\s*:\s*"?(?P<id>\d+)"?', r"/page/(?P<id>\d+)"):
        match = re.search(pattern, response.text)
        if match:
            return match.group("id")
    raise ValueError("Reader URL was fetched, but book id was not found in the page.")


def decode_js_string(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), raw)


def strip_html_text(raw_html: str) -> str:
    text = re.sub(r"</p\s*>", "\n", raw_html, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    lines = [html.unescape(line).strip() for line in text.splitlines() if html.unescape(line).strip()]
    return "\n".join(lines)


def parse_reader_page(html_text: str) -> dict[str, Any]:
    content_match = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', html_text)
    title_match = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', html_text)
    font_urls = re.findall(r"url\((https://[^)]+?\.(?:woff2?|otf))\)", html_text)

    content = ""
    if content_match:
        content = strip_html_text(decode_js_string(content_match.group(1)))

    return {
        "content": content,
        "title": decode_js_string(title_match.group(1)) if title_match else "",
        "font_urls": list(dict.fromkeys(font_urls)),
    }


def gb2312_chinese_chars() -> list[str]:
    chars: list[str] = []
    seen: set[str] = set()
    for high in range(0xB0, 0xF8):
        for low in range(0xA1, 0xFF):
            try:
                char = bytes([high, low]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            if "\u4e00" <= char <= "\u9fff" and char not in seen:
                seen.add(char)
                chars.append(char)
    return chars


def find_reference_font() -> Path:
    candidates = [
        Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\Deng.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return path
    raise RuntimeError("No Chinese reference font found on this Windows machine.")


class FontShapeDecoder:
    def __init__(self, cache_dir: Path = FONT_CACHE_DIR, reference_font: Path | None = None):
        self.cache_dir = cache_dir
        self.reference_font = reference_font or find_reference_font()
        self._candidate_chars: list[str] | None = None
        self._candidate_matrix = None
        self._candidate_norms = None

    @staticmethod
    def _render_char(font: Any, char: str, size: int = 80, out: int = 48):
        from PIL import Image, ImageDraw
        import numpy as np

        canvas_size = size * 2
        image = Image.new("L", (canvas_size, canvas_size), 0)
        draw = ImageDraw.Draw(image)
        bbox = draw.textbbox((0, 0), char, font=font)
        draw.text((-bbox[0] + 12, -bbox[1] + 12), char, font=font, fill=255)
        bbox = image.getbbox()
        if not bbox:
            return None
        crop = image.crop(bbox)
        normalized = Image.new("L", (out, out), 0)
        crop.thumbnail((out - 4, out - 4), Image.Resampling.LANCZOS)
        normalized.paste(crop, ((out - crop.width) // 2, (out - crop.height) // 2))
        return np.asarray(normalized, dtype=np.float32).reshape(-1) / 255.0

    def _ensure_candidates(self) -> None:
        if self._candidate_matrix is not None:
            return
        from PIL import ImageFont
        import numpy as np

        font = ImageFont.truetype(str(self.reference_font), 80)
        chars = gb2312_chinese_chars()
        vectors = []
        kept = []
        for char in chars:
            vec = self._render_char(font, char)
            if vec is None:
                continue
            kept.append(char)
            vectors.append(vec)
        self._candidate_chars = kept
        self._candidate_matrix = np.stack(vectors).astype("float32")
        self._candidate_norms = (self._candidate_matrix * self._candidate_matrix).mean(axis=1)

    def _cache_path(self, font_bytes: bytes) -> Path:
        font_hash = hashlib.sha256(font_bytes).hexdigest()[:16]
        ref_hash = hashlib.sha256(str(self.reference_font).encode("utf-8")).hexdigest()[:8]
        return self.cache_dir / f"{font_hash}_{ref_hash}.json"

    def _load_cache(self, font_bytes: bytes) -> dict[str, str]:
        path = self._cache_path(font_bytes)
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {chr(int(k, 16)): v for k, v in raw.get("mapping", {}).items() if isinstance(v, str) and v}

    def _save_cache(self, font_bytes: bytes, mapping: dict[str, str]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_path(font_bytes)
        payload = {
            "reference_font": str(self.reference_font),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "mapping": {f"{ord(k):04x}": v for k, v in sorted(mapping.items(), key=lambda item: ord(item[0]))},
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_mapping(self, font_bytes: bytes, chars: set[str]) -> dict[str, str]:
        missing = {c for c in chars if "\ue000" <= c <= "\uf8ff"}
        if not missing:
            return {}

        mapping = self._load_cache(font_bytes)
        need = sorted(c for c in missing if c not in mapping)
        if not need:
            return {c: mapping[c] for c in missing if c in mapping}

        self._ensure_candidates()
        from PIL import ImageFont
        import numpy as np

        with tempfile.NamedTemporaryFile(delete=False, suffix=".woff2") as tmp:
            tmp.write(font_bytes)
            font_path = tmp.name
        try:
            encrypted_font = ImageFont.truetype(font_path, 80)
            assert self._candidate_matrix is not None
            assert self._candidate_norms is not None
            assert self._candidate_chars is not None
            feature_size = self._candidate_matrix.shape[1]
            for char in need:
                target = self._render_char(encrypted_font, char)
                if target is None:
                    continue
                target_norm = float((target * target).mean())
                scores = self._candidate_norms + target_norm - 2.0 * (self._candidate_matrix @ target) / feature_size
                best_index = int(np.argmin(scores))
                mapping[char] = self._candidate_chars[best_index]
        finally:
            Path(font_path).unlink(missing_ok=True)

        self._save_cache(font_bytes, mapping)
        return {c: mapping[c] for c in missing if c in mapping}

    def decode_text(self, text: str, font_bytes: bytes) -> tuple[str, dict[str, str]]:
        chars = {c for c in text if "\ue000" <= c <= "\uf8ff"}
        mapping = self.build_mapping(font_bytes, chars)
        if not mapping:
            return text, {}
        return "".join(mapping.get(c, c) for c in text), mapping


async def fetch_reader_chapter(
    client: httpx.AsyncClient,
    chapter_id: str,
    decoder: FontShapeDecoder,
    decode_font: bool = True,
) -> tuple[str, str, float, str, list[str]]:
    warnings: list[str] = []
    response = await client.get(
        f"{FANQIE_BASE}/reader/{chapter_id}",
        headers={**HEADERS, "Accept": "text/html"},
        timeout=20,
    )
    if response.status_code != 200:
        return "", "", 0.0, "fanqie-reader", [f"reader page returned HTTP {response.status_code}: {chapter_id}"]

    parsed = parse_reader_page(response.text)
    content = parsed["content"]
    before_ratio = pua_ratio(content)
    source = "fanqie-reader"
    if decode_font and before_ratio > 0:
        if not parsed["font_urls"]:
            warnings.append(f"no font url found for encrypted chapter {chapter_id}")
        else:
            try:
                font_response = await client.get(
                    parsed["font_urls"][0],
                    headers={**HEADERS, "Referer": f"{FANQIE_BASE}/reader/{chapter_id}"},
                    timeout=20,
                )
                if font_response.status_code == 200 and font_response.content:
                    content, _ = decoder.decode_text(content, font_response.content)
                    source = "fanqie-reader-font-decoded"
                else:
                    warnings.append(f"font download failed for chapter {chapter_id}: HTTP {font_response.status_code}")
            except Exception as exc:
                warnings.append(f"font decode failed for chapter {chapter_id}: {exc}")

    after_ratio = pua_ratio(content)
    if after_ratio > PUA_LIMIT:
        warnings.append(f"chapter {chapter_id} still has PUA ratio {after_ratio:.3f}")
    return content, parsed["title"], after_ratio, source, warnings


async def scrape_book(
    source: str,
    max_chapters: int,
    decode_font: bool = True,
) -> ScrapeResult:
    decoder = FontShapeDecoder()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        book_id = await resolve_book_id(client, source)
        meta = await fetch_book_meta(client, book_id)
        catalog = await get_chapter_list(client, book_id)
        warnings: list[str] = list(meta.pop("warnings", []))
        if not catalog:
            warnings.append("No chapter catalog was returned by Fanqie.")

        chapters: list[ChapterResult] = []
        for item in catalog[:max_chapters]:
            chapter_id = str(item.get("chapter_id", ""))
            content, page_title, ratio, chapter_source, chapter_warnings = await fetch_reader_chapter(
                client,
                chapter_id,
                decoder=decoder,
                decode_font=decode_font,
            )
            warnings.extend(chapter_warnings)
            title = item.get("title", "") or page_title or f"Chapter {item.get('chapter_number', len(chapters) + 1)}"
            chapters.append(
                ChapterResult(
                    chapter_number=int(item.get("chapter_number") or len(chapters) + 1),
                    title=title,
                    source_chapter_id=chapter_id,
                    content=content,
                    source=chapter_source,
                    word_count=len(content),
                    pua_ratio=ratio,
                    skipped_reason="" if content else "empty_content",
                )
            )
            await asyncio.sleep(0.5)

        return ScrapeResult(
            platform="fanqie",
            source_book_id=book_id,
            title=meta.get("title") or f"fanqie-{book_id}",
            author=meta.get("author", ""),
            genre=meta.get("genre", ""),
            tags=list(meta.get("tags") or []),
            synopsis=meta.get("synopsis", ""),
            cover_url=meta.get("cover_url", ""),
            source_url=meta.get("source_url") or f"{FANQIE_BASE}/page/{book_id}",
            catalog_count=len(catalog),
            chapters=chapters,
            warnings=warnings,
        )


def save_json(result: ScrapeResult, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def save_to_learning_db(result: ScrapeResult) -> dict[str, Any]:
    from app.db.connection import SessionLocal, init_db
    from app.models.learning import HotNovelChapter, HotNovelMeta

    init_db()
    db = SessionLocal()
    try:
        row = (
            db.query(HotNovelMeta)
            .filter_by(platform="fanqie", source_book_id=result.source_book_id)
            .first()
        )
        if row is None:
            row = HotNovelMeta(platform="fanqie", source_book_id=result.source_book_id, title=result.title)
            db.add(row)
            db.flush()

        row.title = result.title
        row.author = result.author
        row.genre = result.genre
        row.tags = json.dumps(result.tags, ensure_ascii=False)
        row.synopsis = result.synopsis
        row.cover_url = result.cover_url
        row.source_url = result.source_url
        row.chapter_count = result.catalog_count or len(result.chapters)
        row.status = "done" if any(ch.content for ch in result.chapters) else "meta"
        row.crawled_at = datetime.now(timezone.utc)

        saved = 0
        updated = 0
        for ch in result.chapters:
            if not ch.content:
                continue
            existing = (
                db.query(HotNovelChapter)
                .filter_by(novel_id=row.id, source_chapter_id=ch.source_chapter_id)
                .first()
            )
            if existing is None:
                existing = HotNovelChapter(novel_id=row.id, source_chapter_id=ch.source_chapter_id)
                db.add(existing)
                saved += 1
            else:
                updated += 1
            existing.chapter_number = ch.chapter_number
            existing.title = ch.title
            existing.content = ch.content
            existing.word_count = len(ch.content)
            existing.crawled_at = datetime.now(timezone.utc)

        db.commit()
        return {"novel_id": row.id, "chapters_saved": saved, "chapters_updated": updated, "status": row.status}
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Direct Fanqie scraper for LearnHub: title, cover, catalog and decoded body.")
    parser.add_argument("--book-id", help="Fanqie book id, for example 7276384138653862966.")
    parser.add_argument("--url", help="Fanqie /page/{book_id} URL. /reader/{chapter_id} is also accepted when resolvable.")
    parser.add_argument("--max-chapters", type=int, default=3, help="Maximum chapters to fetch.")
    parser.add_argument("--no-decode", action="store_true", help="Keep raw PUA text instead of decoding the Fanqie web font.")
    parser.add_argument("--save-db", action="store_true", help="Write result into LearnHub HotNovel tables.")
    parser.add_argument("--out", type=Path, help="JSON output path. Defaults to backend/data/fanqie_scrape_{book_id}.json.")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.book_id or args.url
    if not source:
        raise SystemExit("Provide --book-id or --url.")
    if args.max_chapters < 1:
        raise SystemExit("--max-chapters must be >= 1.")

    result = await scrape_book(source=source, max_chapters=args.max_chapters, decode_font=not args.no_decode)
    output = args.out or (BACKEND_ROOT / "data" / f"fanqie_scrape_{result.source_book_id}.json")
    save_json(result, output)

    db_info = save_to_learning_db(result) if args.save_db else None
    content_count = sum(1 for ch in result.chapters if ch.content)
    pua_max = max((ch.pua_ratio for ch in result.chapters), default=0.0)
    summary = {
        "book_id": result.source_book_id,
        "title": result.title,
        "cover": bool(result.cover_url),
        "catalog_count": result.catalog_count,
        "chapters_requested": args.max_chapters,
        "chapters_with_content": content_count,
        "max_pua_ratio": round(pua_max, 6),
        "output": str(output),
        "db": db_info,
        "warnings": result.warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
