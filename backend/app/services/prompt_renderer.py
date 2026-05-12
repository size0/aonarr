"""PromptRenderer — 统一解析和渲染提示词模板

解析 [SYSTEM] / [USER] 标记，填充变量，校验占位符。
所有需要从 DB 加载 prompt 的服务应通过此模块渲染。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


@dataclass
class RenderedPrompt:
    """渲染后的提示词对象"""
    system: str
    user: str = ""
    unresolved: list[str] | None = None


def parse_template(raw: str) -> tuple[str, str]:
    """从模板文本中分离 [SYSTEM] 和 [USER] 部分。

    如果模板没有标记，则整体视为 system prompt。
    """
    if "[SYSTEM]" in raw and "[USER]" in raw:
        sys_start = raw.index("[SYSTEM]") + len("[SYSTEM]")
        user_marker = raw.index("[USER]")
        system_part = raw[sys_start:user_marker].strip()
        user_part = raw[user_marker + len("[USER]"):].strip()
        return system_part, user_part
    # 无标记 → 全部视为 system
    return raw.strip(), ""


def render(
    template: str,
    variables: dict,
    *,
    strict: bool = False,
) -> RenderedPrompt:
    """解析模板并填充变量。

    Args:
        template: 原始模板文本（可能含 [SYSTEM]/[USER] 标记）
        variables: 替换字典
        strict: 如果为 True，遇到未解析占位符时记录 warning

    Returns:
        RenderedPrompt 含 system 和 user 字段
    """
    system_tpl, user_tpl = parse_template(template)

    system_rendered = _fill(system_tpl, variables)
    user_rendered = _fill(user_tpl, variables) if user_tpl else ""

    unresolved = []
    if strict:
        for part_name, part_text in [("system", system_rendered), ("user", user_rendered)]:
            remaining = _PLACEHOLDER_RE.findall(part_text)
            if remaining:
                unresolved.extend(remaining)
                logger.warning("Prompt %s 部分存在未解析占位符: %s", part_name, remaining)

    return RenderedPrompt(
        system=system_rendered,
        user=user_rendered,
        unresolved=unresolved or None,
    )


def _fill(template: str, variables: dict) -> str:
    """安全替换 {variable} 占位符，未找到的保留原样"""
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        if key in variables:
            val = variables[key]
            return str(val) if val is not None else ""
        return match.group(0)  # 保留原占位符

    return _PLACEHOLDER_RE.sub(replacer, template)
