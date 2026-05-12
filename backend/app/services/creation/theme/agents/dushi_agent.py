"""都市题材 Agent"""
from typing import List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, BeatTemplate


class DushiThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "dushi"
    @property
    def genre_name(self) -> str: return "都市"
    @property
    def description(self) -> str: return "现代都市/职场/商战题材，涵盖逆袭打脸、商业博弈、都市情感"

    def get_system_persona(self) -> str:
        return "你是一位深谙现代都市生活与商业逻辑的网络小说大师，熟悉职场竞争、商业运作、社交规则与城市文化。你擅长以真实可信的社会背景为舞台，写出既有爽感又接地气的都市故事。"

    def get_writing_rules(self) -> List[str]:
        return [
            "商业谈判/博弈需有具体策略和逻辑推演，不能只靠主角气场碾压",
            "对话要符合现代都市人说话方式，不要过于书面化或古风化",
            "涉及专业领域时关键术语和逻辑必须基本准确",
            "人际关系发展要有铺垫和过程",
            "打脸/逆袭要有前期蓄力（被轻视、被打压），反转才有爽感",
            "财富地位获取需有合理路径，不能天降横财",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="现代都市社会：\n- 法律/商业/职场规则是行为约束底线\n- 人脉关系和社会资源是核心竞争力\n- 经济逻辑和商业规则必须自洽\n- 角色行为符合其社会阶层和教育背景",
            atmosphere="整体基调：现实质感+逆袭爽感。商业场景需紧张博弈；社交需人情世故；日常可轻松但不悬浮。",
            taboos="- 不要让商业逻辑过于儿戏\n- 不要让所有美女都倒向主角\n- 不要让反派只会降智\n- 不要让主角开挂解决所有问题",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["谈判", "商战", "收购", "投标", "签约"], priority=85, beats=[
                ("谈判准备：信息收集、策略制定", 500, "sensory"),
                ("谈判交锋：条件博弈、心理对抗", 1000, "dialogue"),
                ("关键反转：底牌亮出、局势逆转", 800, "action"),
                ("结果影响：商业格局变动", 500, "emotion"),
            ]),
            BeatTemplate(keywords=["社交", "宴会", "聚会", "饭局"], priority=70, beats=[
                ("入场：身份暴露/隐藏、人物登场", 500, "sensory"),
                ("暗流涌动：试探、拉拢、排挤", 800, "dialogue"),
                ("身份反转/打脸：主角真实身份/实力展露", 900, "action"),
                ("事后影响：关系重组", 400, "emotion"),
            ]),
        ]
