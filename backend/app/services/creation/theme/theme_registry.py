"""ThemeAgentRegistry — 题材 Agent 注册中心 + 自动发现"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.services.creation.theme.theme_agent import ThemeAgent

logger = logging.getLogger(__name__)

# 全局单例
_global_registry: Optional["ThemeAgentRegistry"] = None


def get_theme_registry() -> "ThemeAgentRegistry":
    """获取全局题材注册中心（单例，首次调用自动发现）"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ThemeAgentRegistry()
        _global_registry.auto_discover()
    return _global_registry


class ThemeAgentRegistry:
    def __init__(self):
        self._agents: Dict[str, ThemeAgent] = {}

    def register(self, agent: ThemeAgent) -> None:
        self._agents[agent.genre_key] = agent
        logger.info("注册题材 Agent: %s", agent)

    def get(self, genre_key: str) -> Optional[ThemeAgent]:
        return self._agents.get(genre_key)

    def get_or_default(self, genre_key: str) -> Optional[ThemeAgent]:
        if not genre_key:
            return None
        return self._agents.get(genre_key)

    def list_genres(self) -> List[Dict[str, str]]:
        return [
            {"key": a.genre_key, "name": a.genre_name, "description": a.description}
            for a in self._agents.values()
        ]

    @property
    def registered_keys(self) -> List[str]:
        return list(self._agents.keys())

    def auto_discover(self) -> None:
        """自动注册所有内置题材 Agent"""
        from app.services.creation.theme.agents import ALL_AGENTS
        for agent_cls in ALL_AGENTS:
            try:
                self.register(agent_cls())
            except Exception as e:
                logger.warning("注册题材 Agent 失败: %s — %s", agent_cls, e)
        logger.info("题材 Agent 自动发现完成: %d 个", len(self._agents))
