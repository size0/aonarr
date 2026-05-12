"""武侠题材 Agent"""
from typing import List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, BeatTemplate


class WuxiaThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "wuxia"
    @property
    def genre_name(self) -> str: return "武侠"
    @property
    def description(self) -> str: return "传统武侠题材，注重江湖义气、武功招式、恩怨情仇"

    def get_system_persona(self) -> str:
        return "你是一位深谙江湖之道的武侠小说大师，传承金庸古龙温瑞安的写作精髓。你擅长以侠义为魂、以武功为骨、以江湖为舞台，写出刀光剑影、快意恩仇的武侠故事。"

    def get_writing_rules(self) -> List[str]:
        return [
            "武功招式需有具体描写——招式名、运气路线、攻防变化，不能只写'剑气纵横'",
            "江湖规矩（拜帖、论资排辈、比武规则）要符合武侠世界逻辑",
            "侠义精神是核心——侠之大者为国为民，侠之小者为友为义",
            "内力/轻功/暗器等武侠元素要保持体系一致性",
            "恩怨情仇要有前因后果，不能无理由的仇杀",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="武侠江湖：\n- 武功分内功外功，内力为根基\n- 门派有正邪之分但不绝对\n- 江湖规矩重于律法\n- 武林盟主/大侠有号召力",
            atmosphere="整体基调：刀光剑影+快意恩仇。打斗要有招式美学；江湖要有烟火气息；情感要有侠骨柔情。",
            taboos="- 不要出现现代用语和概念\n- 不要让武功体系过于超自然（区别于仙侠）\n- 不要忽视武侠的「侠」字",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["比武", "擂台", "论剑", "华山论剑", "武林大会"], priority=85, beats=[
                ("赛前：英雄齐聚、规矩宣读、暗流涌动", 500, "sensory"),
                ("交锋：招式过招、内力对抗、攻守转换", 1000, "action"),
                ("高潮：绝学出手、意外变故、胜负揭晓", 800, "action"),
                ("余波：江湖格局变动、新恩怨结下", 500, "emotion"),
            ]),
        ]
