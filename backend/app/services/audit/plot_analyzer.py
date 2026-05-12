"""PlotAnalyzer — LLM 驱动的结构化剧情分析

对每章执行深度分析，输出：
- 剧情阶段 (plot_stage)
- 冲突强度与类型 (conflict_level, conflict_types)
- 情感基调与曲线 (emotional_tone, emotional_intensity, emotional_curve)
- 钩子分析 (hooks)
- 伏笔植入/回收 (foreshadows_planted/resolved)
- 角色状态变化 (character_states)
- 节奏 (pacing)
- 四维评分 (overall/pacing/engagement/coherence)
- 改进建议 (suggestions)

结果写入 PlotAnalysis 表。可在 PostPipeline 或独立 API 调用中使用。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.models.novel import Novel, Chapter, PlotAnalysis
from app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

_PLOT_ANALYSIS_SYSTEM = """你是一位资深的小说叙事结构分析师。请对给定章节进行深度剧情分析。

输出严格 JSON 格式：
{
  "plot_stage": "开端|发展|高潮|结局|过渡",
  "conflict_level": 7,
  "conflict_types": ["人与人", "人与己"],
  "emotional_tone": "紧张",
  "emotional_intensity": 0.8,
  "emotional_curve": {"start": 0.3, "middle": 0.8, "end": 0.6},
  "hooks": [
    {"type": "悬念|情感|冲突|认知", "content": "具体内容", "strength": 8, "position": "开头|中段|结尾"}
  ],
  "foreshadows_planted": 2,
  "foreshadows_resolved": 1,
  "character_states": [
    {"name": "角色名", "state_before": "之前状态", "state_after": "之后状态", "key_event": "触发事件"}
  ],
  "pacing": "slow|moderate|fast|varied",
  "scores": {
    "overall": 7.5,
    "pacing": 7.0,
    "engagement": 8.0,
    "coherence": 7.5
  },
  "suggestions": ["建议1", "建议2"]
}

分析规则：
1. conflict_level 范围 1-10，无冲突=1，生死/命运级=10
2. conflict_types: 人与人/人与己/人与环境/人与命运/人与社会
3. emotional_intensity 范围 0.0-1.0
4. emotional_curve 分三段 (start/middle/end) 各 0.0-1.0
5. hooks 的 strength 范围 1-10
6. scores 各项范围 0.0-10.0
7. suggestions 最多5条，具体可操作
8. 不要编造正文中不存在的内容"""


class PlotAnalyzer:
    """LLM 驱动的结构化剧情分析器"""

    def __init__(self, db: Session):
        self.db = db
        self._resolver = StageModelResolver(db)
        self._prompt_loader = PromptLoader(db)

    async def analyze(
        self,
        novel_id: str,
        chapter_number: int,
        *,
        max_content_chars: int = 8000,
        force: bool = False,
    ) -> PlotAnalysis:
        """分析单章剧情结构

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            max_content_chars: 正文最大字符数（防超 token）
            force: True 则覆盖已有分析

        Returns:
            PlotAnalysis 对象
        """
        # 检查已有分析
        if not force:
            existing = (
                self.db.query(PlotAnalysis)
                .filter_by(novel_id=novel_id, chapter_number=chapter_number)
                .first()
            )
            if existing:
                logger.info("[PlotAnalyzer] 已有分析: %s #%d, 跳过", novel_id, chapter_number)
                return existing

        # 加载章节
        chapter = (
            self.db.query(Chapter)
            .filter_by(novel_id=novel_id, number=chapter_number)
            .first()
        )
        if not chapter or not chapter.content:
            raise ValueError(f"章节不存在或内容为空: {novel_id} #{chapter_number}")

        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        novel_title = novel.title if novel else "未知"
        novel_genre = novel.genre if novel else ""

        # LLM 调用
        llm = self._resolver.get_llm_for_stage("post_chapter_pipeline")

        system = self._prompt_loader.get_prompt(
            "post_chapter_pipeline", name="PlotAnalyzer 剧情分析"
        )
        if not system:
            system = _PLOT_ANALYSIS_SYSTEM

        config = GenerationConfig(
            system=system,
            max_tokens=4096,
            temperature=0.3,
        )

        user_prompt = f"""请对以下章节进行深度剧情结构分析。

【小说】《{novel_title}》（{novel_genre}）
【章节】第 {chapter_number} 章 {chapter.title or ''}
【字数】{len(chapter.content)} 字

