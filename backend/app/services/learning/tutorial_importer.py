"""教程导入器 — 扫描本地教程文件 → 提取文本 → 用 LLM 归纳 → 写入 KnowledgeEntry

支持文件类型: .txt, .docx, .doc(仅 docx 可提取, doc 需 antiword/libreoffice)

流程:
  1. scan_tutorial_dir()   — 递归扫描目录，收集可处理文件
  2. import_file()         — 读取文件文本 → LLM 结构化归纳 → 写入 KnowledgeEntry
  3. import_batch()        — 批量导入（可指定目录或文件列表）
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from app.db.connection import SessionLocal
from app.llm.client import GenerationConfig
from app.llm.resolver import StageModelResolver
from app.models.learning import KnowledgeEntry

logger = logging.getLogger(__name__)

# ── 目录→分类映射 ─────────────────────────────────────────────────

FOLDER_CATEGORY_MAP = {
    "新人基础": "writing_basics",
    "高手进阶": "writing_advanced",
    "大纲": "outline_technique",
    "设定": "worldbuilding",
    "描写词汇": "vocabulary",
    "计谋": "plot_strategy",
    "东方": "eastern_worldbuilding",
    "西方": "western_worldbuilding",
    "都市": "urban_genre",
    "穿越": "isekai_genre",
    "网游": "game_genre",
    "修真": "cultivation_genre",
    "玄幻": "fantasy_genre",
    "兵器": "weapons_reference",
    "格斗": "combat_reference",
    "名字": "naming_reference",
    "心理": "psychology",
    "道家": "taoism_reference",
    "佛家": "buddhism_reference",
    "辅助资料": "reference_material",
    "创作技巧": "writing_technique",
    "三部曲": "story_structure",
    "写作大纲": "outline_technique",
    "素材": "writing_material",
    "技巧": "writing_technique",
    "网文全程": "webnovel_workflow",
    "网文培训": "webnovel_training",
    "节奏": "pacing_technique",
    "入门": "writing_basics",
    "更新教程": "writing_updates",
}

SUPPORTED_EXTENSIONS = {".txt", ".docx"}

# LLM 提取每篇教程的结构化知识
TUTORIAL_SYSTEM_PROMPT = """你是一位网文创作知识提取专家。从提供的写作教程中提取可复用的结构化知识。

请严格按 JSON 格式输出：
{
  "title": "简短标题 (10-30字，概括核心知识点)",
  "insights": ["核心要点1", "核心要点2", ...],
  "pattern": "核心模式/技巧的简明描述",
  "applicable_to": ["适用场景1", "适用场景2"],
  "quality_score": 0.0-1.0,
  "tags": ["标签1", "标签2"]
}

