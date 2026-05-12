"""实体扫描器 - jieba 分词 + 高频实体提取

对全文进行分词统计，提取高频人名/地名/组织等实体，
构建实体词典供后续 LLM 章节提取参考。
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_jieba_cache = None


def _get_jieba():
    global _jieba_cache
    if _jieba_cache is None:
        import jieba
        import jieba.posseg as pseg
        jieba.setLogLevel(logging.WARNING)
        _jieba_cache = (jieba, pseg)
    return _jieba_cache


@dataclass
class Entity:
    name: str
    category: str
    frequency: int = 0
    aliases: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"<Entity {self.category}:{self.name} freq={self.frequency}>"


@dataclass
class ScanResult:
    entities: list[Entity] = field(default_factory=list)
    top_persons: list[Entity] = field(default_factory=list)
    top_locations: list[Entity] = field(default_factory=list)
    top_items: list[Entity] = field(default_factory=list)
    word_count: int = 0
    unique_words: int = 0

    def get_entity_names(self, category: Optional[str] = None) -> list[str]:
        if category:
            return [e.name for e in self.entities if e.category == category]
        return [e.name for e in self.entities]

    def to_dict(self) -> dict:
        return {
            "entities": [
                {"name": e.name, "category": e.category, "frequency": e.frequency}
                for e in self.entities
            ],
            "top_persons": [e.name for e in self.top_persons],
            "top_locations": [e.name for e in self.top_locations],
            "word_count": self.word_count,
            "unique_words": self.unique_words,
        }


POS_CATEGORY_MAP = {
    "nr": "person", "nr1": "person", "nr2": "person",
    "nrj": "person", "nrf": "person",
    "ns": "location", "nsf": "location",
    "nt": "organization",
    "nz": "other",
}

STOP_WORDS = frozenset([
    "self", "what", "one",
    "\u81ea\u5df1", "\u4ec0\u4e48", "\u4e00\u4e2a", "\u8fd9\u4e2a",
    "\u90a3\u4e2a", "\u4ed6\u4eec", "\u5979\u4eec", "\u6211\u4eec",
    "\u6ca1\u6709", "\u4e0d\u662f", "\u53ef\u4ee5", "\u5df2\u7ecf",
    "\u8fd9\u6837", "\u90a3\u6837", "\u600e\u4e48", "\u5982\u4f55",
    "\u77e5\u9053", "\u89c9\u5f97", "\u53ef\u80fd", "\u5e94\u8be5",
    "\u4e00\u4e9b", "\u8fd9\u4e9b", "\u90a3\u4e9b", "\u6240\u6709",
    "\u8fd8\u662f", "\u6216\u8005", "\u4f46\u662f", "\u56e0\u4e3a",
    "\u6240\u4ee5", "\u5982\u679c", "\u867d\u7136", "\u800c\u4e14",
    "\u7136\u540e", "\u65f6\u5019", "\u5730\u65b9", "\u4e1c\u897f",
    "\u4e8b\u60c5", "\u95ee\u9898", "\u73b0\u5728", "\u4eca\u5929",
    "\u660e\u5929", "\u6628\u5929", "\u4e00\u4e0b", "\u4e00\u70b9",
    "\u4e00\u76f4", "\u4e00\u8d77", "\u4e00\u6837", "\u4e00\u8fb9",
    "\u8d77\u6765", "\u51fa\u6765", "\u51fa\u53bb", "\u8fdb\u6765",
    "\u8fdb\u53bb", "\u4e0a\u53bb", "\u4e0b\u6765", "\u8fc7\u6765",
    "\u8fc7\u53bb", "\u56de\u6765", "\u56de\u53bb", "\u4e0d\u8fc7",
    "\u53ea\u662f", "\u5c31\u662f", "\u8fd8\u6709", "\u9664\u4e86",
])

_CJK_NAME_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}$")


def _is_likely_person_name(word: str, pos: str) -> bool:
    """判断是否可能是人名"""
    if pos.startswith("nr"):
        return True
    if not _CJK_NAME_RE.match(word):
        return False
    if len(word) < 2 or len(word) > 4:
        return False
    return True


def scan_entities(
    text: str,
    top_n: int = 50,
    min_freq: int = 3,
    custom_names: Optional[list[str]] = None,
) -> ScanResult:
    """扫描文本，提取高频实体

    Args:
        text: 待扫描的全文文本
        top_n: 每类返回的最大实体数
        min_freq: 最小出现频次
        custom_names: 自定义人名列表 (会加入 jieba 词典)
    """
    jieba_mod, pseg = _get_jieba()

    if custom_names:
        for name in custom_names:
            jieba_mod.add_word(name, freq=1000, tag="nr")

    person_counter: Counter = Counter()
    location_counter: Counter = Counter()
    org_counter: Counter = Counter()
    other_counter: Counter = Counter()
    total_words = 0
    unique_set: set[str] = set()

    for word, pos in pseg.cut(text):
        word = word.strip()
        if not word or len(word) < 2:
            continue
        if word in STOP_WORDS:
            continue

        total_words += 1
        unique_set.add(word)

        category = POS_CATEGORY_MAP.get(pos)
        if category == "person" or (category is None and _is_likely_person_name(word, pos)):
            person_counter[word] += 1
        elif category == "location":
            location_counter[word] += 1
        elif category == "organization":
            org_counter[word] += 1
        elif category == "other" and _CJK_NAME_RE.match(word):
            other_counter[word] += 1

    # -- dialogue name extraction (from quoted speech attribution) --
    dialogue_names = _extract_dialogue_names(text)
    for name, count in dialogue_names.items():
        person_counter[name] += count

    # -- build entity lists --
    entities: list[Entity] = []

    top_persons = _counter_to_entities(person_counter, "person", top_n, min_freq)
    top_locations = _counter_to_entities(location_counter, "location", top_n, min_freq)
    top_orgs = _counter_to_entities(org_counter, "organization", top_n, min_freq)
    top_items = _counter_to_entities(other_counter, "item", top_n, min_freq)

    entities.extend(top_persons)
    entities.extend(top_locations)
    entities.extend(top_orgs)
    entities.extend(top_items)

    entities.sort(key=lambda e: e.frequency, reverse=True)

    return ScanResult(
        entities=entities,
        top_persons=top_persons,
        top_locations=top_locations,
        top_items=top_items,
        word_count=total_words,
        unique_words=len(unique_set),
    )


def _counter_to_entities(
    counter: Counter, category: str, top_n: int, min_freq: int
) -> list[Entity]:
    items = [(w, c) for w, c in counter.most_common(top_n * 2) if c >= min_freq]
    return [Entity(name=w, category=category, frequency=c) for w, c in items[:top_n]]


_DIALOGUE_ATTR_RE = re.compile(
    r"([\u4e00-\u9fff]{2,4})\s*(?:\u8bf4|\u9053|\u95ee|\u7b54|\u53eb|\u559c|\u6012|\u7b11|\u53f9|\u55b5|\u54fc|\u5410\u69fd)"
)


def _extract_dialogue_names(text: str) -> Counter:
    """从对话归属语句中提取人名 (e.g. 'XXX said/asked/answered')"""
    counter: Counter = Counter()
    for m in _DIALOGUE_ATTR_RE.finditer(text):
        name = m.group(1)
        if name not in STOP_WORDS and len(name) >= 2:
            counter[name] += 1
    return counter


# ── LLM 实体确认与补充 ─────────────────────────────────────────

ENTITY_CONFIRM_SYSTEM = """你是一位小说文本分析专家。用户会给你一组从分词工具提取的疑似角色名列表，以及一段小说文本样本。

