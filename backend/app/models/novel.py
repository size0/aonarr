"""小说与章节数据模型"""
import uuid
from datetime import datetime, timezone


from sqlalchemy import String, Integer, Float, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.connection import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Novel(Base):
    __tablename__ = "novels"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    genre: Mapped[str] = mapped_column(String(64), default="")
    tags: Mapped[str] = mapped_column(Text, default="")  # JSON array string
    synopsis: Mapped[str] = mapped_column(Text, default="")
    premise: Mapped[str] = mapped_column(Text, default="")
    world_setting: Mapped[str] = mapped_column(Text, default="")
    target_word_count: Mapped[int] = mapped_column(Integer, default=0)
    target_chapter_count: Mapped[int] = mapped_column(Integer, default=200)
    words_per_chapter: Mapped[int] = mapped_column(Integer, default=2000)
    current_word_count: Mapped[int] = mapped_column(Integer, default=0)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft/writing/paused/completed
    auto_approve_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    chapters: Mapped[list["Chapter"]] = relationship(back_populates="novel", cascade="all, delete-orphan")
    characters: Mapped[list["Character"]] = relationship(back_populates="novel", cascade="all, delete-orphan")
    world_items: Mapped[list["WorldItem"]] = relationship(back_populates="novel", cascade="all, delete-orphan")
    outline_nodes: Mapped[list["OutlineNode"]] = relationship(back_populates="novel", cascade="all, delete-orphan", foreign_keys="[OutlineNode.novel_id]")
    truth_files: Mapped[list["TruthFile"]] = relationship(back_populates="novel", cascade="all, delete-orphan")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft/generated/reviewed/published
    events: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    entities: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    foreshadows: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    tension_score: Mapped[float] = mapped_column(Float, default=0.0)
    model_used: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    novel: Mapped["Novel"] = relationship(back_populates="chapters")


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="supporting")  # protagonist/antagonist/supporting
    description: Mapped[str] = mapped_column(Text, default="")
    traits: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    relationships: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    first_appearance: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    novel: Mapped["Novel"] = relationship(back_populates="characters")


class WorldItem(Base):
    __tablename__ = "world_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)  # location/faction/item/rule/history
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    properties: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    novel: Mapped["Novel"] = relationship(back_populates="world_items")


class OutlineNode(Base):
    __tablename__ = "outline_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    parent_id: Mapped[str] = mapped_column(String(64), ForeignKey("outline_nodes.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(32), default="chapter")  # volume/act/chapter/scene/beat
    title: Mapped[str] = mapped_column(String(256), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")  # JSON extra data
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    novel: Mapped["Novel"] = relationship(back_populates="outline_nodes", foreign_keys=[novel_id])


# ── 真相文件 (Truth Files) ──────────────────────────────────────
# 借鉴 InkOS 的 7 维度真相文件体系，作为小说长期记忆的唯一事实来源

TRUTH_FILE_KEYS = (
    "current_state",       # 世界状态：角色位置、关系网络、已知信息
    "particle_ledger",     # 资源账本：物品、金钱、物资数量及衰减追踪
    "pending_hooks",       # 未闭合伏笔：铺垫、承诺、未解决冲突
    "chapter_summaries",   # 各章摘要：出场人物、关键事件、状态变化
    "subplot_board",       # 支线进度板：A/B/C 线状态、停滞检测
    "emotional_arcs",      # 情感弧线：按角色追踪情绪变化和成长
    "character_matrix",    # 角色交互矩阵：相遇记录、信息边界
)


class TruthFile(Base):
    __tablename__ = "truth_files"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    file_key: Mapped[str] = mapped_column(String(64), nullable=False)  # one of TRUTH_FILE_KEYS
    content: Mapped[str] = mapped_column(Text, default="")             # markdown / structured text
    data_json: Mapped[str] = mapped_column(Text, default="{}")         # structured JSON (machine-readable)
    version: Mapped[int] = mapped_column(Integer, default=1)           # bump on each update
    last_chapter: Mapped[int] = mapped_column(Integer, default=0)      # chapter# when last updated
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    novel: Mapped["Novel"] = relationship(back_populates="truth_files")


class AuditResult(Base):
    """审计结果结构化存储"""
    __tablename__ = "audit_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_type: Mapped[str] = mapped_column(String(32), default="full")  # full/quality/consistency/drift/anti_detect
    scores_json: Mapped[str] = mapped_column(Text, default="{}")  # QualityScore.to_dict()
    issues_json: Mapped[str] = mapped_column(Text, default="[]")  # issues list
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Integer, default=True)  # SQLite no native bool
    revision_round: Mapped[int] = mapped_column(Integer, default=0)  # 0=initial, 1-3=revision
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── 结构化剧情分析 ─────────────────────────────────────────────────

