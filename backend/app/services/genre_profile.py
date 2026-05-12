"""题材规则 (Genre Profile) 加载与管理

从 app/data/genres/*.md 加载 markdown 格式的题材规则文件，
解析为结构化数据供写作 prompt 注入。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_GENRES_DIR = Path(__file__).resolve().parent.parent / "data" / "genres"


@dataclass
class GenreProfile:
    """题材规则的结构化表示"""
    id: str = ""
    name: str = ""
    name_en: str = ""
    description: str = ""
    chapter_types: list[str] = field(default_factory=list)
    fatigue_words: list[str] = field(default_factory=list)
    satisfaction_types: list[str] = field(default_factory=list)
    pacing_rules: list[str] = field(default_factory=list)
    numerical_rules: list[str] = field(default_factory=list)
    language_rules: list[str] = field(default_factory=list)
    taboos: list[str] = field(default_factory=list)
    narrative_guidance: list[str] = field(default_factory=list)
    raw_markdown: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "name_en": self.name_en,
            "description": self.description,
            "chapter_types": self.chapter_types,
            "fatigue_words": self.fatigue_words,
            "satisfaction_types": self.satisfaction_types,
            "pacing_rules": self.pacing_rules,
            "numerical_rules": self.numerical_rules,
            "language_rules": self.language_rules,
            "taboos": self.taboos,
            "narrative_guidance": self.narrative_guidance,
        }

    def to_prompt_section(self) -> str:
        """生成可直接注入写作 system prompt 的文本段"""
        parts = [f"## 题材规则 — {self.name}（{self.name_en}）\n"]

        if self.fatigue_words:
            parts.append("### 疲劳词（写作中必须规避）")
            parts.append("、".join(self.fatigue_words))
            parts.append("")

        if self.satisfaction_types:
            parts.append("### 爽点类型")
            for s in self.satisfaction_types:
                parts.append(f"- {s}")
            parts.append("")

        if self.pacing_rules:
            parts.append("### 节奏规则")
            for r in self.pacing_rules:
                parts.append(f"- {r}")
            parts.append("")

        if self.language_rules:
            parts.append("### 语言铁律")
            for r in self.language_rules:
                parts.append(f"- {r}")
            parts.append("")

        if self.taboos:
            parts.append("### 题材禁忌")
            for t in self.taboos:
                parts.append(f"- {t}")
            parts.append("")

        if self.narrative_guidance:
            parts.append("### 叙事指导")
            for g in self.narrative_guidance:
                parts.append(f"- {g}")

        return "\n".join(parts)


# ── 解析器 ──────────────────────────────────────────────────────

_SECTION_MAP = {
    "基本信息": "_parse_basic_info",
    "章节类型": "chapter_types",
    "疲劳词表": "fatigue_words",
    "爽点类型": "satisfaction_types",
    "节奏规则": "pacing_rules",
    "数值体系规则": "numerical_rules",
    "语言铁律": "language_rules",
    "题材禁忌": "taboos",
    "叙事指导": "narrative_guidance",
}


def _parse_genre_md(text: str) -> GenreProfile:
    """解析题材 markdown 为 GenreProfile"""
    profile = GenreProfile(raw_markdown=text)

    # 按 ## 标题拆分
    sections: dict[str, str] = {}
    current_section = ""
    current_lines: list[str] = []

    for line in text.split("\n"):
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_section:
                sections[current_section] = "\n".join(current_lines)
            current_section = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_lines)

    # 解析各 section
    for section_title, target in _SECTION_MAP.items():
        if section_title not in sections:
            continue

        content = sections[section_title]

        if target == "_parse_basic_info":
            _fill_basic_info(profile, content)
        else:
            items = _extract_list_items(content)
            setattr(profile, target, items)

    return profile


def _fill_basic_info(profile: GenreProfile, content: str) -> None:
    """解析基本信息 section"""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- id:"):
            profile.id = line.split(":", 1)[1].strip()
        elif line.startswith("- name:") and "name_en" not in line:
            profile.name = line.split(":", 1)[1].strip()
        elif line.startswith("- name_en:"):
            profile.name_en = line.split(":", 1)[1].strip()
        elif line.startswith("- description:"):
            profile.description = line.split(":", 1)[1].strip()


def _extract_list_items(content: str) -> list[str]:
    """提取 markdown 列表项"""
    items = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            item = line[2:].strip()
            if item:
                items.append(item)
    return items


# ── 公共接口 ────────────────────────────────────────────────────

_cache: dict[str, GenreProfile] = {}


def load_all_genres(force_reload: bool = False) -> dict[str, GenreProfile]:
    """加载所有题材规则文件，返回 {id: GenreProfile}"""
    global _cache
    if _cache and not force_reload:
        return _cache

    _cache.clear()

    if not _GENRES_DIR.exists():
        logger.warning("题材目录不存在: %s", _GENRES_DIR)
        return _cache

    for md_file in sorted(_GENRES_DIR.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            profile = _parse_genre_md(text)
            if not profile.id:
                profile.id = md_file.stem
            _cache[profile.id] = profile
            logger.debug("加载题材: %s (%s)", profile.name, profile.id)
        except Exception as e:
            logger.error("加载题材文件失败 %s: %s", md_file.name, e)

    logger.info("已加载 %d 个题材规则", len(_cache))
    return _cache


def get_genre(genre_id: str) -> Optional[GenreProfile]:
    """获取指定题材"""
    if not _cache:
        load_all_genres()
    return _cache.get(genre_id)


def get_genre_for_novel_genre(novel_genre: str) -> Optional[GenreProfile]:
    """从小说的 genre 字段模糊匹配到题材规则"""
    if not _cache:
        load_all_genres()
    if not novel_genre:
        return None

    g = novel_genre.strip().lower()

    # 精确匹配
    if g in _cache:
        return _cache[g]

    # 中文名匹配
    for profile in _cache.values():
        if profile.name == novel_genre or profile.name_en.lower() == g:
            return profile

    # 模糊包含
    for profile in _cache.values():
        if profile.name in novel_genre or novel_genre in profile.name:
            return profile

    return None


def list_genres() -> list[dict]:
    """列出所有可用题材（轻量摘要）"""
    if not _cache:
        load_all_genres()
    return [
        {
            "id": p.id,
            "name": p.name,
            "name_en": p.name_en,
            "description": p.description,
            "fatigue_words_count": len(p.fatigue_words),
        }
        for p in _cache.values()
    ]
