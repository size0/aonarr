"""书名优化器 — 四维拆解公式

基于用户总结的爆款书名方法论：
1. 背景/时间 — 故事世界设定（定基调）
2. 行为     — 主角在做什么（代入感）
3. 期待     — 读者期望/主角状态（悬念）
4. 反差/噱头 — 出人意料的元素（点击欲）

流程：
  用户草拟书名 → LLM 四维拆解 → 诊断缺失 → 对标爆款 → 生成 5 个优化候选
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一位网文标题策划专家。你精通爆款书名的底层逻辑——四维拆解公式。

## 四维公式

每个成功书名可拆为 4 个维度：
| 维度 | 含义 | 作用 |
|---|---|---|
| ① 背景/时间 | 故事世界设定 | 定基调、定类型 |
| ② 行为 | 主角在做什么 | 有动词才有画面，制造代入感 |
| ③ 期待 | 读者的期望/主角已有状态 | 制造悬念、"已经很强了"的前提 |
| ④ 反差/噱头 | 出人意料的元素 | 两个不该在一起的概念放一起，制造冲突和点击欲 |

## 关键规律
- 行为维度必须有动词感（开/捡/读/让/拉）
- 反差/噱头是点击率核心
- 期待制造"已经很强了"的前提，反差才有冲击
- 书名越口语化、第一人称，点击率越高
- 短书名（≤15字）比长书名好
- 逗号分句制造节奏感

## 成功案例
- "全球冰河，我捡到了一台神级贩卖机"（背景：冰河 | 行为：捡到 | 噱头：神级贩卖机）
- "我开的真实孤儿院不是杀手堂"（行为：开 | 期待：真的 | 反差：孤儿院vs杀手堂）
- "都快成仙了，才拉我进穿越萌新群"（期待：快成仙 | 行为：拉 | 反差：穿越萌新群）

你的任务：
1. 分析用户给出的书名，按四维拆解
2. 诊断哪些维度缺失或薄弱
3. 生成 5 个优化候选书名
4. 每个候选附带四维标注和预估吸引力评分(1-10)

输出严格 JSON 格式：
{
  "original": {
    "title": "原书名",
    "analysis": {
      "background": "背景维度分析（有/缺）",
      "action": "行为维度分析（有/缺）",
      "expectation": "期待维度分析（有/缺）",
      "contrast": "反差维度分析（有/缺）"
    },
    "score": 5,
    "diagnosis": "总体诊断（哪些维度缺失，为什么不够吸引人）"
  },
  "candidates": [
    {
      "title": "优化书名",
      "background": "背景描述",
      "action": "行为描述",
      "expectation": "期待描述",
      "contrast": "反差描述",
      "score": 8,
      "reason": "为什么这个更好"
    }
  ]
}"""


@dataclass
class TitleOptimizeResult:
    original_title: str = ""
    original_analysis: dict = field(default_factory=dict)
    original_score: int = 0
    diagnosis: str = ""
    candidates: list[dict] = field(default_factory=list)
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "original": {
                "title": self.original_title,
                "analysis": self.original_analysis,
                "score": self.original_score,
                "diagnosis": self.diagnosis,
            },
            "candidates": self.candidates,
        }


class TitleOptimizer:
    """AI 书名优化器"""

    def __init__(self, db: Session):
        self.db = db
        self._resolver = StageModelResolver(db)
        self._prompt_loader = PromptLoader(db)

    async def optimize(
        self,
        title: str,
        genre: str = "",
        synopsis: str = "",
        *,
        num_candidates: int = 5,
    ) -> TitleOptimizeResult:
        """对给定书名进行四维分析并生成优化候选

        Args:
            title: 用户的草拟书名
            genre: 小说题材
            synopsis: 故事简介（可选，提供后优化更精准）
            num_candidates: 生成候选数量
        """
        llm = self._resolver.get_llm_for_stage("prompt_optimization")

        system = self._prompt_loader.get_prompt("prompt_optimization", name="书名优化器")
        if not system:
            system = _SYSTEM_PROMPT

        config = GenerationConfig(
            system=system,
            max_tokens=4096,
            temperature=0.7,
        )

        user_prompt = f"""请分析并优化以下书名：

【原书名】{title}
【题材】{genre or '未指定'}
【故事简介】{synopsis or '未提供'}
【要求候选数】{num_candidates}

请用四维公式分析原书名，诊断缺失维度，然后生成 {num_candidates} 个优化候选。
每个候选都要比原书名在四维完整度上有明显提升。
输出严格 JSON。"""

        result = await llm.generate(user_prompt, config)

        parsed = self._parse_json(result.content)
        return self._build_result(title, parsed, result.content)

    def _build_result(self, title: str, parsed: dict, raw: str) -> TitleOptimizeResult:
        """从 LLM 输出构建结果"""
        r = TitleOptimizeResult(
            original_title=title,
            raw_response=raw,
        )

        if not parsed:
            r.diagnosis = "解析失败，请重试"
            return r

        original = parsed.get("original", {})
        r.original_analysis = original.get("analysis", {})
        r.original_score = int(original.get("score", 0))
        r.diagnosis = original.get("diagnosis", "")
        r.candidates = parsed.get("candidates", [])

        # 确保 score 是 int
        for c in r.candidates:
            try:
                c["score"] = int(c.get("score", 0))
            except (ValueError, TypeError):
                c["score"] = 0

        # 按分数降序排列
        r.candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

        return r

    @staticmethod
    def _parse_json(text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON"""
        import re
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
        return None
