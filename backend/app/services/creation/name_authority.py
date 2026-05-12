"""NameAuthority — 人名归一化与别名解析

职责：
1. 维护一份规范人名 → 别名映射
2. 过滤泛称代词（他/她/某人/弟子…）
3. 在 Observer / Reflector / Composer 中将非规范引用映射到角色实体
4. 支持从 Character 模型的 traits JSON 中提取别名

用法：
    authority = NameAuthority.from_novel(db, novel_id)
    canonical = authority.resolve("苏哥")  # → "苏凌风"
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.models.novel import Character

# ── 泛称词表（代词 + 职位称呼 + 模糊描述） ──────────────────────

GENERIC_REFERENCES: set[str] = {
    # 代词
    "他", "她", "它", "他们", "她们", "它们", "自己", "本人", "对方",
    # 泛称人物
    "那人", "这个人", "那个人", "某人", "此人", "这人", "这位", "那位",
    "男人", "女人", "男孩", "女孩", "少年", "少女", "青年", "老人", "老者",
    "中年人", "孩子", "年轻人", "年轻男子", "年轻女子",
    "女子", "男子", "姑娘", "小姐", "公子", "少爷", "先生", "夫人",
    # 群体
    "大家", "众人", "所有人", "旁人", "路人", "敌人", "同伴", "队友",
    "士兵", "军官", "船员",
    # 亲属/关系
    "老师", "同学", "前辈", "后辈", "大哥", "大姐", "叔叔", "阿姨",
    "父亲", "母亲", "哥哥", "姐姐", "弟弟", "妹妹",
    "老板", "店员", "医生", "护士", "警察", "司机",
    # 古风/玄幻
    "掌柜", "小二", "店主", "店家", "客人", "客官", "使者", "信使",
    "弟子", "师父", "师傅", "师兄", "师弟", "师姐", "师妹",
    "道友", "仙子", "仙师", "小友", "阁下", "老夫", "在下", "妾身",
    "主人", "大人", "长老", "掌门", "帮主", "教主", "堂主", "队长", "领队",
}

# 模糊描述正则（"那个黑衣男子"之类）
_FUZZY_DESC_RE = re.compile(
    r"(?:这|那|某)?(?:个|位|名)?"
    r"(?:年轻|年长|中年|老年|高大|瘦弱|矮小|陌生|神秘|普通|"
    r"黑衣|白衣|红衣|蓝衣|灰衣|青衣|黑袍|白袍|青袍|蒙面|"
    r"戴帽|戴面具|披斗篷)?"
    r"(?:男子|女子|少年|少女|青年|老人|老者|修士|人影|身影)$"
)

_GENERIC_PATTERN_RE = re.compile(
    r"(?:这|那|某)?(?:个|位|名|些)?"
    r"(?:人|男人|女人|男孩|女孩|少年|少女|青年|老人|老者|孩子|"
    r"老师|同学|前辈|后辈|大哥|大姐|叔叔|阿姨|父亲|母亲|"
    r"哥哥|姐姐|弟弟|妹妹|队友|同伴|敌人|船员|士兵|军官)$"
)


def normalize_name(value: Any) -> str:
    """规范化名字：去空白、去引号括号包裹"""
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    return text.strip("「」『』""''\"'`（）()[]【】<>《》")


def is_generic_reference(value: Any) -> bool:
    """判断是否为泛称/代词，不应作为角色实体"""
    text = normalize_name(value)
    if not text or len(text) <= 1:
        return True
    if text in GENERIC_REFERENCES:
        return True
    if _FUZZY_DESC_RE.fullmatch(text):
        return True
    if _GENERIC_PATTERN_RE.fullmatch(text):
        return True
    return False


def _safe_json(value: Any) -> Any:
    if not value:
        return None
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _extract_alias_strings(value: Any, *, trusted: bool = False) -> list[str]:
    """从灵活的 JSON 结构中提取别名字符串"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if trusted else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_extract_alias_strings(item, trusted=trusted))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        alias_keys = {"alias", "aliases", "别名", "昵称", "称呼", "称号", "name_aliases"}
        for key, item in value.items():
            if str(key).lower() in alias_keys:
                out.extend(_extract_alias_strings(item, trusted=True))
        return out
    return []


