"""西方奇幻题材 Agent"""
from typing import List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, BeatTemplate


class FantasyThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "fantasy"
    @property
    def genre_name(self) -> str: return "奇幻"
    @property
    def description(self) -> str: return "西方奇幻/DND/魔法/中世纪题材"

    def get_system_persona(self) -> str:
        return "你是一位精通西方奇幻世界观的小说大师，深谙魔法体系、种族文化、中世纪社会结构。你擅长构建宏大而细致的奇幻世界，写出史诗级别的奇幻冒险故事。"

    def get_writing_rules(self) -> List[str]:
        return [
            "魔法体系要有明确的规则和代价——不能无限制使用魔法",
            "不同种族（精灵/矮人/兽人等）要有独特的文化和行为逻辑",
            "中世纪社会结构（封建/骑士/教会）要有基本逻辑",
            "史诗叙事节奏——英雄之旅的结构但要有新意",
            "黑暗势力/反派不能纯粹邪恶，要有动机和逻辑",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="西方奇幻世界观：\n- 魔法有规则和代价\n- 种族有独特文化体系\n- 社会结构基于封建/教会/公会\n- 神话体系影响世界运作",
            atmosphere="整体基调：史诗宏大+冒险刺激。战斗需磅礴壮观；探索需神秘奇幻；日常需中世纪风情。",
            taboos="- 魔法不能万能\n- 种族不能只有刻板印象\n- 不要忽视世界的政治经济\n- 反派不能纯粹邪恶",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["冒险", "探索", "地下城", "迷宫", "龙穴"], priority=80, beats=[
                ("冒险准备：队伍集结、装备补给", 400, "sensory"),
                ("探索过程：陷阱、谜题、遭遇战", 1000, "action"),
                ("核心挑战：BOSS/守护者/终极谜题", 900, "action"),
                ("收获归来：宝物/知识/成长", 500, "emotion"),
            ]),
        ]