注意：
- 提取实用的创作技巧，忽略无关内容
- 如果文本内容过短或无实质内容，quality_score 设为 0.1 以下
- tags 应包含具体的写作领域关键词"""

# 最大文本长度（字符），超过则截断（避免 token 超限）
MAX_TEXT_LENGTH = 8000
# 最小有效文本长度
MIN_TEXT_LENGTH = 50


# ── 文件读取 ──────────────────────────────────────────────────────

def _read_txt(path: Path) -> str:
    """读取 .txt 文件"""
    for enc in ("utf-8", "gbk", "gb2312", "gb18030", "big5", "latin1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def _read_docx(path: Path) -> str:
    """读取 .docx 文件"""
    try:
        import zipfile
        import xml.etree.ElementTree as ET

        paragraphs = []
        with zipfile.ZipFile(path, "r") as z:
            with z.open("word/document.xml") as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                for p in root.iter(f"{{{ns['w']}}}p"):
                    texts = [t.text for t in p.iter(f"{{{ns['w']}}}t") if t.text]
                    if texts:
                        paragraphs.append("".join(texts))
        return "\n".join(paragraphs)
    except Exception as e:
        logger.debug("读取 docx 失败 %s: %s", path, e)
        return ""


READER_MAP = {
    ".txt": _read_txt,
    ".docx": _read_docx,
}


def read_file_text(path: Path) -> str:
    """统一文本提取"""
    ext = path.suffix.lower()
    reader = READER_MAP.get(ext)
    if not reader:
        return ""
    text = reader(path)
    # 清理多余空白
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# ── 目录扫描 ──────────────────────────────────────────────────────

def _infer_category(file_path: Path) -> str:
    """根据文件所在目录推断分类"""
    parts = file_path.parts
    for part in parts:
        for keyword, category in FOLDER_CATEGORY_MAP.items():
            if keyword in part:
                return category
    return "writing_general"


def _file_hash(path: Path) -> str:
    """文件内容 SHA256 前 16 字符"""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def scan_tutorial_dir(
    base_dir: str | Path,
    extensions: set[str] | None = None,
) -> list[dict]:
    """递归扫描目录，返回待导入文件列表"""
    base = Path(base_dir)
    if not base.is_dir():
        logger.error("目录不存在: %s", base_dir)
        return []

    exts = extensions or SUPPORTED_EXTENSIONS
    files: list[dict] = []

    for f in base.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in exts:
            continue
        # 跳过重复文件（文件名带 _20211016 这类备份后缀）
        stem = f.stem
        if re.search(r"_\d{14}$", stem):
            continue
        # 跳过太小的文件 (<100 bytes)
        if f.stat().st_size < 100:
            continue

        rel = f.relative_to(base)
        files.append({
            "path": str(f),
            "relative": str(rel),
            "name": f.stem,
            "ext": f.suffix.lower(),
            "size": f.stat().st_size,
            "category": _infer_category(f),
            "folder": str(rel.parent) if rel.parent != Path(".") else "",
        })

    logger.info("扫描到 %d 个可导入文件 (目录: %s)", len(files), base_dir)
    return files


# ── 单文件导入 ────────────────────────────────────────────────────

async def import_file(
    file_path: str | Path,
    category: str | None = None,
    use_llm: bool = True,
) -> dict | None:
    """导入单个教程文件到知识库"""
    path = Path(file_path)
    if not path.exists():
        logger.warning("文件不存在: %s", file_path)
        return None

    # 读取文本
    text = read_file_text(path)
    if len(text) < MIN_TEXT_LENGTH:
        logger.debug("跳过过短文件: %s (%d 字符)", path.name, len(text))
        return None

    cat = category or _infer_category(path)
    file_str = str(path)

    db = SessionLocal()
    try:
        # 检查是否已导入（按 source_file 去重）
        existing = db.query(KnowledgeEntry).filter_by(source_file=file_str).first()
        if existing:
            logger.debug("已导入，跳过: %s", path.name)
            return {"id": existing.id, "title": existing.title, "skipped": True}

        # 截断过长文本
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "\n...(已截断)"

        if use_llm:
            result = await _llm_extract(text, path.stem, cat)
        else:
            # 简单模式：直接存储文本摘要
            result = {
                "title": path.stem[:60],
                "insights": [text[:200]],
                "pattern": "",
                "quality_score": 0.3,
                "tags": [cat],
            }

        if not result:
            return None

        entry = KnowledgeEntry(
            category=cat,
            title=result.get("title", path.stem)[:256],
            content=json.dumps(result, ensure_ascii=False),
            source_file=file_str,
            tags=json.dumps(result.get("tags", [cat]), ensure_ascii=False),
            quality_score=float(result.get("quality_score", 0.3)),
        )
        db.add(entry)
        db.commit()

        logger.info("已导入: [%s] %s", cat, entry.title)
        return {"id": entry.id, "title": entry.title, "category": cat, "skipped": False}

    except Exception as e:
        logger.error("导入文件失败 %s: %s", path.name, e)
        db.rollback()
        return None
    finally:
        db.close()


async def _llm_extract(text: str, filename: str, category: str) -> dict | None:
    """使用 LLM 从教程文本中提取结构化知识"""
    db = SessionLocal()
    try:
        resolver = StageModelResolver(db)
        llm = resolver.get_llm_for_stage("learning_agent")
    except Exception as e:
        logger.error("获取 learning_agent LLM 失败: %s", e)
        return None
    finally:
        db.close()

    prompt = f"""## 教程文件: {filename}
## 分类: {category}

## 正文内容
{text}

请提取上述教程的核心写作知识。"""

    config = GenerationConfig(
        system=TUTORIAL_SYSTEM_PROMPT,
        temperature=0.4,
        max_tokens=2048,
    )

    try:
        result = await llm.generate(prompt, config)
        return _parse_json(result.content)
    except Exception as e:
        logger.error("LLM 提取失败: %s", e)
        return None


def _parse_json(text: str) -> dict | None:
    """从 LLM 输出中解析 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试找到第一个 { ... } 结构
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ── 批量导入 ──────────────────────────────────────────────────────

async def import_batch(
    base_dir: str | Path,
    use_llm: bool = True,
    max_files: int = 100,
    categories: list[str] | None = None,
) -> dict:
    """批量导入教程文件到知识库

    Returns: {imported: int, skipped: int, failed: int, total: int, entries: [...]}
    """
    files = scan_tutorial_dir(base_dir)

    if categories:
        files = [f for f in files if f["category"] in categories]

    files = files[:max_files]

    imported = 0
    skipped = 0
    failed = 0
    entries: list[dict] = []

    for f in files:
        result = await import_file(f["path"], f["category"], use_llm=use_llm)
        if result is None:
            failed += 1
        elif result.get("skipped"):
            skipped += 1
        else:
            imported += 1
            entries.append(result)

    logger.info(
        "批量导入完成: imported=%d skipped=%d failed=%d total=%d",
        imported, skipped, failed, len(files),
    )
    return {
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "total": len(files),
        "entries": entries,
    }
