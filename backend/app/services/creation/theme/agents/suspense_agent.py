"""悬疑题材 Agent"""
from typing import List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, BeatTemplate


class SuspenseThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "suspense"
    @property
    def genre_name(self) -> str: return "悬疑"
    @property
    def description(self) -> str: return "推理/悬疑/惊悚题材，涵盖案件调查、逻辑推理、真相反转"

    def get_system_persona(self) -> str:
        return "你是一位精通悬疑叙事结构的推理小说大师，深谙线索布置、红鲱鱼设计、多层反转的写作技巧。你擅长以精密逻辑推理为骨架，以紧张悬疑氛围为血肉，写出让读者欲罢不能的悬疑故事。"

    def get_writing_rules(self) -> List[str]:
        return [
            "所有关键线索必须在揭露前合理出现过（公平推理原则）",
            "红鲱鱼必须自然融入剧情，不能像故意放的烟雾弹",
            "推理过程要有完整逻辑链：观察→假设→验证→排除→结论",
            "悬疑氛围通过场景细节和人物反应营造，不能只靠旁白渲染",
            "每章结尾留一个钩子（新线索/新疑问/反转）",
            "凶手/幕后黑手的行为要有充分心理动因",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="悬疑推理规则：\n- 公平推理：关键线索必须提前出现\n- 逻辑自洽：推理链条无跳跃\n- 信息管控：每章投放适量新信息\n- 角色动机：所有行为有合理心理动因\n- 时间线清晰经得起推敲",
            atmosphere="整体基调：紧张压抑+智力快感。调查需推理氛围；对峙需心理博弈紧迫感；日常也要暗藏不安。",
            taboos="- 不要用超自然能力获得线索\n- 不要最后一章才抛关键证据\n- 不要凶手动机只是「因为他疯了」\n- 不要过度依赖巧合推动剧情",
            tropes_to_use="- 红鲱鱼：精心设计的误导线索\n- 不可靠叙述：角色选择性隐瞒\n- 多层真相：揭开一层还有更深秘密",
            tropes_to_avoid="- 主角莫名猜到真相\n- 犯人独白交代所有\n- 用惊吓代替智力挑战",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["案件", "案发", "现场", "尸体", "报案"], priority=90, beats=[
                ("案发现场：细节描写、初步线索", 600, "sensory"),
                ("初步调查：证据收集、目击者询问", 900, "dialogue"),
                ("疑点浮现：矛盾证词、不合理细节", 700, "suspense"),
                ("章末钩子：改变调查方向的新发现", 400, "hook"),
            ]),
            BeatTemplate(keywords=["推理", "真相", "揭露", "破案"], priority=95, beats=[
                ("线索梳理：已知证据整合、排除假设", 600, "dialogue"),
                ("关键推理：逻辑推演、真相逼近", 1000, "action"),
                ("真相揭露：震撼反转、犯人动机", 800, "emotion"),
                ("余波：案件影响、人物命运变化", 400, "emotion"),
            ]),
        ]
