"""去 AI 味系统 — 疲劳词替换 + 禁用句式改写 + 文风指纹注入

工作模式：
1. prompt_rules() — 返回注入 ChapterWriter prompt 的反检测规则
2. post_process()  — 对已生成文本做后处理替换
3. full_anti_detect() — LLM 驱动的深度改写（调 audit_review 模型）

疲劳词表从 quality_radar 复用并扩展。
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.services.audit.quality_radar import (
    score_chapter,
)

logger = logging.getLogger(__name__)


# ── 疲劳词替换映射 ──────────────────────────────────────────────────

_FATIGUE_REPLACEMENTS: dict[str, list[str]] = {
    "不禁": ["忍不住", "自然而然", ""],
    "竟然": ["居然", "没想到", ""],
    "居然": ["竟", "倒是", ""],
    "不由自主": ["本能地", "鬼使神差", ""],
    "默默地": ["静静", "无声地", ""],
    "缓缓地": ["慢慢", "徐徐", ""],
    "微微一笑": ["笑了笑", "嘴角一翘", ""],
    "淡淡地": ["随口", "平静地", ""],
    "轻轻地": ["悄悄", "轻手轻脚", ""],
    "一股": ["", "某种", "一团"],
    "一丝": ["些许", "微弱的", ""],
    "一抹": ["淡淡", "浅浅", ""],
    "一缕": ["几缕", "丝丝", ""],
    "内心深处": ["心底", "潜意识里", ""],
    "心中暗想": ["心想", "琢磨", ""],
    "嘴角微微上扬": ["笑了", "咧嘴一笑", "扯了下嘴角"],
    "嘴角勾起": ["歪嘴一笑", "嘴角上翘", ""],
    "深吸一口气": ["吸了口气", "喘了口气", ""],
    "长舒一口气": ["松了口气", "舒了口气", ""],
    "眼眸": ["眼睛", "目光", "双眼"],
    "薄唇": ["嘴唇", "唇", ""],
    "唇角": ["嘴角", "嘴边", ""],
    "暗忖": ["想着", "琢磨", "盘算"],
    "思忖": ["想了想", "盘算", "寻思"],
}


# ── Prompt 注入规则 ─────────────────────────────────────────────────

def prompt_rules(genre: str = "") -> str:
    """生成注入 ChapterWriter system prompt 的生稿质感规则"""
    fatigue_sample = ", ".join(list(_FATIGUE_REPLACEMENTS.keys())[:15])

    rules = f"""━━━ 生稿质感校准 ━━━
【少用套话】这些词只在确实准确时使用，别连续出现: {fatigue_sample}
【避开腔调】
  - "一股/一丝/一缕 + 情绪" 这类空泛感受
  - "眼中闪过一抹/一丝" 这类镜头套句
  - "挺拔/修长的身影" 这类泛外貌
  - "清冷/低沉/磁性的声音" 这类空标签
【替代写法】
  - 情绪写成手上动作、停顿、改口、避让、抢话
  - 心理独白换成台词博弈或当场选择
  - 环境只挑一个能反映处境的细节
  - 段落开头轮换：动作、台词、物件、声音、反应、结果"""

    return rules


# ── 后处理 ──────────────────────────────────────────────────────────

def post_process(text: str, *, max_replacements_per_word: int = 3) -> tuple[str, list[dict]]:
    """对生成文本做疲劳词后处理替换

    Returns:
        (processed_text, changes_log)
    """
    changes = []
    result = text
    import random

    for word, replacements in _FATIGUE_REPLACEMENTS.items():
        count = result.count(word)
        if count <= 1:
            continue  # 出现1次可接受

        # 保留第1次出现，替换后续出现
        positions = []
        start = 0
        while True:
            idx = result.find(word, start)
            if idx == -1:
                break
            positions.append(idx)
            start = idx + len(word)

        # 从后往前替换（避免位移）
        replaced = 0
        for pos in reversed(positions[1:]):  # 跳过第1个
            if replaced >= max_replacements_per_word:
                break
            valid_replacements = [r for r in replacements if r]
            if not valid_replacements:
                valid_replacements = [""]
            replacement = random.choice(valid_replacements)
            result = result[:pos] + replacement + result[pos + len(word):]
            changes.append({
                "original": word,
                "replacement": replacement,
                "position": pos,
            })
            replaced += 1

    return result, changes


# ── LLM 深度改写 ───────────────────────────────────────────────────

_ANTI_DETECT_SYSTEM = """你是一位资深网文编辑，擅长把生硬稿改成能连载的正文。

任务：改写以下文本，保持原意和情节不变，去掉机械感、作文腔和套话。

改写规则：
1. 替换疲劳词（不禁/竟然/一丝/一股/缓缓地/微微一笑等）
2. 消除模式化句式（"XXX的身影"、"眼中闪过一丝"等）
3. 用具体感官细节替代抽象描写
4. 变化句式结构和段落开头
5. 保持对话的口语化和个性化
6. 保持原有的情节、人物、事件不变

输出纯文本，不要解释，不要添加标记。"""


async def full_anti_detect(
    db: Session,
    text: str,
    *,
    genre: str = "",
    max_text_len: int = 6000,
) -> dict:
    """LLM 驱动的深度去AI味改写

    Returns:
        {"original_score": float, "processed_score": float, "text": str, "improved": bool}
    """
    # 先评分
    original_qs = score_chapter(text)
    original_ai_score = original_qs.ai_detect or 0.0

    # 如果已经足够好，跳过
    if original_ai_score >= 80:
        return {
            "original_score": original_ai_score,
            "processed_score": original_ai_score,
            "text": text,
            "improved": False,
            "message": "AI味评分已达标，无需改写",
        }

    # 先做基础后处理
    processed, changes = post_process(text)

    # 再调 LLM 改写
    resolver = StageModelResolver(db)
    llm = resolver.get_llm_for_stage("audit_review")

    config = GenerationConfig(
        system=_ANTI_DETECT_SYSTEM,
        temperature=0.6,
        max_tokens=8192,
    )

    prompt = f"""请改写以下文本，去掉机械感、作文腔和套话，保持原意不变：

---原文---
{processed[:max_text_len]}
---原文结束---

请直接输出改写后的文本。"""

    try:
        result = await llm.generate(prompt, config)
        rewritten = result.content.strip()

        # 验证改写结果
        if len(rewritten) < len(text) * 0.5:
            # 改写过短，可能出错
            rewritten = processed

        new_qs = score_chapter(rewritten)
        return {
            "original_score": original_ai_score,
            "processed_score": new_qs.ai_detect,
            "text": rewritten,
            "improved": new_qs.ai_detect > original_ai_score,
            "changes_count": len(changes),
            "message": f"AI味: {original_ai_score:.0f} → {new_qs.ai_detect:.0f}",
        }
    except Exception as e:
        logger.error("Anti-detect LLM改写失败: %s", e)
        # 降级到纯后处理结果
        new_qs = score_chapter(processed)
        return {
            "original_score": original_ai_score,
            "processed_score": new_qs.ai_detect,
            "text": processed,
            "improved": new_qs.ai_detect > original_ai_score,
            "changes_count": len(changes),
            "message": f"LLM改写失败，仅做基础替换: {e}",
        }
