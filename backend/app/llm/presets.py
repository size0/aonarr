"""双预设定义 — 实用版 & 旗舰版

每个预设为 11 个阶段指定默认 Profile 模型。
用户可一键切换预设，也可在预设基础上自定义修改个别阶段。
"""
from __future__ import annotations

from dataclasses import dataclass

# ── 11 个阶段常量 ─────────────────────────────────────────────────

STAGE_CHAPTER_WRITING = "chapter_writing"
STAGE_OUTLINE_PLANNING = "outline_planning"
STAGE_POST_CHAPTER = "post_chapter_pipeline"
STAGE_BOOK_EXTRACT = "book_analysis_extract"
STAGE_BOOK_DEEP = "book_analysis_deep"
STAGE_STYLE_DETECTION = "style_detection"
STAGE_AUDIT_REVIEW = "audit_review"
STAGE_LEARNING_AGENT = "learning_agent"
STAGE_PROMPT_OPT = "prompt_optimization"
STAGE_PREDICTION = "prediction"
STAGE_EMBEDDING = "embedding"

ALL_STAGES = [
    STAGE_CHAPTER_WRITING,
    STAGE_OUTLINE_PLANNING,
    STAGE_POST_CHAPTER,
    STAGE_BOOK_EXTRACT,
    STAGE_BOOK_DEEP,
    STAGE_STYLE_DETECTION,
    STAGE_AUDIT_REVIEW,
    STAGE_LEARNING_AGENT,
    STAGE_PROMPT_OPT,
    STAGE_PREDICTION,
    STAGE_EMBEDDING,
]

STAGE_LABELS = {
    STAGE_CHAPTER_WRITING: "章节正文写作",
    STAGE_OUTLINE_PLANNING: "大纲规划",
    STAGE_POST_CHAPTER: "章后管线",
    STAGE_BOOK_EXTRACT: "拆书-批量提取",
    STAGE_BOOK_DEEP: "拆书-深度分析",
    STAGE_STYLE_DETECTION: "文风检测",
    STAGE_AUDIT_REVIEW: "审核校对",
    STAGE_LEARNING_AGENT: "学习Agent",
    STAGE_PROMPT_OPT: "提示词优化",
    STAGE_PREDICTION: "数据预测",
    STAGE_EMBEDDING: "向量嵌入",
}


@dataclass
class PresetStageModel:
    """预设中某个阶段对应的模型"""
    model: str
    reason: str


# ── 🔥 实用版预设 ─────────────────────────────────────────────────

PRACTICAL_PRESET: dict[str, PresetStageModel] = {
    STAGE_CHAPTER_WRITING: PresetStageModel(
        model="claude-opus-4-7-medium",
        reason="文笔90分，30s/章，性价比最高",
    ),
    STAGE_OUTLINE_PLANNING: PresetStageModel(
        model="gemini-3.1-pro-high",
        reason="结构化强，成本低",
    ),
    STAGE_POST_CHAPTER: PresetStageModel(
        model="gemini-2.5-flash",
        reason="高频提取，快且省",
    ),
    STAGE_BOOK_EXTRACT: PresetStageModel(
        model="gemini-2.5-flash",
        reason="批量处理，几十分钟/本",
    ),
    STAGE_BOOK_DEEP: PresetStageModel(
        model="gemini-3.1-pro-high",
        reason="需要理解力",
    ),
    STAGE_STYLE_DETECTION: PresetStageModel(
        model="claude-opus-4-7-medium",
        reason="Claude对语感敏感",
    ),
    STAGE_AUDIT_REVIEW: PresetStageModel(
        model="gemini-3.1-pro-high",
        reason="逻辑推理",
    ),
    STAGE_LEARNING_AGENT: PresetStageModel(
        model="gemini-2.5-flash",
        reason="量大(每天几千次)，成本敏感",
    ),
    STAGE_PROMPT_OPT: PresetStageModel(
        model="claude-opus-4-7-medium",
        reason="周频，适中",
    ),
    STAGE_PREDICTION: PresetStageModel(
        model="gemini-3.1-pro-high",
        reason="数据分析",
    ),
    STAGE_EMBEDDING: PresetStageModel(
        model="text-embedding-3-small",
        reason="向量嵌入专用",
    ),
}


# ── 👑 旗舰版预设 ─────────────────────────────────────────────────

FLAGSHIP_PRESET: dict[str, PresetStageModel] = {
    STAGE_CHAPTER_WRITING: PresetStageModel(
        model="claude-opus-4.6-thinking",
        reason="文笔100分，4min/章，最强",
    ),
    STAGE_OUTLINE_PLANNING: PresetStageModel(
        model="claude-opus-4.6-thinking",
        reason="深度思考出最优结构",
    ),
    STAGE_POST_CHAPTER: PresetStageModel(
        model="claude-opus-4-7-medium",
        reason="提取也用Claude保语义精度",
    ),
    STAGE_BOOK_EXTRACT: PresetStageModel(
        model="claude-opus-4-7-medium",
        reason="比Flash更精准",
    ),
    STAGE_BOOK_DEEP: PresetStageModel(
        model="claude-opus-4.6-thinking",
        reason="最深度理解",
    ),
    STAGE_STYLE_DETECTION: PresetStageModel(
        model="claude-opus-4.6-thinking",
        reason="最精准语感判断",
    ),
    STAGE_AUDIT_REVIEW: PresetStageModel(
        model="claude-opus-4.6-thinking",
        reason="最严格逻辑审查",
    ),
    STAGE_LEARNING_AGENT: PresetStageModel(
        model="gemini-3.1-pro-high",
        reason="即使旗舰版也不建议用thinking，量太大",
    ),
    STAGE_PROMPT_OPT: PresetStageModel(
        model="claude-opus-4.6-thinking",
        reason="深度思考优化",
    ),
    STAGE_PREDICTION: PresetStageModel(
        model="claude-opus-4.6-thinking",
        reason="最精准分析",
    ),
    STAGE_EMBEDDING: PresetStageModel(
        model="text-embedding-3-small",
        reason="向量嵌入专用(无替代)",
    ),
}


PRESETS = {
    "practical": PRACTICAL_PRESET,
    "flagship": FLAGSHIP_PRESET,
}


def get_preset(name: str) -> dict[str, PresetStageModel]:
    """获取预设，不存在则返回实用版"""
    return PRESETS.get(name, PRACTICAL_PRESET)
