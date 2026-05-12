"""历史题材 Agent"""
from typing import List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, BeatTemplate


class HistoryThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "history"
    @property
    def genre_name(self) -> str: return "历史"
    @property
    def description(self) -> str: return "历史/架空历史/宫斗/权谋题材"

    def get_system_persona(self) -> str:
        return "你是一位精通中国历史和宫廷文化的小说大师，擅长以历史为骨架、以人物为血肉，写出波澜壮阔的历史故事。你深谙权谋博弈、宫廷斗争、家国情怀的写作技巧。"

    def get_writing_rules(self) -> List[str]:
        return [
            "历史背景需基本准确——朝代制度、官职称谓、礼仪习俗要符合时代",
            "权谋博弈要有层次——不能只靠暗杀解决问题，要有政治智慧",
            "人物对话要有古风韵味但不能过于生僻",
            "战争场景要有战略层面的描写，不能只写个人武力",
            "架空历史也要有内在逻辑——不能随意改变物理法则",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="历史世界观：\n- 等级制度和礼法是行为框架\n- 权力斗争遵循政治逻辑\n- 战争有策略、后勤、地理因素\n- 社会阶层决定人物行为空间",
            atmosphere="整体基调：厚重质感+权谋张力。朝堂需威严肃穆；战场需壮烈悲壮；日常需古韵雅致。",
            taboos="- 不要出现时代错误的概念和用词\n- 不要让权谋斗争过于儿戏\n- 不要忽视历史人物的复杂性\n- 不要用现代价值观审判古人",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["朝堂", "上朝", "奏折", "政变", "权谋"], priority=85, beats=[
                ("朝堂氛围：权力格局、各方势力暗流", 500, "sensory"),
                ("权谋交锋：口舌之争、政治算计", 1000, "dialogue"),
                ("局势变化：权力天平倾斜、格局重塑", 700, "action"),
                ("人心所向：各方反应、新的布局", 500, "emotion"),
            ]),
        ]
