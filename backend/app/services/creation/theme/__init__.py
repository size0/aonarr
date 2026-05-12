"""题材 Agent 体系 — 为不同题材提供专项写作策略

移植自 PlotPilot，适配 NovelForgeX 体系。

核心组件：
- ThemeAgent: 抽象接口
- ThemeAgentRegistry: 注册中心
- agents/: 11 个题材的具体实现
"""

from app.services.creation.theme.theme_agent import (
    ThemeAgent,
    BeatTemplate,
    ThemeDirectives,
    ThemeAuditCriteria,
)
from app.services.creation.theme.theme_registry import ThemeAgentRegistry

__all__ = [
    "ThemeAgent",
    "BeatTemplate",
    "ThemeDirectives",
    "ThemeAuditCriteria",
    "ThemeAgentRegistry",
]
