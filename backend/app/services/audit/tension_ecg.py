"""张力心电图 — 全书章节维度的张力曲线与节奏分析

对全书每一章计算 tension_score（来自 PostPipeline 已提取数据或即时计算），
输出可供前端 ECharts 渲染的张力心电图数据。

分析维度：
1. 各章 tension_score 曲线
2. 节奏评价（连续高/低潮检测）
3. 张力密度（高潮章占比）
4. 建议（连续低潮超 3 章预警）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.novel import Novel, Chapter

logger = logging.getLogger(__name__)


@dataclass
class TensionPoint:
    """单章张力数据点"""
    chapter_number: int
    title: str = ""
    tension_score: float = 0.0
    word_count: int = 0
    level: str = "normal"  # low / normal / high / climax
    summary: str = ""
    estimated: bool = False  # True = 临时启发式估分，非 PostPipeline 正式结果

    def to_dict(self) -> dict:
        d = {
            "chapter": self.chapter_number,
            "title": self.title,
            "tension": round(self.tension_score, 1),
            "words": self.word_count,
            "level": self.level,
            "summary": self.summary,
        }
        if self.estimated:
            d["estimated"] = True
        return d


@dataclass
class TensionECG:
    """张力心电图完整报告"""
    novel_id: str
    novel_title: str = ""
    chapter_count: int = 0
    points: list[TensionPoint] = field(default_factory=list)
    avg_tension: float = 0.0
    max_tension: float = 0.0
    min_tension: float = 0.0
    climax_ratio: float = 0.0
    pacing_grade: str = "B"   # S/A/B/C/D
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "novel_id": self.novel_id,
            "novel_title": self.novel_title,
            "chapter_count": self.chapter_count,
            "points": [p.to_dict() for p in self.points],
            "stats": {
                "avg_tension": round(self.avg_tension, 1),
                "max_tension": round(self.max_tension, 1),
                "min_tension": round(self.min_tension, 1),
                "climax_ratio": round(self.climax_ratio, 2),
                "pacing_grade": self.pacing_grade,
            },
            "warnings": self.warnings,
            "suggestions": self.suggestions,
        }


def _classify_tension(score: float) -> str:
    """将张力分数分级"""
    if score >= 7.0:
        return "climax"
    elif score >= 5.0:
        return "high"
    elif score >= 3.0:
        return "normal"
    return "low"


def _grade_pacing(points: list[TensionPoint]) -> str:
    """根据张力曲线节奏打分"""
    if not points or len(points) < 3:
        return "B"

    # 计算起伏度 (standard deviation)
    scores = [p.tension_score for p in points]
    n = len(scores)
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    std = variance ** 0.5

    # 计算相邻章节的变化频率
    direction_changes = 0
    for i in range(2, n):
        d1 = scores[i - 1] - scores[i - 2]
        d2 = scores[i] - scores[i - 1]
        if d1 * d2 < 0:
            direction_changes += 1

    change_rate = direction_changes / max(n - 2, 1)

    # 高潮比例
    climax_ratio = sum(1 for p in points if p.level in ("climax", "high")) / n

    # 综合评分
    if std >= 1.5 and change_rate >= 0.25 and 0.15 <= climax_ratio <= 0.5:
        return "S"
    elif std >= 1.0 and change_rate >= 0.2:
        return "A"
    elif std >= 0.7:
        return "B"
    elif std >= 0.4:
        return "C"
    return "D"


def generate_tension_ecg(db: Session, novel_id: str) -> TensionECG:
    """生成全书张力心电图"""
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        return TensionECG(novel_id=novel_id)

    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .order_by(Chapter.number)
        .all()
    )

    ecg = TensionECG(
        novel_id=novel_id,
        novel_title=novel.title,
        chapter_count=len(chapters),
    )

    if not chapters:
        return ecg

    # 构建张力数据点
    for ch in chapters:
        tension = 0.0

        # 统一来源：只用 tension_score（由 PostPipeline 校准写入）
        estimated = False
        if ch.tension_score and ch.tension_score > 0:
            tension = ch.tension_score
        elif ch.content:
            # 无 tension_score 时即时校准（同 PostPipeline 逻辑）
            from app.services.creation.post_pipeline import PostPipeline
            import json as _json
            raw_events = _json.loads(ch.events) if ch.events else []
            tension = PostPipeline._calibrate_tension(5.0, ch.content, raw_events)
            estimated = True

        point = TensionPoint(
            chapter_number=ch.number,
            title=ch.title or f"第{ch.number}章",
            tension_score=tension,
            word_count=ch.word_count or 0,
            level=_classify_tension(tension),
            summary=(ch.summary or "")[:80],
            estimated=estimated,
        )
        ecg.points.append(point)

    # 统计
    scores = [p.tension_score for p in ecg.points]
    ecg.avg_tension = sum(scores) / len(scores) if scores else 0
    ecg.max_tension = max(scores) if scores else 0
    ecg.min_tension = min(scores) if scores else 0
    ecg.climax_ratio = sum(1 for p in ecg.points if p.level == "climax") / len(ecg.points) if ecg.points else 0

    # 节奏评级
    ecg.pacing_grade = _grade_pacing(ecg.points)

    # 预警
    ecg.warnings = _detect_warnings(ecg.points)
    ecg.suggestions = _generate_suggestions(ecg)

    return ecg


def _detect_warnings(points: list[TensionPoint]) -> list[str]:
    """检测节奏问题"""
    warnings = []
    n = len(points)

    # 连续低潮检测
    low_streak = 0
    low_start = 0
    for i, p in enumerate(points):
        if p.level == "low":
            if low_streak == 0:
                low_start = i
            low_streak += 1
        else:
            if low_streak >= 3:
                s = points[low_start].chapter_number
                e = points[i - 1].chapter_number
                warnings.append(f"第{s}~{e}章连续{low_streak}章低潮，读者可能流失")
            low_streak = 0
    if low_streak >= 3:
        s = points[low_start].chapter_number
        e = points[-1].chapter_number
        warnings.append(f"第{s}~{e}章连续{low_streak}章低潮，读者可能流失")

    # 连续高潮检测
    high_streak = 0
    high_start = 0
    for i, p in enumerate(points):
        if p.level in ("climax", "high"):
            if high_streak == 0:
                high_start = i
            high_streak += 1
        else:
            if high_streak >= 4:
                s = points[high_start].chapter_number
                e = points[i - 1].chapter_number
                warnings.append(f"第{s}~{e}章连续{high_streak}章高张力，读者可能疲劳")
            high_streak = 0
    if high_streak >= 4:
        s = points[high_start].chapter_number
        e = points[-1].chapter_number
        warnings.append(f"第{s}~{e}章连续{high_streak}章高张力，读者可能疲劳")

    # 开局检测
    if n >= 3 and all(p.level == "low" for p in points[:3]):
        warnings.append("前3章均为低潮，开局可能不够吸引人")

    # 全书张力过低
    if n >= 5:
        avg = sum(p.tension_score for p in points) / n
        if avg < 3.0:
            warnings.append(f"全书平均张力仅{avg:.1f}，整体节奏偏平")

    return warnings


def _generate_suggestions(ecg: TensionECG) -> list[str]:
    """基于张力数据生成优化建议"""
    suggestions = []

    if ecg.pacing_grade in ("D", "C"):
        suggestions.append("节奏过于平淡，建议增加冲突密度，每3-5章至少安排一次高潮")

    if ecg.climax_ratio < 0.15 and ecg.chapter_count >= 5:
        suggestions.append(f"高潮章占比仅{ecg.climax_ratio:.0%}，建议增加至20%以上")

    if ecg.climax_ratio > 0.6:
        suggestions.append("高潮章过多，建议穿插舒缓章节让读者喘息")

    if ecg.avg_tension < 4.0 and ecg.chapter_count >= 3:
        suggestions.append("整体张力偏低，建议增加对抗性事件和悬念钩子")

    # 检查是否有起伏
    if ecg.max_tension - ecg.min_tension < 2.0 and ecg.chapter_count >= 5:
        suggestions.append("张力曲线过于平坦，缺少起伏对比，建议制造更大的高低差")

    return suggestions