---正文开始---
{chapter.content[:max_content_chars]}
---正文结束---

请严格按 JSON 格式输出分析结果。"""

        result = await llm.generate(user_prompt, config)
        parsed = _extract_json(result.content)

        # 写入 DB
        analysis = self._save_analysis(novel_id, chapter_number, parsed)

        logger.info(
            "[PlotAnalyzer] %s #%d → stage=%s conflict=%d engagement=%.1f",
            novel_id, chapter_number,
            analysis.plot_stage,
            analysis.conflict_level,
            analysis.engagement_score,
        )
        return analysis

    async def analyze_all(
        self,
        novel_id: str,
        *,
        force: bool = False,
    ) -> list[PlotAnalysis]:
        """分析全书所有章节"""
        chapters = (
            self.db.query(Chapter)
            .filter(Chapter.novel_id == novel_id, Chapter.content != "")
            .order_by(Chapter.number)
            .all()
        )
        results = []
        for ch in chapters:
            try:
                analysis = await self.analyze(
                    novel_id, ch.number, force=force
                )
                results.append(analysis)
            except Exception as e:
                logger.warning("[PlotAnalyzer] 分析失败 %s #%d: %s", novel_id, ch.number, e)
        return results

    def get_analysis(self, novel_id: str, chapter_number: int) -> Optional[PlotAnalysis]:
        """获取已有分析（不调 LLM）"""
        return (
            self.db.query(PlotAnalysis)
            .filter_by(novel_id=novel_id, chapter_number=chapter_number)
            .first()
        )

    def get_all_analyses(self, novel_id: str) -> list[PlotAnalysis]:
        """获取全书分析"""
        return (
            self.db.query(PlotAnalysis)
            .filter_by(novel_id=novel_id)
            .order_by(PlotAnalysis.chapter_number)
            .all()
        )

    def _save_analysis(
        self, novel_id: str, chapter_number: int, data: dict
    ) -> PlotAnalysis:
        """将 LLM 解析结果保存到 PlotAnalysis"""
        # 删除旧记录
        self.db.query(PlotAnalysis).filter_by(
            novel_id=novel_id, chapter_number=chapter_number
        ).delete()

        scores = data.get("scores", {})

        analysis = PlotAnalysis(
            novel_id=novel_id,
            chapter_number=chapter_number,
            plot_stage=data.get("plot_stage", ""),
            conflict_level=_safe_int(data.get("conflict_level"), 0, 10),
            conflict_types=json.dumps(data.get("conflict_types", []), ensure_ascii=False),
            emotional_tone=data.get("emotional_tone", ""),
            emotional_intensity=_safe_float(data.get("emotional_intensity"), 0.0, 1.0),
            emotional_curve=json.dumps(data.get("emotional_curve", {}), ensure_ascii=False),
            hooks=json.dumps(data.get("hooks", []), ensure_ascii=False),
            hooks_count=len(data.get("hooks", [])),
            foreshadows_planted=_safe_int(data.get("foreshadows_planted"), 0, 100),
            foreshadows_resolved=_safe_int(data.get("foreshadows_resolved"), 0, 100),
            character_states=json.dumps(data.get("character_states", []), ensure_ascii=False),
            pacing=data.get("pacing", ""),
            overall_score=_safe_float(scores.get("overall"), 0.0, 10.0),
            pacing_score=_safe_float(scores.get("pacing"), 0.0, 10.0),
            engagement_score=_safe_float(scores.get("engagement"), 0.0, 10.0),
            coherence_score=_safe_float(scores.get("coherence"), 0.0, 10.0),
            suggestions=json.dumps(data.get("suggestions", []), ensure_ascii=False),
        )
        self.db.add(analysis)
        self.db.commit()
        return analysis


# ── 工具函数 ────────────────────────────────────────────────────

def _safe_int(val, low: int = 0, high: int = 10) -> int:
    try:
        return max(low, min(high, int(val)))
    except (TypeError, ValueError):
        return low


def _safe_float(val, low: float = 0.0, high: float = 10.0) -> float:
    try:
        return max(low, min(high, float(val)))
    except (TypeError, ValueError):
        return low


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        try:
            return json.loads(text[start:end].strip())
        except json.JSONDecodeError:
            pass
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        try:
            return json.loads(text[first:last + 1])
        except json.JSONDecodeError:
            pass
    return {}
