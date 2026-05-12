"""言情题材 Agent"""
from typing import List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, BeatTemplate


class RomanceThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "romance"
    @property
    def genre_name(self) -> str: return "言情"
    @property
    def description(self) -> str: return "现代/古代言情题材，涵盖甜宠、虐恋、双强、先婚后爱等核心元素"

    def get_system_persona(self) -> str:
        return "你是一位精通情感描写的言情小说大师，对人物心理、感情发展节奏和CP互动有极致把控力。你擅长以细腻的心理描写为灵魂，以张弛有度的情感发展为脉络，写出让读者心动、揪心又感动的言情故事。"

    def get_writing_rules(self) -> List[str]:
        return [
            "感情发展必须循序渐进，不能见面就无理由心动",
            "心理描写是言情灵魂——角色对感情的内心独白要细腻真实",
            "CP互动要有化学反应——对话/动作中的微妙暧昧和情感张力",
            "误会/波折不能过于刻意，需有合理心理基础",
            "配角不能只是工具人——闺蜜/情敌/家人都应有自己的立场",
            "甜和虐要有节奏——连续甜会腻，连续虐会累，交替进行",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="感情线为核心驱动：\n- 感情发展阶段：相识→暧昧→确认→波折→圆满/遗憾\n- 每阶段需具体事件推动\n- 角色感情观与性格/经历一致\n- 外部事件服务于感情线",
            atmosphere="整体基调：心动暧昧+情感张力。甜蜜需小鹿乱撞感；冲突需揪心不狗血；日常需温馨有趣的CP互动。",
            taboos="- 不要感情转变无铺垫\n- 不要用强制性情节推动感情\n- 不要所有配角都是恋爱脑\n- 不要过度狗血（车祸失忆三角恋全上）",
            tropes_to_use="- 误会推拉：因误解产生距离，解开后更亲近\n- 双向暗恋：两人都喜欢但不敢表白\n- 共患难：危机中的真情流露",
            tropes_to_avoid="- 霸道总裁模板化\n- 强行制造三角恋\n- 所有冲突靠误解",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["告白", "表白", "确认关系", "在一起"], priority=90, beats=[
                ("告白前奏：犹豫、心理活动、氛围铺垫", 600, "emotion"),
                ("告白时刻：对话、心跳、细微动作描写", 800, "dialogue"),
                ("回应与确认：惊喜、感动、拥抱/亲吻", 600, "sensory"),
                ("甜蜜余韵：确认关系后的小甜蜜", 400, "emotion"),
            ]),
            BeatTemplate(keywords=["误会", "争吵", "分手", "冷战"], priority=85, beats=[
                ("矛盾起因：误解/外部干扰/价值观冲突", 500, "dialogue"),
                ("冲突爆发：争吵、赌气、冷暴力", 800, "emotion"),
                ("痛苦独处：分开后的思念和反省", 700, "emotion"),
                ("和解伏笔：一个小细节暗示感情未断", 400, "suspense"),
            ]),
        ]
