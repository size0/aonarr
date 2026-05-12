"""文风指纹分析 - 句长分布/对话占比/修辞密度/节奏模式

纯统计 + 可选 LLM 深度分析。
使用 get_llm_for_stage("style_detection") 获取客户端。
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from app.llm.client import LLMClient, GenerationConfig

logger = logging.getLogger(__name__)


@dataclass
class StyleFingerprint:
    """文风指纹"""
    # 句长分布
    avg_sentence_length: float = 0.0
    median_sentence_length: float = 0.0
    sentence_length_std: float = 0.0
    short_sentence_ratio: float = 0.0   # < 10 chars
    long_sentence_ratio: float = 0.0    # > 50 chars
    sentence_count: int = 0

    # 段落
    avg_paragraph_length: float = 0.0
    paragraph_count: int = 0

    # 对话
    dialogue_ratio: float = 0.0         # 对话占全文比例
    dialogue_count: int = 0
    avg_dialogue_length: float = 0.0

    # 修辞
    rhetoric_density: float = 0.0       # 修辞手法密度 (per 1000 chars)
    rhetoric_counts: dict = field(default_factory=dict)

    # 节奏
    rhythm_pattern: str = ""            # fast / medium / slow / varied
    action_ratio: float = 0.0          # 动作场景占比
    description_ratio: float = 0.0     # 描写占比

    # 用词
    vocab_richness: float = 0.0        # 词汇丰富度 (TTR)
    top_verbs: list[str] = field(default_factory=list)
    top_adjectives: list[str] = field(default_factory=list)

    # LLM 补充
    llm_style_summary: str = ""
    llm_style_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sentence": {
                "avg_length": round(self.avg_sentence_length, 1),
                "median_length": round(self.median_sentence_length, 1),
                "std": round(self.sentence_length_std, 1),
                "short_ratio": round(self.short_sentence_ratio, 3),
                "long_ratio": round(self.long_sentence_ratio, 3),
                "count": self.sentence_count,
            },
            "paragraph": {
                "avg_length": round(self.avg_paragraph_length, 1),
                "count": self.paragraph_count,
            },
            "dialogue": {
                "ratio": round(self.dialogue_ratio, 3),
                "count": self.dialogue_count,
                "avg_length": round(self.avg_dialogue_length, 1),
            },
            "rhetoric": {
                "density": round(self.rhetoric_density, 3),
                "counts": self.rhetoric_counts,
            },
            "rhythm": {
                "pattern": self.rhythm_pattern,
                "action_ratio": round(self.action_ratio, 3),
                "description_ratio": round(self.description_ratio, 3),
            },
            "vocabulary": {
                "richness": round(self.vocab_richness, 4),
                "top_verbs": self.top_verbs,
                "top_adjectives": self.top_adjectives,
            },
            "llm_summary": self.llm_style_summary,
            "llm_tags": self.llm_style_tags,
        }


# ---- sentence splitting ----

_SENTENCE_END_RE = re.compile(
    r'[。！？!?\u2026.]+[\s""\u201d\u300d）)]*'
)

_DIALOGUE_RE = re.compile(
    r'[\u201c"](.*?)[\u201d"]'
    r'|[\u300c](.*?)[\u300d]'
    r'|["](.*?)["]',
    re.DOTALL,
)

# ---- rhetoric patterns ----

RHETORIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("simile_like", re.compile(r"(?:好像|仿佛|宛如|犹如|如同|好似|恰似|像是).{2,20}(?:一样|一般|似的|般)")),
    ("simile_like_en", re.compile(r"\blike\s+(?:a|an|the)\b", re.IGNORECASE)),
    ("metaphor", re.compile(r"(?:是|成了|变成|化作|化为).{2,15}(?:的|了)")),
    ("parallelism", re.compile(r"(.{4,12})[，,](.{4,12})[，,](.{4,12})")),
    ("rhetorical_q", re.compile(r"(?:难道|岂|何尝|怎能|哪里).{2,30}[？?]")),
    ("exaggeration", re.compile(r"(?:无数|万千|千万|成千上万|铺天盖地|惊天动地|翻天覆地)")),
    ("personification", re.compile(r"(?:风|月|花|草|树|云|山|水|雨|雪).{0,4}(?:笑|哭|唱|跳|舞|说|叹|怒|喜)")),
    ("repetition", re.compile(r"([\u4e00-\u9fff]{2,4})[，,\s]+([\u4e00-\u9fff]{2,4})[，,\s]+\1")),
    ("contrast", re.compile(r"(?:然而|却|可是|但|不过|偏偏|反而|倒是)")),
    ("onomatopoeia", re.compile(
        r"(?:哗哗|轰隆|咔嚓|嘎吱|淅淅沥沥|叮叮当当|噼里啪啦|叽叽喳喳|咕噜|滴答)"
    )),
]


def analyze_style(text: str) -> StyleFingerprint:
    """纯统计文风分析 (不调用 LLM)"""
    fp = StyleFingerprint()

    if not text.strip():
        return fp

    # ---- sentences ----
    sentences = [s.strip() for s in _SENTENCE_END_RE.split(text) if s.strip()]
    lengths = [len(s) for s in sentences]
    fp.sentence_count = len(lengths)

    if lengths:
        fp.avg_sentence_length = sum(lengths) / len(lengths)
        sorted_lens = sorted(lengths)
        mid = len(sorted_lens) // 2
        fp.median_sentence_length = (
            sorted_lens[mid] if len(sorted_lens) % 2 == 1
            else (sorted_lens[mid - 1] + sorted_lens[mid]) / 2
        )
        mean = fp.avg_sentence_length
        variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
        fp.sentence_length_std = variance ** 0.5
        fp.short_sentence_ratio = sum(1 for x in lengths if x < 10) / len(lengths)
        fp.long_sentence_ratio = sum(1 for x in lengths if x > 50) / len(lengths)

    # ---- paragraphs ----
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    fp.paragraph_count = len(paragraphs)
    if paragraphs:
        fp.avg_paragraph_length = sum(len(p) for p in paragraphs) / len(paragraphs)

    # ---- dialogue ----
    dialogues = _DIALOGUE_RE.findall(text)
    # findall with groups returns tuples
    dialogue_texts = []
    for groups in dialogues:
        if isinstance(groups, tuple):
            for g in groups:
                if g:
                    dialogue_texts.append(g)
        elif groups:
            dialogue_texts.append(groups)

    fp.dialogue_count = len(dialogue_texts)
    total_dialogue_chars = sum(len(d) for d in dialogue_texts)
    fp.dialogue_ratio = total_dialogue_chars / len(text) if text else 0.0
    fp.avg_dialogue_length = (
        total_dialogue_chars / len(dialogue_texts) if dialogue_texts else 0.0
    )

    # ---- rhetoric ----
    rhetoric_total = 0
    for name, pattern in RHETORIC_PATTERNS:
        count = len(pattern.findall(text))
        if count > 0:
            fp.rhetoric_counts[name] = count
            rhetoric_total += count
    fp.rhetoric_density = rhetoric_total / (len(text) / 1000) if text else 0.0

    # ---- rhythm ----
    fp.rhythm_pattern = _classify_rhythm(fp)

    # ---- vocabulary (jieba) ----
    try:
        _analyze_vocabulary(text, fp)
    except Exception as e:
        logger.warning("Vocabulary analysis failed: %s", e)

    return fp


def _classify_rhythm(fp: StyleFingerprint) -> str:
    """根据句长分布判断节奏"""
    if fp.short_sentence_ratio > 0.5:
        return "fast"
    elif fp.long_sentence_ratio > 0.3:
        return "slow"
    elif fp.sentence_length_std > 15:
        return "varied"
    else:
        return "medium"


def _analyze_vocabulary(text: str, fp: StyleFingerprint) -> None:
    """使用 jieba 分析词汇丰富度和高频词"""
    import jieba.posseg as pseg
    import jieba
    jieba.setLogLevel(logging.WARNING)

    verbs: Counter = Counter()
    adjectives: Counter = Counter()
    all_words: list[str] = []
    unique_words: set[str] = set()

    for word, pos in pseg.cut(text):
        w = word.strip()
        if len(w) < 2:
            continue
        all_words.append(w)
        unique_words.add(w)
        if pos.startswith("v") and not pos.startswith("vn"):
            verbs[w] += 1
        elif pos.startswith("a"):
            adjectives[w] += 1

    if all_words:
        fp.vocab_richness = len(unique_words) / len(all_words)
    fp.top_verbs = [w for w, _ in verbs.most_common(10)]
    fp.top_adjectives = [w for w, _ in adjectives.most_common(10)]


STYLE_SYSTEM_PROMPT = """你是一个文学风格分析专家。基于提供的文本样本和统计数据，分析作者的写作风格。

