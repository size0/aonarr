"""文件解析器 — 支持 txt / epub / docx 三种格式

将上传的小说文件统一转为纯文本，自动检测编码。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import chardet

logger = logging.getLogger(__name__)


class ImportResult:
    """导入结果"""

    def __init__(self, text: str, title: str = "", metadata: Optional[dict] = None):
        self.text = text
        self.title = title
        self.metadata = metadata or {}
        self.char_count = len(text)

    def __repr__(self) -> str:
        return f"<ImportResult title={self.title!r} chars={self.char_count}>"


# ── 公共入口 ──────────────────────────────────────────────────────

def import_file(path: str | Path) -> ImportResult:
    """根据扩展名自动选择解析器"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")

    ext = p.suffix.lower()
    parsers = {
        ".txt": _parse_txt,
        ".epub": _parse_epub,
        ".docx": _parse_docx,
    }
    parser = parsers.get(ext)
    if parser is None:
        raise ValueError(f"不支持的文件格式: {ext}（支持 .txt / .epub / .docx）")

    logger.info("开始解析文件: %s (格式: %s)", p.name, ext)
    result = parser(p)
    logger.info("解析完成: %s, %d 字符", result.title or p.stem, result.char_count)
    return result


# ── TXT 解析 ──────────────────────────────────────────────────────

def _parse_txt(path: Path) -> ImportResult:
    """解析纯文本文件，自动检测编码"""
    raw = path.read_bytes()
    encoding = _detect_encoding(raw)
    text = raw.decode(encoding, errors="replace")
    # 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return ImportResult(text=text, title=path.stem)


def _detect_encoding(raw: bytes) -> str:
    """使用 chardet 检测编码，兜底 utf-8"""
    if raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    result = chardet.detect(raw[:10000])
    encoding = result.get("encoding") or "utf-8"
    confidence = result.get("confidence", 0)
    # 低置信度或检测为 ascii 时，尝试 utf-8
    if confidence < 0.6 or encoding.lower() == "ascii":
        encoding = "utf-8"
    logger.debug("编码检测: %s (confidence=%.2f)", encoding, confidence)
    return encoding


# ── EPUB 解析 ─────────────────────────────────────────────────────

def _parse_epub(path: Path) -> ImportResult:
    """解析 EPUB 电子书，提取正文文本"""
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError as e:
        raise ImportError("请安装 ebooklib: pip install ebooklib") from e

    book = epub.read_epub(str(path), options={"ignore_ncx": True})

    # 提取标题
    title = ""
    dc_title = book.get_metadata("DC", "title")
    if dc_title:
        title = dc_title[0][0] if isinstance(dc_title[0], tuple) else str(dc_title[0])

    # 提取正文
    texts: list[str] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        html_content = item.get_content()
        plain = _strip_html(html_content)
        if plain.strip():
            texts.append(plain.strip())

    full_text = "\n\n".join(texts)
    metadata = {}
    dc_creator = book.get_metadata("DC", "creator")
    if dc_creator:
        metadata["author"] = dc_creator[0][0] if isinstance(dc_creator[0], tuple) else str(dc_creator[0])

    return ImportResult(text=full_text, title=title or path.stem, metadata=metadata)


def _strip_html(html_bytes: bytes) -> str:
    """简单 HTML 标签剥离"""
    import re
    text = html_bytes.decode("utf-8", errors="replace")
    # 移除 script/style 块
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # 段落/换行标签转换为换行
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]>", "\n", text, flags=re.IGNORECASE)
    # 移除所有标签
    text = re.sub(r"<[^>]+>", "", text)
    # 清理 HTML 实体
    text = text.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&").replace("&quot;", '"')
    # 合并多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── DOCX 解析 ─────────────────────────────────────────────────────

def _parse_docx(path: Path) -> ImportResult:
    """解析 Word docx 文件"""
    try:
        from docx import Document
    except ImportError as e:
        raise ImportError("请安装 python-docx: pip install python-docx") from e

    doc = Document(str(path))

    # 提取核心属性作为标题
    title = ""
    if doc.core_properties and doc.core_properties.title:
        title = doc.core_properties.title

    paragraphs: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)

    full_text = "\n".join(paragraphs)
    metadata = {}
    if doc.core_properties and doc.core_properties.author:
        metadata["author"] = doc.core_properties.author

    return ImportResult(text=full_text, title=title or path.stem, metadata=metadata)
