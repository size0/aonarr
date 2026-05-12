"""玄幻题材 Agent — 东方玄幻/修仙专项"""
from typing import Dict, List, Optional
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, ThemeAuditCriteria, BeatTemplate


class XuanhuanThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "xuanhuan"
    @property
    def genre_name(self) -> str: return "玄幻"
    @property
    def description(self) -> str: return "东方玄幻/修仙题材，涵盖修炼体系、宗门争斗、以弱胜强等核心元素"

    def get_system_persona(self) -> str:
        return (
            "你是一位精通东方玄幻体系的网络小说大师，深谙修仙功法、境界体系与宗门争斗的设定逻辑。"
            "你擅长以严密的力量体系为骨架，以快意恩仇的情节为血肉，写出既有爽感又不失深度的玄幻故事。"
            "你熟练掌握「以弱胜强」「扮猪吃老虎」「打脸」等经典套路的高级写法，避免廉价降智和主角光环。"
        )

    def get_writing_rules(self) -> List[str]:
        return [
            "战斗场景必须有具体的功法/招式/法宝描写，不能只写「一拳打出」",
            "修炼突破时必须描写灵气变化、经脉打通或境界感悟，避免一句话带过",
            "境界压制必须体现在具体的力量对比上（速度、破坏力、感知范围等）",
            "以弱胜强必须有合理的战术/底牌/外部因素支撑，不能无理由翻盘",
            "宗门/势力的等级体系需保持一致，不要前后矛盾",
            "灵药/法宝/功法的获取不能过于随意，需有合理铺垫",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="本作世界观基于东方玄幻/修仙体系：\n- 修炼境界须层层递进，不可跳级\n- 灵气/仙元力是一切功法的基础能量\n- 法宝/灵药/功法有明确等级划分\n- 宗门/家族/势力有清晰实力梯度\n- 天地规则（天劫、大道、因果）是最高层约束",
            atmosphere="整体基调：快意恩仇+热血成长。战斗需画面感和力量美学；修炼需沉浸意境感；日常可轻松但不跳脱。",
            taboos="- 不要出现现代科技元素\n- 不要让配角无理由降智衬托主角\n- 不要无铺垫突然出现逆天机缘\n- 不要让境界差距过大的战斗以弱者轻松获胜",
            tropes_to_use="- 扮猪吃老虎：低调→被轻视→展露实力→震惊全场\n- 步步高升：持续正反馈\n- 宗门大比/拍卖会/秘境探险经典场景",
            tropes_to_avoid="- 无脑碾压\n- 金手指滥用\n- 境界注水\n- 后宫收集器",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["修炼", "突破", "闭关", "悟道", "晋升", "渡劫"], priority=80, beats=[
                ("修炼准备：入定、调息、灵气汇聚", 500, "sensory"),
                ("修炼过程：功法运转、经脉打通、灵气暴动", 1000, "cultivation"),
                ("突破感悟：境界壁垒突破、天地异象", 800, "power_reveal"),
                ("突破余波：实力暴增感知变化、旁观者反应", 500, "emotion"),
            ]),
            BeatTemplate(keywords=["以弱胜强", "打脸", "嘲讽", "挑衅", "蝼蚁"], priority=90, beats=[
                ("铺垫：对手嚣张轻视，旁观者不看好", 500, "dialogue"),
                ("交锋：主角被压制或假装被压制", 700, "action"),
                ("反转：底牌揭露、隐藏实力爆发", 900, "power_reveal"),
                ("碾压收场：震惊全场、势力格局变动", 600, "emotion"),
            ]),
            BeatTemplate(keywords=["大比", "比武", "擂台", "排名赛"], priority=75, beats=[
                ("赛前：规则宣布、对手出场、氛围渲染", 500, "sensory"),
                ("核心对战：功法对抗、险象环生", 1000, "action"),
                ("高潮反转：底牌对决、胜负揭晓", 700, "power_reveal"),
                ("赛后余波：名次确定、新挑战预告", 400, "emotion"),
            ]),
            BeatTemplate(keywords=["秘境", "遗迹", "宝藏", "禁地", "传承"], priority=70, beats=[
                ("秘境入口：环境描写、危险预兆", 500, "sensory"),
                ("探索危机：陷阱/守护兽/阵法", 1000, "action"),
                ("核心发现：传承/宝物出现、争夺考验", 800, "power_reveal"),
                ("收获离开：获得机缘、脱险、伏笔埋设", 500, "emotion"),
            ]),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "cultivation": "重点描写修炼过程：灵气经脉流动、功法口诀默念、天地灵气汇聚、丹田识海变化。要有沉浸感和意境美。",
            "power_reveal": "重点描写实力揭露：压制性气息释放、旁观者从轻视到震惊的表情变化、力量等级差距的具体呈现。",
        }

    def get_buffer_chapter_template(self, outline: str) -> str:
        return f"【缓冲章：战后修整悟道】{outline}。主角战后疗伤修炼，感悟战斗得失，整理收获。与同伴交流切磋，暗埋下一个冲突种子。"

    def get_opening_beats(self, chapter_number: int) -> Optional[List[tuple]]:
        if chapter_number == 1:
            return [
                ("开篇：主角身份/处境揭示，用强冲击事件抓住读者", 500, "hook"),
                ("修炼体系初展：通过具体场景展现力量体系", 1000, "character_intro"),
                ("核心冲突引入：第一个危机/压迫", 800, "action"),
                ("金手指伏笔：暗示主角的特殊之处", 700, "suspense"),
            ]
        return None

    def get_audit_criteria(self, chapter_number: int, outline: str) -> ThemeAuditCriteria:
        required, checks = [], []
        if any(kw in outline for kw in ["战斗", "打斗", "对决"]):
            required.append("战斗场景需有具体功法/招式描写")
        if any(kw in outline for kw in ["突破", "修炼", "闭关"]):
            required.append("修炼/突破需有过程描写")
        return ThemeAuditCriteria(required_elements=required, quality_checks=checks,
            tension_guidance="玄幻张力：大型战斗8-10/大比对决6-8/修炼突破5-7/日常3-5")
