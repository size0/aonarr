"""游戏题材 Agent"""
from typing import Dict, List
from app.services.creation.theme.theme_agent import ThemeAgent, ThemeDirectives, BeatTemplate


class GameThemeAgent(ThemeAgent):
    @property
    def genre_key(self) -> str: return "game"
    @property
    def genre_name(self) -> str: return "游戏"
    @property
    def description(self) -> str: return "游戏/电竞/系统流/无限流题材"

    def get_system_persona(self) -> str:
        return "你是一位精通游戏机制和系统设计的网络小说大师，擅长将游戏元素融入精彩叙事。你熟悉RPG/FPS/MOBA等各类游戏机制，能写出让玩家和非玩家都沉浸的游戏类故事。"

    def get_writing_rules(self) -> List[str]:
        return [
            "系统/面板描写要简洁有力，不能大段罗列数值",
            "游戏机制要有内在平衡性——不能让主角无限刷BUG",
            "技能/装备的获取和升级要有成就感和节奏感",
            "PVP/团战要有策略性描写，不能只堆数值碾压",
            "非游戏场景（现实/社交）也要有存在感，不能全是刷怪",
        ]

    def get_context_directives(self, novel_id: str, chapter_number: int, outline: str) -> ThemeDirectives:
        return ThemeDirectives(
            world_rules="游戏世界观：\n- 系统规则是最高法则\n- 等级/装备/技能有明确体系\n- 玩家社交和公会政治是重要维度\n- 游戏经济体系需基本自洽",
            atmosphere="整体基调：热血竞技+策略博弈。副本需紧张刺激；PVP需对抗快感；日常需轻松社交。",
            taboos="- 系统面板不要大段数值罗列\n- 不要无限BUG利用\n- 不要忽视非战斗内容\n- NPC不能只是工具",
        )

    def get_beat_templates(self) -> List[BeatTemplate]:
        return [
            BeatTemplate(keywords=["副本", "BOSS", "团战", "raid", "通关"], priority=85, beats=[
                ("副本入口：队伍配置、策略制定", 400, "sensory"),
                ("战斗过程：机制应对、配合协作", 1000, "action"),
                ("BOSS战：核心机制、危机时刻", 900, "action"),
                ("通关奖励：装备掉落、成就解锁", 500, "emotion"),
            ]),
        ]

    def get_custom_focus_instructions(self) -> Dict[str, str]:
        return {
            "system_panel": "展示系统面板要简洁——只列关键变化数值，配合角色的惊喜/沮丧反应，不要纯数据罗列。",
        }