请完成以下任务：
1. 从候选列表中筛选出真正的角色名（去除误识别的普通词汇）
2. 从文本样本中发现候选列表遗漏的角色名
3. 为确认的角色标注类型

严格按 JSON 格式输出：
{
  "confirmed_persons": [
    {"name": "角色名", "confidence": "high/medium", "note": "主角/配角/提及"}
  ],
  "rejected": ["被误识别的词"],
  "discovered": [
    {"name": "新发现的角色名", "confidence": "high/medium", "note": "备注"}
  ]
}"""


async def confirm_entities_with_llm(
    scan_result: ScanResult,
    text_sample: str,
    llm,
) -> ScanResult:
    """使用 LLM 确认 jieba 扫描结果并补充遗漏实体

    Args:
        scan_result: jieba 扫描结果
        text_sample: 文本样本（取前1万字）
        llm: LLM 客户端 (app.llm.client.LLMClient)

    Returns:
        增强后的 ScanResult（原地修改并返回）
    """
    from app.llm.client import GenerationConfig

    # 准备候选列表
    candidates = [e.name for e in scan_result.top_persons[:30]]
    if not candidates:
        return scan_result

    sample = text_sample[:8000]
    prompt = f"""## 候选角色名列表（来自分词工具）
{', '.join(candidates)}

## 文本样本
{sample}

请筛选并补充角色名。"""

    config = GenerationConfig(
        system=ENTITY_CONFIRM_SYSTEM,
        temperature=0.3,
        max_tokens=2048,
    )

    try:
        result = await llm.generate(prompt, config)
        parsed = _parse_entity_response(result.content)

        # 处理被拒绝的实体
        rejected = set(parsed.get("rejected", []))
        if rejected:
            scan_result.top_persons = [
                e for e in scan_result.top_persons if e.name not in rejected
            ]
            scan_result.entities = [
                e for e in scan_result.entities if e.name not in rejected
            ]

        # 添加新发现的实体
        existing_names = {e.name for e in scan_result.entities}
        for d in parsed.get("discovered", []):
            name = d.get("name", "").strip()
            if name and name not in existing_names and len(name) >= 2:
                new_entity = Entity(
                    name=name,
                    category="person",
                    frequency=1,
                )
                scan_result.entities.append(new_entity)
                scan_result.top_persons.append(new_entity)
                existing_names.add(name)

        logger.info(
            "LLM 实体确认: 拒绝 %d, 新发现 %d",
            len(rejected),
            len(parsed.get("discovered", [])),
        )

    except Exception as e:
        logger.warning("LLM 实体确认失败（跳过）: %s", e)

    return scan_result


def _parse_entity_response(content: str) -> dict:
    """解析 LLM 实体确认响应"""
    import json as _json
    content = content.strip()

    # 尝试 ```json``` 块
    block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    text = block.group(1).strip() if block else content

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        text = text[first:last + 1]

    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        # 修复尾部逗号
        text = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return _json.loads(text)
        except _json.JSONDecodeError:
            return {}
