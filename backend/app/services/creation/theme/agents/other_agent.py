"""通用/其他题材 Agent — 作为兜底"""
from typing import List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives


class OtherThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "other"
    @property
    def genre_name(self) -> str: return "其他"
    @property
    def description(self) -> str: return "通用题材兜底，提供基础写作规则"

    def get_system_persona(self) -> str:
        return "你是一位经验丰富的网络小说作家，擅长多种题材创作，注重叙事节奏、人物塑造和情节张力。"

    def get_writing_rules(self) -> List[str]:
        return [
            "叙事节奏要张弛有度——不能一直高潮也不能一直平淡",
            "人物行为要有动机和逻辑——不能为了剧情需要而降智",
            "对话要符合角色身份和性格",
            "伏笔要前后呼应，不要挖坑不填",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            atmosphere="注重叙事节奏的张弛有度，人物的真实感，情节的逻辑自洽。",
        )
