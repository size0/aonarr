"""ThemeAgent 抽象接口 — 专项题材写作能力的统一契约

每个题材 Agent 实现此接口，向写作管线注入题材专项知识：
1. 人设/角色设定指导（system persona）
2. 题材专项写作规则（writing rules）
3. 世界观/氛围约束上下文（context directives）
4. 题材专项节拍模板（beat templates）
5. 缓冲章模板（buffer chapter template）
6. 题材专项审计规则（audit criteria）
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BeatTemplate:
    """题材专项节拍模板"""
    keywords: List[str]
    beats: List[tuple]  # [(description, target_words, focus), ...]
    priority: int = 50


@dataclass
class ThemeDirectives:
    """题材上下文指令 — 注入 ContextBudgetAllocator T0 槽位"""
    world_rules: str = ""
    atmosphere: str = ""
    taboos: str = ""
    tropes_to_use: str = ""
    tropes_to_avoid: str = ""

    def to_context_text(self) -> str:
        parts = []
        if self.world_rules:
            parts.append(f"【世界观规则】\n{self.world_rules}")
        if self.atmosphere:
            parts.append(f"【氛围基调】\n{self.atmosphere}")
        if self.taboos:
            parts.append(f"【题材禁忌】\n{self.taboos}")
        if self.tropes_to_use:
            parts.append(f"【推荐叙事手法】\n{self.tropes_to_use}")
        if self.tropes_to_avoid:
            parts.append(f"【应避免的套路】\n{self.tropes_to_avoid}")
        return "\n\n".join(parts) if parts else ""


@dataclass
class ThemeAuditCriteria:
    """题材专项审计标准"""
    required_elements: List[str] = field(default_factory=list)
    quality_checks: List[str] = field(default_factory=list)
    tension_guidance: str = ""


class ThemeAgent(ABC):
    """专项题材 Agent 抽象接口"""

    @property
    @abstractmethod
    def genre_key(self) -> str:
        ...

    @property
    @abstractmethod
    def genre_name(self) -> str:
        ...

    @property
    def description(self) -> str:
        return ""

    def get_system_persona(self) -> str:
        return ""

    def get_writing_rules(self) -> List[str]:
        return []

    def get_context_directives(
        self, novel_id: str, chapter_number: int, outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives()

    def get_beat_templates(self) -> List[BeatTemplate]:
        return []

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {}

    def get_buffer_chapter_template(self, outline: str) -> str:
        return ""

    def get_audit_criteria(self, chapter_number: int, outline: str) -> ThemeAuditCriteria:
        return ThemeAuditCriteria()

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        return None

    def __repr__(self) -> str:
        return f"<ThemeAgent:{self.genre_key}({self.genre_name})>"
