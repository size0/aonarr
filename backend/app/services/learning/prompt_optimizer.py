"""提示词优化 — 基于知识库与写作效果反馈优化系统提示词

调用 get_llm_for_stage("prompt_optimization")
写入 OptimizationLog 表
"""
from __future__ import annotations

import json
import logging
import re

from app.db.connection import SessionLocal
from app.llm.client import LLMClient, GenerationConfig
from app.llm.resolver import StageModelResolver
from app.models.learning import KnowledgeEntry, OptimizationLog

logger = logging.getLogger(__name__)

# ── 可优化的提示词目标 ──────────────────────────────────────────

OPTIMIZATION_TARGETS = {
    "chapter_writing": {
        "label": "章节写作提示词",
        "description": "用于生成小说正文的核心提示词",
    },
    "outline_planning": {
        "label": "大纲规划提示词",
        "description": "用于生成小说大纲/卷/幕/章结构的提示词",
    },
    "post_chapter_pipeline": {
        "label": "章后管线提示词",
        "description": "用于章后提取摘要/事件/关系的提示词",
    },
}

SYSTEM_PROMPT = """你是一位AI提示词工程专家，专注于小说创作领域。
基于提供的知识库洞察和当前提示词，生成改进建议。

请严格按 JSON 格式输出：
{
  "analysis": "当前提示词的优缺点分析 (50-100字)",
  "suggestions": [
    {"aspect": "改进方面", "before": "原文片段或描述", "after": "建议改进为", "reason": "原因"}
  ],
  "improved_prompt": "完整的改进后提示词",
  "expected_improvement": "预期改进效果描述",
  "confidence": 0.0-1.0
}"""


async def optimize_prompts(
    targets: list[str] | None = None,
    current_prompts: dict[str, str] | None = None,
) -> list[dict]:
    """对指定目标的提示词进行优化

    Args:
        targets: 要优化的目标列表, None=全部
        current_prompts: 当前提示词 {target: prompt_text}
    """
    from app.api.learning import push_activity

    db = SessionLocal()
    try:
        # 获取 LLM
        try:
            resolver = StageModelResolver(db)
            llm = resolver.get_llm_for_stage("prompt_optimization")
        except Exception as e:
            logger.error("获取 prompt_optimization LLM 失败: %s", e)
            push_activity(f"❌ 提示词优化失败: LLM 未配置 ({e})", "error")
            return []

        # 获取知识库中的高质量条目
        knowledge = _load_relevant_knowledge(db)

        if targets is None:
            targets = list(OPTIMIZATION_TARGETS.keys())

        results: list[dict] = []

        for target in targets:
            if target not in OPTIMIZATION_TARGETS:
                continue

            current_prompt = (current_prompts or {}).get(target, "")
            if not current_prompt:
                current_prompt = f"[{OPTIMIZATION_TARGETS[target]['label']}的默认提示词 - 尚未自定义]"

            push_activity(f"⚡ 优化中: {OPTIMIZATION_TARGETS[target]['label']}")
            try:
                result = await _optimize_single(db, llm, target, current_prompt, knowledge)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error("优化 %s 失败: %s", target, e)

        if results:
            push_activity(f"✅ 提示词优化完成: {len(results)} 项")
        else:
            push_activity("ℹ️ 提示词优化完成，无新建议")
        return results

    finally:
        db.close()


async def _optimize_single(
    db,
    llm: LLMClient,
    target: str,
    current_prompt: str,
    knowledge: str,
) -> dict | None:
    """优化单个目标的提示词"""
    meta = OPTIMIZATION_TARGETS[target]

    prompt = f"""## 优化目标
{meta['label']}: {meta['description']}

## 当前提示词
```
{current_prompt[:3000]}
```

## 知识库洞察
{knowledge[:4000]}

## 任务
分析当前提示词，结合知识库中的创作洞察，提出改进建议。
重点关注：
1. 是否充分利用了热门小说的套路和模式
2. 生成内容的质量和可读性
3. 文风一致性控制
4. 节奏和爽点把控"""

    config = GenerationConfig(
        system=SYSTEM_PROMPT,
        temperature=0.6,
        max_tokens=4096,
    )

    result = await llm.generate(prompt, config)
    parsed = _parse_response(result.content)

    # 写入 OptimizationLog
    log = OptimizationLog(
        target="prompt",
        description=f"优化 {meta['label']}",
        before_snapshot=json.dumps({"target": target, "prompt": current_prompt[:2000]}, ensure_ascii=False),
        after_snapshot=json.dumps(parsed, ensure_ascii=False),
        improvement_score=float(parsed.get("confidence", 0.5)),
        applied=False,
    )
    db.add(log)
    db.commit()

    logger.info("提示词优化完成: %s (confidence=%.2f)", target, log.improvement_score)

    return {
        "target": target,
        "label": meta["label"],
        "log_id": log.id,
        "confidence": log.improvement_score,
        "suggestions_count": len(parsed.get("suggestions", [])),
    }


def _load_relevant_knowledge(db, limit: int = 20) -> str:
    """加载高质量知识条目作为优化上下文"""
    entries = (
        db.query(KnowledgeEntry)
        .order_by(KnowledgeEntry.quality_score.desc())
        .limit(limit)
        .all()
    )

    if not entries:
        return "知识库为空，暂无可参考的创作洞察。"

    parts: list[str] = []
    for entry in entries:
        try:
            content = json.loads(entry.content)
            insights = content.get("insights", [])
            pattern = content.get("pattern", "")
        except (json.JSONDecodeError, AttributeError):
            insights = []
            pattern = ""

        item = f"- [{entry.category}] {entry.title}"
        if pattern:
            item += f"\n  模式: {pattern}"
        if insights:
            item += "\n  洞察: " + "; ".join(insights[:3])
        parts.append(item)

    return "\n".join(parts)


def _parse_response(content: str) -> dict:
    """解析 LLM 响应"""
    content = content.strip()
    block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    text = block.group(1).strip() if block else content
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        text = text[first:last + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"analysis": content[:300], "suggestions": [], "confidence": 0.3}