def extract_character_aliases(char: Character) -> set[str]:
    """从 Character 模型提取别名集合"""
    canonical = normalize_name(char.name)
    aliases = {canonical}

    # 从 traits JSON 提取
    traits = _safe_json(char.traits)
    for val in _extract_alias_strings(traits):
        aliases.add(normalize_name(val))

    # 从 description 提取 — 匹配"又名XXX"/"别号XXX"/"人称XXX"
    desc = char.description or ""
    _alias_re = re.compile(r'(?:又名|别号|人称|外号|绰号)[：:]?\s*(\S{2,8})')
    for m in _alias_re.finditer(desc):
        aliases.add(normalize_name(m.group(1)))

    # 处理带分隔符的名字：苏·凌风 → 苏凌风 + 凌风
    if "·" in canonical or "•" in canonical or "・" in canonical:
        parts = [p for p in re.split(r"[·•・]", canonical) if p]
        aliases.add("".join(parts))
        if parts and len(parts[-1]) >= 2:
            aliases.add(parts[-1])

    # 过滤无效别名
    return {a for a in aliases if a and not is_generic_reference(a)}


@dataclass
class NameAuthority:
    """人名权威解析器 — 维护 canonical ↔ alias 映射"""

    canonical_names: set[str] = field(default_factory=set)
    alias_to_canonical: dict[str, str] = field(default_factory=dict)
    ambiguous_aliases: set[str] = field(default_factory=set)

    def resolve(self, value: Any, *, keep_unknown: bool = True) -> Optional[str]:
        """将任意名称解析为规范名

        Args:
            value: 原始名称
            keep_unknown: 未知名称是否原样返回（False 则返回 None）
        """
        text = normalize_name(value)
        if not text or is_generic_reference(text):
            return None
        if text in self.canonical_names:
            return text
        if text in self.ambiguous_aliases:
            return text if keep_unknown else None
        canonical = self.alias_to_canonical.get(text)
        if canonical:
            return canonical
        return text if keep_unknown else None

    def resolve_many(self, values: Any, *, keep_unknown: bool = True) -> list[str]:
        """批量解析，去重并保持顺序"""
        if not values:
            return []
        if not isinstance(values, (list, tuple, set)):
            values = [values]
        result: list[str] = []
        for v in values:
            resolved = self.resolve(v, keep_unknown=keep_unknown)
            if resolved and resolved not in result:
                result.append(resolved)
        return result

    def is_known(self, value: Any) -> bool:
        """判断名称是否为已知角色"""
        text = normalize_name(value)
        if not text:
            return False
        return (
            text in self.canonical_names
            or text in self.alias_to_canonical
            or text in self.ambiguous_aliases
        )

    @classmethod
    def from_characters(cls, characters: Iterable[Character]) -> NameAuthority:
        """从 Character 列表构建权威解析器"""
        authority = cls()
        alias_candidates: dict[str, set[str]] = {}

        for char in characters:
            canonical = normalize_name(char.name)
            if not canonical or is_generic_reference(canonical):
                continue
            authority.canonical_names.add(canonical)
            for alias in extract_character_aliases(char):
                alias_candidates.setdefault(alias, set()).add(canonical)

        # 无歧义的别名 → 直接映射；有歧义的 → 标记
        for alias, canonical_set in alias_candidates.items():
            if alias in authority.canonical_names:
                continue  # 规范名本身不需要映射
            if len(canonical_set) == 1:
                authority.alias_to_canonical[alias] = next(iter(canonical_set))
            else:
                authority.ambiguous_aliases.add(alias)

        return authority

    @classmethod
    def from_novel(cls, db: Session, novel_id: str) -> NameAuthority:
        """从数据库加载小说所有角色并构建解析器"""
        characters = db.query(Character).filter_by(novel_id=novel_id).all()
        return cls.from_characters(characters)