class PlotAnalysis(Base):
    """结构化剧情分析 — LLM 驱动的章节深度分析结果"""
    __tablename__ = "plot_analysis"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # 剧情结构
    plot_stage: Mapped[str] = mapped_column(String(32), default="")  # 开端/发展/高潮/结局/过渡
    conflict_level: Mapped[int] = mapped_column(Integer, default=0)  # 冲突强度 1-10
    conflict_types: Mapped[str] = mapped_column(Text, default="[]")  # JSON: ["人与人", "人与己"]

    # 情感分析
    emotional_tone: Mapped[str] = mapped_column(String(64), default="")  # 紧张/温馨/悲伤/激昂/平静
    emotional_intensity: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0-1.0
    emotional_curve: Mapped[str] = mapped_column(Text, default="{}")  # JSON: {start:0.3, middle:0.7, end:0.5}

    # 钩子 (Hook) 分析
    hooks: Mapped[str] = mapped_column(Text, default="[]")  # JSON: [{type,content,strength,position}]
    hooks_count: Mapped[int] = mapped_column(Integer, default=0)

    # 伏笔分析
    foreshadows_planted: Mapped[int] = mapped_column(Integer, default=0)
    foreshadows_resolved: Mapped[int] = mapped_column(Integer, default=0)

    # 角色状态追踪
    character_states: Mapped[str] = mapped_column(Text, default="[]")  # JSON: [{name,before,after,event}]

    # 节奏
    pacing: Mapped[str] = mapped_column(String(32), default="")  # slow/moderate/fast/varied

    # 质量评分
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-10
    pacing_score: Mapped[float] = mapped_column(Float, default=0.0)
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    coherence_score: Mapped[float] = mapped_column(Float, default=0.0)

    # 改进建议
    suggestions: Mapped[str] = mapped_column(Text, default="[]")  # JSON

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── 记忆编译缓存 ───────────────────────────────────────────────────

class MemoryCache(Base):
    """记忆编译 SHA 指纹缓存 — 避免未变更章节被重复编译"""
    __tablename__ = "memory_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)  # short/mid/long
    scope_key: Mapped[str] = mapped_column(String(128), nullable=False)  # "ch_5" / "ch_1_10" / "global"
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    compiled_text: Mapped[str] = mapped_column(Text, default="")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── 时序记忆索引 ───────────────────────────────────────────────────

class MemoryIndex(Base):
    """时序记忆索引 — 按章节存储结构化记忆条目，支持按类型/关键词检索"""
    __tablename__ = "memory_index"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)  # fact/foreshadow/summary/event/character_change
    content: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[str] = mapped_column(Text, default="")  # 逗号分隔关键词
    importance: Mapped[int] = mapped_column(Integer, default=5)  # 1-10 重要性
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── 知识图谱三元组 ───────────────────────────────────────────────────

class KnowledgeTriple(Base):
    """知识图谱三元组 — (主体, 谓词, 客体) + 来源追溯

    用于存储角色关系、地点属性、道具归属、势力从属等结构化知识。
    支持从章后管线自动提取，也支持手动编辑。
    """
    __tablename__ = "knowledge_triples"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)       # 主体（角色名/地点名/物品名）
    subject_type: Mapped[str] = mapped_column(String(32), default="character")  # character/location/item/faction/concept
    predicate: Mapped[str] = mapped_column(String(128), nullable=False)         # 谓词（关系/属性）
    object_id: Mapped[str] = mapped_column(String(128), nullable=False)         # 客体
    object_type: Mapped[str] = mapped_column(String(32), default="character")
    description: Mapped[str] = mapped_column(Text, default="")                  # 描述/备注
    confidence: Mapped[float] = mapped_column(Float, default=1.0)               # 置信度 0-1
    source_type: Mapped[str] = mapped_column(String(32), default="auto")        # auto/manual/bible
    source_chapter: Mapped[int] = mapped_column(Integer, nullable=True)         # 来源章节号
    first_appearance: Mapped[int] = mapped_column(Integer, nullable=True)       # 首次出现章节
    related_chapters: Mapped[str] = mapped_column(Text, default="")             # 逗号分隔相关章节号
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)              # 是否仍然有效
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class AutopilotCheckpoint(Base):
    """全托管写作进度检查点 — 用于断点恢复"""
    __tablename__ = "autopilot_checkpoints"

    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default="idle")
    current_chapter: Mapped[int] = mapped_column(Integer, default=0)
    target_end_chapter: Mapped[int] = mapped_column(Integer, default=0)
    chapters_completed: Mapped[int] = mapped_column(Integer, default=0)
    total_words_written: Mapped[int] = mapped_column(Integer, default=0)
    auto_beats: Mapped[bool] = mapped_column(Boolean, default=True)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