请严格按照 JSON 格式输出：
{
  "style_summary": "风格概述 (100-200字，描述文风特征)",
  "style_tags": ["标签1", "标签2", ...],
  "writing_level": "通俗/文学/学术/混合",
  "era_feel": "时代感受 (古典/现代/后现代/混合)",
  "similar_authors": ["风格相似的知名作家"]
}"""


async def analyze_style_with_llm(
    text: str,
    llm: LLMClient,
    fp: Optional[StyleFingerprint] = None,
    db=None,
) -> StyleFingerprint:
    """结合 LLM 进行深度风格分析"""
    if fp is None:
        fp = analyze_style(text)

    # 取样本 (开头/中间/结尾各取一段)
    sample_size = 2000
    total = len(text)
    samples = []
    if total <= sample_size * 3:
        samples.append(text)
    else:
        samples.append(text[:sample_size])
        mid = total // 2
        samples.append(text[mid - sample_size // 2 : mid + sample_size // 2])
        samples.append(text[-sample_size:])

    sample_text = "\n---\n".join(samples)

    stats_info = (
        f"avg_sentence_len={fp.avg_sentence_length:.1f}, "
        f"dialogue_ratio={fp.dialogue_ratio:.1%}, "
        f"rhetoric_density={fp.rhetoric_density:.2f}/1000chars, "
        f"rhythm={fp.rhythm_pattern}, "
        f"vocab_richness={fp.vocab_richness:.4f}"
    )

    prompt = f"""## 文本样本 (开头/中间/结尾)
{sample_text}

## 统计数据
{stats_info}

请分析此作品的写作风格。"""

    # 优先从 DB 加载风格检测提示词
    system = STYLE_SYSTEM_PROMPT
    if db is not None:
        from app.services.prompt_loader import PromptLoader
        db_prompt = PromptLoader(db).get_prompt("style_detection")
        if db_prompt:
            system = db_prompt

    config = GenerationConfig(
        system=system,
        temperature=0.5,
        max_tokens=2048,
    )

    try:
        result = await llm.generate(prompt, config)
        parsed = _parse_style_response(result.content)
        fp.llm_style_summary = parsed.get("style_summary", "")
        fp.llm_style_tags = parsed.get("style_tags", [])
    except Exception as e:
        logger.error("LLM style analysis failed: %s", e)
        fp.llm_style_summary = f"[analysis failed: {e}]"

    return fp


def _parse_style_response(content: str) -> dict:
    """Parse LLM style analysis response"""
    import json as _json
    content = content.strip()
    block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    text = block.group(1).strip() if block else content
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        text = text[first:last + 1]
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return {"style_summary": content[:500]}
