"""文风漂移检测 — 对比当前章节文风指纹与全书基准

复用 services/analysis/style_fingerprint.py 的纯统计指纹算法。
不调用 LLM (可选)。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.analysis.style_fingerprint import analyze_style, StyleFingerprint


@dataclass
class DriftReport:
    """文风漂移报告"""
    chapter_number: int = 0
    drift_score: float = 0.0         # 0-100, 越高漂移越大
    drift_level: str = "normal"      # normal / mild / moderate / severe
    dimension_diffs: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "chapter_number": self.chapter_number,
            "drift_score": round(self.drift_score, 1),
            "drift_level": self.drift_level,
            "dimension_diffs": {
                k: round(v, 3) if isinstance(v, float) else v
                for k, v in self.dimension_diffs.items()
            },
            "warnings": self.warnings,
        }


# ── 维度权重 ────────────────────────────────────────────────────

DIMENSION_WEIGHTS = {
    "avg_sentence_length": 1.0,
    "short_sentence_ratio": 1.5,
    "long_sentence_ratio": 1.5,
    "dialogue_ratio": 2.0,
    "rhetoric_density": 1.5,
    "vocab_richness": 1.0,
    "avg_paragraph_length": 0.8,
}

DRIFT_THRESHOLDS = {
    "normal": 15,
    "mild": 30,
    "moderate": 50,
}


def detect_drift(
    chapter_text: str,
    baseline_text: str,
    chapter_number: int = 0,
    baseline_fp: StyleFingerprint | None = None,
) -> DriftReport:
    """检测单个章节相对于全书基准的文风漂移

    Args:
        chapter_text: 当前章节文本
        baseline_text: 全书文本 (用于计算基准, 如已有 baseline_fp 可为空)
        chapter_number: 章节编号
        baseline_fp: 预计算的全书文风指纹 (避免重复计算)
    """
    report = DriftReport(chapter_number=chapter_number)

    if not chapter_text.strip():
        return report

    # 计算指纹
    chapter_fp = analyze_style(chapter_text)
    if baseline_fp is None:
        if not baseline_text.strip():
            return report
        baseline_fp = analyze_style(baseline_text)

    # 计算各维度偏差
    diffs = _compute_dimension_diffs(chapter_fp, baseline_fp)
    report.dimension_diffs = diffs

    # 加权综合漂移分
    weighted_sum = 0.0
    total_weight = 0.0
    for dim, diff in diffs.items():
        w = DIMENSION_WEIGHTS.get(dim, 1.0)
        weighted_sum += abs(diff) * w
        total_weight += w

    raw_drift = weighted_sum / total_weight if total_weight > 0 else 0.0
    report.drift_score = min(raw_drift * 100, 100)

    # 分级
    if report.drift_score < DRIFT_THRESHOLDS["normal"]:
        report.drift_level = "normal"
    elif report.drift_score < DRIFT_THRESHOLDS["mild"]:
        report.drift_level = "mild"
    elif report.drift_score < DRIFT_THRESHOLDS["moderate"]:
        report.drift_level = "moderate"
    else:
        report.drift_level = "severe"

    # 生成具体警告
    report.warnings = _generate_warnings(diffs, chapter_fp, baseline_fp)

    return report


def detect_drift_multi(
    chapter_texts: list[str],
    full_text: str,
) -> list[DriftReport]:
    """检测多个章节的文风漂移 (批量)"""
    baseline_fp = analyze_style(full_text) if full_text.strip() else None
    reports: list[DriftReport] = []

    for i, text in enumerate(chapter_texts):
        report = detect_drift(
            chapter_text=text,
            baseline_text="",
            chapter_number=i + 1,
            baseline_fp=baseline_fp,
        )
        reports.append(report)

    return reports


# ── 内部算法 ────────────────────────────────────────────────────

def _compute_dimension_diffs(
    chapter: StyleFingerprint,
    baseline: StyleFingerprint,
) -> dict[str, float]:
    """计算各维度的相对偏差 (归一化到 0-1 范围)"""
    diffs: dict[str, float] = {}

    # 句长
    if baseline.avg_sentence_length > 0:
        diffs["avg_sentence_length"] = (
            abs(chapter.avg_sentence_length - baseline.avg_sentence_length)
            / max(baseline.avg_sentence_length, 1)
        )
    else:
        diffs["avg_sentence_length"] = 0.0

    # 短句比例
    diffs["short_sentence_ratio"] = abs(
        chapter.short_sentence_ratio - baseline.short_sentence_ratio
    )

    # 长句比例
    diffs["long_sentence_ratio"] = abs(
        chapter.long_sentence_ratio - baseline.long_sentence_ratio
    )

    # 对话比例 — 最重要的文风指标
    diffs["dialogue_ratio"] = abs(
        chapter.dialogue_ratio - baseline.dialogue_ratio
    )

    # 修辞密度
    if baseline.rhetoric_density > 0:
        diffs["rhetoric_density"] = (
            abs(chapter.rhetoric_density - baseline.rhetoric_density)
            / max(baseline.rhetoric_density, 0.1)
        )
    else:
        diffs["rhetoric_density"] = min(chapter.rhetoric_density / 5, 1.0)

    # 词汇丰富度
    diffs["vocab_richness"] = abs(
        chapter.vocab_richness - baseline.vocab_richness
    )

    # 段落长度
    if baseline.avg_paragraph_length > 0:
        diffs["avg_paragraph_length"] = (
            abs(chapter.avg_paragraph_length - baseline.avg_paragraph_length)
            / max(baseline.avg_paragraph_length, 1)
        )
    else:
        diffs["avg_paragraph_length"] = 0.0

    return diffs


def _generate_warnings(
    diffs: dict[str, float],
    chapter: StyleFingerprint,
    baseline: StyleFingerprint,
) -> list[str]:
    """根据偏差值生成具体的文字警告"""
    warnings: list[str] = []

    # 对话比例偏差 > 0.15
    if diffs.get("dialogue_ratio", 0) > 0.15:
        direction = "高于" if chapter.dialogue_ratio > baseline.dialogue_ratio else "低于"
        warnings.append(
            f"对话比例显著{direction}全书基准 "
            f"(本章 {chapter.dialogue_ratio:.1%} vs 基准 {baseline.dialogue_ratio:.1%})"
        )

    # 平均句长偏差 > 30%
    if diffs.get("avg_sentence_length", 0) > 0.3:
        direction = "长于" if chapter.avg_sentence_length > baseline.avg_sentence_length else "短于"
        warnings.append(
            f"平均句长显著{direction}全书基准 "
            f"(本章 {chapter.avg_sentence_length:.0f} vs 基准 {baseline.avg_sentence_length:.0f})"
        )

    # 修辞密度偏差 > 50%
    if diffs.get("rhetoric_density", 0) > 0.5:
        direction = "多于" if chapter.rhetoric_density > baseline.rhetoric_density else "少于"
        warnings.append(
            f"修辞手法密度显著{direction}全书基准 "
            f"(本章 {chapter.rhetoric_density:.1f} vs 基准 {baseline.rhetoric_density:.1f}/千字)"
        )

    # 短句比例偏差
    if diffs.get("short_sentence_ratio", 0) > 0.2:
        direction = "多" if chapter.short_sentence_ratio > baseline.short_sentence_ratio else "少"
        warnings.append(f"短句使用{direction}于全书基准, 节奏感可能不一致")

    # 词汇丰富度偏差
    if diffs.get("vocab_richness", 0) > 0.05:
        direction = "丰富" if chapter.vocab_richness > baseline.vocab_richness else "单调"
        warnings.append(f"用词较全书基准更{direction}, 可能存在文风切换")

    return warnings
