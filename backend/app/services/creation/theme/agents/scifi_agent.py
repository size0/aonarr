"""科幻题材 Agent"""
from typing import List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, BeatTemplate


class ScifiThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "scifi"
    @property
    def genre_name(self) -> str: return "科幻"
    @property
    def description(self) -> str: return "科幻题材，涵盖太空歌剧、赛博朋克、末日废土、硬科幻等"

    def get_system_persona(self) -> str:
        return "你是一位兼具科学素养和文学功底的科幻小说大师，擅长将前沿科技概念融入引人入胜的叙事中。你精通硬科幻的严谨逻辑和软科幻的人文思辨，能写出既有技术深度又有情感温度的科幻故事。"

    def get_writing_rules(self) -> List[str]:
        return [
            "科技设定需有内在逻辑自洽性——不能今天FTL明天说光速不可超越",
            "科技元素要融入叙事而非生硬灌输，通过角色使用来展现技术",
            "外星文明/AI 的描写要有异质感，不能只是「人类换了个皮肤」",
            "末日/灾难场景要有真实感和紧迫感，注重细节描写",
            "哲学思辨（人类本质、AI伦理、文明冲突）融入情节，不要说教",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="科幻世界观：\n- 科技体系需内在自洽\n- 社会结构受科技水平影响\n- 物理法则在设定框架内遵守\n- 外星/AI文明有独立逻辑体系",
            atmosphere="整体基调：科技感+哲思深度。太空场景需宏大壮观；赛博场景需颓废华丽；末日场景需荒凉压迫。",
            taboos="- 不要科技设定前后矛盾\n- 不要用科技万能论解决所有问题\n- 外星人不能太人类化\n- 不要忽视科技的社会影响",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["太空", "星际", "飞船", "跃迁", "虫洞"], priority=80, beats=[
                ("宇宙场景：星空描写、飞船内部、技术展示", 600, "sensory"),
                ("太空危机：失重/辐射/碰撞等太空特有困境", 1000, "action"),
                ("科技解决：运用科技手段应对危机", 700, "action"),
                ("哲思余波：面对宇宙的渺小感/使命感", 400, "emotion"),
            ]),
        ]
