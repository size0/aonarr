"""仙侠题材 Agent"""
from typing import List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, BeatTemplate


class XianxiaThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "xianxia"
    @property
    def genre_name(self) -> str: return "仙侠"
    @property
    def description(self) -> str: return "仙侠题材，注重仙道哲理、天人关系、侠义精神"

    def get_system_persona(self) -> str:
        return "你是一位精通仙侠文化的小说大师，深谙道法自然、天人合一的哲学意境。你擅长将修仙求道与人间情义相融，以侠义为骨、仙道为魂，写出既有超凡境界又有人间烟火的仙侠故事。"

    def get_writing_rules(self) -> List[str]:
        return [
            "仙道修行要体现心境变化和道的感悟，不能只是数值升级",
            "侠义精神是核心——为正义出手、为弱者发声，而非纯粹求长生",
            "天劫/心魔等考验要有深层含义，不能只是战力检验",
            "门派文化和师徒传承要有人文深度",
            "爱情线要与修仙大道相关联——情劫、道侣、斩情等",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="仙侠世界观：\n- 修道求真，心境与境界并重\n- 天道有序，因果循环\n- 门派体系严谨，长幼有序\n- 仙凡有别，渡劫飞升为终极目标",
            atmosphere="整体基调：飘逸洒脱+侠骨柔情。打斗需仙气飘飘的美感；修行需超然出尘的意境；情感需刻骨铭心的深度。",
            taboos="- 不要将仙侠写成纯粹的打怪升级\n- 不要忽视角色的心境成长\n- 修仙者不应过于世俗化",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["悟道", "天劫", "飞升", "心魔", "证道"], priority=85, beats=[
                ("心境准备：回顾修行之路、感悟天道", 600, "emotion"),
                ("天劫/心魔降临：内外交困、考验本心", 1000, "action"),
                ("破境感悟：道的领悟、境界蜕变", 800, "cultivation"),
                ("新境界：超然感受、世界观变化", 400, "sensory"),
            ]),
        ]
