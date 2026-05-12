"""智能章节切分器 — 50+ 正则模式 + 启发式评分

支持中文/英文/日文等多语言章节标题识别。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Chapter:
    """切分后的章节"""
    number: int
    title: str
    text: str
    start_pos: int = 0
    end_pos: int = 0

    @property
    def word_count(self) -> int:
        return len(self.text)

    def __repr__(self) -> str:
        return f"<Chapter {self.number}: {self.title!r} ({self.word_count} chars)>"


@dataclass
class SplitResult:
    """切分结果"""
    chapters: list[Chapter] = field(default_factory=list)
    pattern_used: str = ""
    total_chars: int = 0

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)


# ── 章节标题正则模式库 (50+ 模式) ────────────────────────────────────

# 中文数字映射
_CN_NUMS = "零一二三四五六七八九十百千"
_CN_NUM_PAT = f"[{_CN_NUMS}]+"

CHAPTER_PATTERNS: list[tuple[str, re.Pattern]] = [
    # ── 中文 "第X章" 系列 ──
    ("第X章", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+章[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X节", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+节[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X回", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+回[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X卷", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+卷[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X篇", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+篇[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X部", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+部[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X话", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+话[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X集", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+集[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X幕", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+幕[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X折", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+折[\s：:．.\-—]*(.*)", re.MULTILINE)),

    # ── 纯数字章节号 ──
    ("数字.标题", re.compile(r"^[ \t]*(\d{1,4})[．.、]\s*(.*)", re.MULTILINE)),
    ("数字、标题", re.compile(r"^[ \t]*(\d{1,4})、\s*(.*)", re.MULTILINE)),

    # ── "章节X" 格式 ──
    ("章节X", re.compile(r"^[ \t]*章节\s*(\d+)[\s：:．.\-—]*(.*)", re.MULTILINE)),

    # ── 卷/篇+章组合 ──
    ("X章X节", re.compile(rf"^[ \t]*第[{_CN_NUMS}\d]+章\s*第[{_CN_NUMS}\d]+节[\s：:．.\-—]*(.*)", re.MULTILINE)),

    # ── 英文 Chapter 系列 ──
    ("Chapter X", re.compile(r"^[ \t]*Chapter\s+(\d+|[IVXLC]+)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),
    ("CHAPTER X", re.compile(r"^[ \t]*CHAPTER\s+(\d+|[IVXLC]+)[\s:.\-—]*(.*)", re.MULTILINE)),
    ("Ch.X", re.compile(r"^[ \t]*Ch\.?\s*(\d+)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),
    ("Part X", re.compile(r"^[ \t]*Part\s+(\d+|[IVXLC]+)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),
    ("Book X", re.compile(r"^[ \t]*Book\s+(\d+|[IVXLC]+)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),
    ("Section X", re.compile(r"^[ \t]*Section\s+(\d+|[IVXLC]+)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),
    ("Act X", re.compile(r"^[ \t]*Act\s+(\d+|[IVXLC]+)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),
    ("Episode X", re.compile(r"^[ \t]*Episode\s+(\d+)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),
    ("Volume X", re.compile(r"^[ \t]*Volume\s+(\d+|[IVXLC]+)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),

    # ── 日文 ──
    ("第X話(日)", re.compile(r"^[ \t]*第(\d+)話[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("第X章(日)", re.compile(r"^[ \t]*第(\d+)章[\s：:．.\-—]*(.*)", re.MULTILINE)),

    # ── 韩文 ──
    ("제X장", re.compile(r"^[ \t]*제\s*(\d+)\s*장[\s:.\-—]*(.*)", re.MULTILINE)),
    ("제X화", re.compile(r"^[ \t]*제\s*(\d+)\s*화[\s:.\-—]*(.*)", re.MULTILINE)),

    # ── 网文特殊格式 ──
    ("正文 第X章", re.compile(rf"^[ \t]*正文\s+第[{_CN_NUMS}\d]+章[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("卷X 第X章", re.compile(rf"^[ \t]*卷[{_CN_NUMS}\d]+\s+第[{_CN_NUMS}\d]+章[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("【第X章】", re.compile(rf"^[ \t]*【第[{_CN_NUMS}\d]+章[】\]][\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("「第X章」", re.compile(rf"^[ \t]*「第[{_CN_NUMS}\d]+章」[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("(第X章)", re.compile(rf"^[ \t]*[（(]第[{_CN_NUMS}\d]+章[)）][\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("——第X章——", re.compile(rf"^[ \t]*[—\-]+\s*第[{_CN_NUMS}\d]+章[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("★第X章", re.compile(rf"^[ \t]*[★☆※◆◇]\s*第[{_CN_NUMS}\d]+章[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("序章/序幕", re.compile(r"^[ \t]*(序章|序幕|楔子|引子|前言|引言)[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("尾声/终章", re.compile(r"^[ \t]*(尾声|终章|后记|终幕|大结局|番外)[\s：:．.\-—]*(.*)", re.MULTILINE)),
    ("Prologue", re.compile(r"^[ \t]*(Prologue|Epilogue|Foreword|Preface|Introduction)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),

    # ── 分隔线风格 ──
    ("===分隔", re.compile(r"^[ \t]*(={3,}|—{3,}|\*{3,}|#{3,}|-{5,})[ \t]*$", re.MULTILINE)),

    # ── 自增数字标题 (独占一行的数字) ──
    ("独立数字行", re.compile(r"^[ \t]*(\d{1,4})[ \t]*$", re.MULTILINE)),

    # ── 网文：括号数字 ──
    ("(数字)", re.compile(r"^[ \t]*[（(]\s*(\d{1,4})\s*[)）][\s：:．.\-—]*(.*)", re.MULTILINE)),

    # ── 上/中/下 篇 ──
    ("上中下篇", re.compile(r"^[ \t]*(上篇|中篇|下篇|上卷|中卷|下卷|上部|中部|下部)[\s：:．.\-—]*(.*)", re.MULTILINE)),

    # ── 天干地支 ──
    ("天干地支", re.compile(r"^[ \t]*(甲|乙|丙|丁|戊|己|庚|辛|壬|癸)[\s：:．.\-—]+(.*)", re.MULTILINE)),

    # ── 子丑寅卯 ──
    ("地支", re.compile(r"^[ \t]*(子|丑|寅|卯|辰|巳|午|未|申|酉|戌|亥)[\s：:．.\-—]+(.*)", re.MULTILINE)),

    # ── Scene/场景标记 ──
    ("Scene X", re.compile(r"^[ \t]*Scene\s+(\d+)[\s:.\-—]*(.*)", re.MULTILINE | re.IGNORECASE)),
]


# ── 最小章节长度 (低于此值会合并到上一章) ─────────────────────────────
MIN_CHAPTER_CHARS = 200

# ── 最大单章字符 (超过此值说明可能漏切) ─────────────────────────────
MAX_CHAPTER_CHARS = 50000


def split_chapters(text: str, min_chars: int = MIN_CHAPTER_CHARS) -> SplitResult:
    """智能章节切分

    策略:
    1. 逐一尝试所有模式，记录匹配数
    2. 选择匹配数最多且 ≥ 2 的模式
    3. 按该模式切分文本
    4. 短章节合并到上一章
    5. 如果无匹配，按固定字数切分作为兜底
    """
    if not text.strip():
        return SplitResult(chapters=[], total_chars=0)

    # ── 第一步: 评分选择最佳模式 ──
    best_pattern_name = ""
    best_pattern: re.Pattern | None = None
    best_matches: list[re.Match] = []

    for name, pattern in CHAPTER_PATTERNS:
        matches = list(pattern.finditer(text))
        if len(matches) >= 2 and len(matches) > len(best_matches):
            best_pattern_name = name
            best_pattern = pattern
            best_matches = matches

    # ── 第二步: 切分 ──
    if best_pattern and best_matches:
        logger.info("章节模式: %s, 匹配 %d 处", best_pattern_name, len(best_matches))
        chapters = _split_by_matches(text, best_matches)
    else:
        logger.warning("未匹配到章节模式，使用固定字数切分")
        chapters = _split_by_length(text)
        best_pattern_name = "fixed_length"

    # ── 第三步: 合并过短章节 ──
    chapters = _merge_short_chapters(chapters, min_chars)

    # ── 第四步: 重新编号 ──
    for i, ch in enumerate(chapters):
        ch.number = i + 1

    return SplitResult(
        chapters=chapters,
        pattern_used=best_pattern_name,
        total_chars=len(text),
    )


def _split_by_matches(text: str, matches: list[re.Match]) -> list[Chapter]:
    """按正则匹配位置切分文本"""
    chapters: list[Chapter] = []

    # 如果第一个匹配之前有内容，作为"前言"
    if matches[0].start() > MIN_CHAPTER_CHARS:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            chapters.append(Chapter(
                number=0,
                title="前言",
                text=preamble,
                start_pos=0,
                end_pos=matches[0].start(),
            ))

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        # 提取标题: 取匹配行的全文
        title_line = m.group(0).strip()
        # 正文从匹配行之后开始
        body_start = m.end()
        body = text[body_start:end].strip()

        chapters.append(Chapter(
            number=i + 1,
            title=title_line,
            text=body,
            start_pos=start,
            end_pos=end,
        ))

    return chapters


def _split_by_length(text: str, chunk_size: int = 5000) -> list[Chapter]:
    """按固定字数切分 (兜底方案)"""
    chapters: list[Chapter] = []
    lines = text.split("\n")
    current_text: list[str] = []
    current_len = 0

    for line in lines:
        current_text.append(line)
        current_len += len(line) + 1
        if current_len >= chunk_size:
            ch_text = "\n".join(current_text).strip()
            if ch_text:
                chapters.append(Chapter(
                    number=len(chapters) + 1,
                    title=f"段落 {len(chapters) + 1}",
                    text=ch_text,
                ))
            current_text = []
            current_len = 0

    # 剩余内容
    if current_text:
        ch_text = "\n".join(current_text).strip()
        if ch_text:
            chapters.append(Chapter(
                number=len(chapters) + 1,
                title=f"段落 {len(chapters) + 1}",
                text=ch_text,
            ))

    return chapters


def _merge_short_chapters(chapters: list[Chapter], min_chars: int) -> list[Chapter]:
    """将过短的章节合并到前一章"""
    if not chapters:
        return chapters

    merged: list[Chapter] = [chapters[0]]
    for ch in chapters[1:]:
        if ch.word_count < min_chars and merged:
            # 合并到前一章
            prev = merged[-1]
            prev.text = prev.text + "\n\n" + ch.title + "\n" + ch.text
            prev.end_pos = ch.end_pos
        else:
            merged.append(ch)

    return merged
