"""职场破局编剧 Agent — 事件发动机

核心职责：为长篇职场规则爽文持续生成不重复的事件单元。
每次调用输入故事当前状态，输出结构化12字段事件方案。

定位：不是"写故事Agent"，而是"事件发动机Agent"。
每次造一个新麻烦，再设计一个漂亮反杀。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 输入结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class EventEngineInput:
    """调用事件发动机时的输入"""
    protagonist_name: str                # 主角名字
    protagonist_role: str                # 当前职位
    stage: str                           # 当前阶段: 生存期 / 破局期 / 上位期
    existing_antagonists: List[str]      # 已有反派列表
    last_event_result: str               # 上一事件结果摘要
    conflict_direction: str              # 本次想要的冲突方向
    forbidden_elements: List[str]        # 禁止重复的元素
    intensity: str = "高"                # 爽点强度: 低 / 中 / 高
    chapter_number: int = 0              # 当前章节号（可选）
    novel_id: str = ""                   # 小说ID（可选，用于查历史）

    def to_prompt_block(self) -> str:
        """转为 LLM 可读的输入块"""
        return (
            f"主角：{self.protagonist_name}，{self.protagonist_role}\n"
            f"当前阶段：{self.stage}\n"
            f"已有反派：{'、'.join(self.existing_antagonists) if self.existing_antagonists else '暂无'}\n"
            f"上一事件结果：{self.last_event_result or '无（第一章）'}\n"
            f"本次冲突方向：{self.conflict_direction}\n"
            f"禁止重复：{'、'.join(self.forbidden_elements) if self.forbidden_elements else '无'}\n"
            f"爽点强度：{self.intensity}"
        )


# ═══════════════════════════════════════════════════════════════
# 输出结构 — 12字段
# ═══════════════════════════════════════════════════════════════

@dataclass
class EventBlueprint:
    """事件发动机的输出 — 一个完整事件方案"""
    event_title: str = ""                # 1. 事件标题
    conflict_cause: str = ""             # 2. 冲突起因
    antagonist_goal: str = ""            # 3. 反派目的
    antagonist_method: str = ""          # 4. 反派手段
    protagonist_surface: str = ""        # 5. 主角表面反应
    protagonist_hidden: str = ""         # 6. 主角暗中布局
    key_evidence: str = ""               # 7. 关键证据
    reversal_trigger: str = ""           # 8. 反转触发点
    antagonist_consequence: str = ""     # 9. 反派反噬结果
    protagonist_gain: str = ""           # 10. 主角获得什么
    chapter_outline: str = ""            # 11. 可扩写章节大纲
    killer_line: str = ""                # 12. 爽点台词

    def to_dict(self) -> dict:
        return {
            "event_title": self.event_title,
            "conflict_cause": self.conflict_cause,
            "antagonist_goal": self.antagonist_goal,
            "antagonist_method": self.antagonist_method,
            "protagonist_surface": self.protagonist_surface,
            "protagonist_hidden": self.protagonist_hidden,
            "key_evidence": self.key_evidence,
            "reversal_trigger": self.reversal_trigger,
            "antagonist_consequence": self.antagonist_consequence,
            "protagonist_gain": self.protagonist_gain,
            "chapter_outline": self.chapter_outline,
            "killer_line": self.killer_line,
        }

    def to_writing_context(self) -> str:
        """转为写作上下文注入 ChapterWriter"""
        return (
            f"【本章事件蓝图】\n"
            f"标题: {self.event_title}\n"
            f"冲突起因: {self.conflict_cause}\n"
            f"反派目的: {self.antagonist_goal}\n"
            f"反派手段: {self.antagonist_method}\n"
            f"主角表面反应: {self.protagonist_surface}\n"
            f"主角暗中布局: {self.protagonist_hidden}\n"
            f"关键证据: {self.key_evidence}\n"
            f"反转触发点: {self.reversal_trigger}\n"
            f"反派反噬: {self.antagonist_consequence}\n"
            f"主角收获: {self.protagonist_gain}\n"
            f"章节大纲: {self.chapter_outline}\n"
            f"爽点台词: {self.killer_line}"
        )


# ═══════════════════════════════════════════════════════════════
# 内置事件类型库（灵感池，不是硬约束）
# ═══════════════════════════════════════════════════════════════

EVENT_TYPES = [
    "抢客户", "抢功劳", "甩锅项目", "篡改方案", "恶意压价",
    "会议羞辱", "财务卡报销", "供应商设局", "跨部门踢皮球", "空降关系户",
    "年终考核打压", "晋升名额被截胡", "客户投诉反转", "竞标方案泄露",
    "审计进场", "大老板暗访", "团队内鬼", "离职挽留", "调岗边缘化",
    "烂部门翻盘", "加班陷阱", "培训借口架空", "合同条款陷阱",
    "绩效数据造假", "招标围标", "项目验收扯皮", "保密协议威胁",
    "客户回扣举报", "猎头挖角试探", "股权纠纷", "薪酬倒挂冲突",
]


# ═══════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = '''你是"职场破局编剧 Agent"。

你的任务是为一部长篇职场规则爽文设计连续事件。故事核心是：主角在职场中被针对、被抢功、被甩锅、被污蔑，但主角不主动作恶，而是通过证据、规则、流程、合同、会议纪要、客户反馈和人性判断完成反击。

你每次必须生成一个全新的职场事件，不能重复用户指定的禁用元素。事件必须现实、紧张、有反转，并且能推动主角职位、人脉、声望或资源提升。

输出必须严格按 JSON 格式，包含以下12个字段：
{
  "event_title": "事件标题（像短剧集名，有悬念）",
  "conflict_cause": "冲突起因（为什么冲突发生）",
  "antagonist_goal": "反派目的（他想得到什么）",
  "antagonist_method": "反派手段（具体怎么做的，要有现实逻辑）",
  "protagonist_surface": "主角表面反应（让反派以为得逞的假象）",
  "protagonist_hidden": "主角暗中布局（实际在做什么准备）",
  "key_evidence": "关键证据（什么东西成为翻盘关键）",
  "reversal_trigger": "反转触发点（在什么场合、什么时机亮牌）",
  "antagonist_consequence": "反派反噬结果（自作自受的具体后果）",
  "protagonist_gain": "主角获得什么（职位/人脉/资源/声望的具体提升）",
  "chapter_outline": "可扩写章节大纲（3-5个节拍，每个一句话）",
  "killer_line": "爽点台词（主角或旁观者的一句话，有冲击力）"
}

铁律：
1. 主角不能主动造假、诬陷、违法。只能用证据、流程、制度、合同、会议纪要、邮件、客户反馈反击。
2. 反派不能蠢，要有现实动机：嫉妒、抢功、甩锅、利益、站队、保职位。
3. 每个事件必须推进主角地位，不能只是打脸。
4. 每个事件不能重复上一个事件的手段。
5. 爽点必须来自"对方自己越界，自己承担后果"。
6. 关键证据必须具体可信（邮件截图/签字文件/系统日志/录音/合同条款），不能模糊。
7. 反转触发点必须在有旁观者的公开场合。

可参考的事件类型（不限于此）：
''' + '、'.join(EVENT_TYPES) + '''

三个阶段的侧重：
- 生存期：直属领导、小同事、小项目、自保为主
- 破局期：大客户、跨部门、供应商、公司派系
- 上位期：团队管理、集团审计、高层博弈、最终夺权

只输出 JSON，不要输出任何其他内容。'''


# ═══════════════════════════════════════════════════════════════
# 事件发动机核心逻辑
# ═══════════════════════════════════════════════════════════════

class ZhichangEventEngine:
    """职场破局编剧 Agent — 事件发动机

    使用方式:
        engine = ZhichangEventEngine(llm_client)
        blueprint = await engine.generate(input_data)
    """

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: app.llm.client.LLMClient 实例，
                       使用 .generate(prompt, config) 接口
        """
        self._llm = llm_client

    async def generate(self, input_data: EventEngineInput) -> EventBlueprint:
        """生成一个事件方案

        Args:
            input_data: 当前故事状态和需求

        Returns:
            EventBlueprint: 结构化12字段事件方案
        """
        if not self._llm:
            # 无 LLM 时使用内置启发式生成（简化版）
            return self._heuristic_generate(input_data)

        from app.llm.client import GenerationConfig

        user_prompt = (
            f"请为以下状态生成一个职场事件：\n\n"
            f"{input_data.to_prompt_block()}"
        )

        config = GenerationConfig(
            temperature=0.85,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
        )

        try:
            result = await self._llm.generate(user_prompt, config)
            content = result.content
            blueprint = self._parse_response(content)
            return blueprint
        except Exception as e:
            logger.error("事件发动机 LLM 调用失败: %s", e)
            return self._heuristic_generate(input_data)

    def _parse_response(self, content: str) -> EventBlueprint:
        """从 LLM 响应中解析 JSON 为 EventBlueprint"""
        # 尝试提取 JSON 块
        text = content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        # 找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

        try:
            data = json.loads(text)
            return EventBlueprint(
                event_title=data.get("event_title", ""),
                conflict_cause=data.get("conflict_cause", ""),
                antagonist_goal=data.get("antagonist_goal", ""),
                antagonist_method=data.get("antagonist_method", ""),
                protagonist_surface=data.get("protagonist_surface", ""),
                protagonist_hidden=data.get("protagonist_hidden", ""),
                key_evidence=data.get("key_evidence", ""),
                reversal_trigger=data.get("reversal_trigger", ""),
                antagonist_consequence=data.get("antagonist_consequence", ""),
                protagonist_gain=data.get("protagonist_gain", ""),
                chapter_outline=data.get("chapter_outline", ""),
                killer_line=data.get("killer_line", ""),
            )
        except json.JSONDecodeError as e:
            logger.warning("事件发动机 JSON 解析失败: %s", e)
            return EventBlueprint(event_title="[解析失败]", conflict_cause=text[:200])

    def _heuristic_generate(self, inp: EventEngineInput) -> EventBlueprint:
        """无 LLM 时的启发式生成 — 提供基础骨架"""
        # 根据阶段选择事件方向
        stage_events = {
            "生存期": ["抢功劳", "甩锅项目", "会议羞辱", "财务卡报销", "年终考核打压"],
            "破局期": ["抢客户", "供应商设局", "竞标方案泄露", "跨部门踢皮球", "空降关系户"],
            "上位期": ["审计进场", "大老板暗访", "团队内鬼", "股权纠纷", "晋升名额被截胡"],
        }
        pool = stage_events.get(inp.stage, stage_events["生存期"])
        # 排除禁用元素
        available = [e for e in pool if e not in inp.forbidden_elements]
        if not available:
            available = [e for e in EVENT_TYPES if e not in inp.forbidden_elements]
        event_type = available[inp.chapter_number % len(available)] if available else "规则博弈"

        antagonist = inp.existing_antagonists[0] if inp.existing_antagonists else "未知对手"

        return EventBlueprint(
            event_title=f"{antagonist}的{event_type}",
            conflict_cause=f"{antagonist}为了个人利益，对{inp.protagonist_name}发动{event_type}",
            antagonist_goal=f"通过{event_type}打压{inp.protagonist_name}，巩固自身地位",
            antagonist_method=f"利用职务便利和信息不对称实施{event_type}",
            protagonist_surface=f"{inp.protagonist_name}表面接受安排，不动声色",
            protagonist_hidden="暗中收集证据，等待合适时机反击",
            key_evidence="邮件记录/系统日志/会议纪要（需LLM细化）",
            reversal_trigger="在公开场合亮出证据",
            antagonist_consequence=f"{antagonist}的行为被揭露，信任受损",
            protagonist_gain="获得上级认可，向上晋升一步",
            chapter_outline=(
                "1. 冲突爆发，主角被动\n"
                "2. 主角表面配合，暗中收集证据\n"
                "3. 公开场合反转，亮出关键证据\n"
                "4. 反派自食其果\n"
                "5. 主角获得收益，埋下新线索"
            ),
            killer_line=f"「{antagonist}，这份文件上的签名是你的吧？」",
        )


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def create_engine(llm_client=None) -> ZhichangEventEngine:
    """创建事件发动机实例"""
    return ZhichangEventEngine(llm_client)
