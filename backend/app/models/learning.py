"""学习Agent数据模型"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.connection import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class HotNovelMeta(Base):
    __tablename__ = "hot_novel_meta"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # fanqie / qidian
    source_book_id: Mapped[str] = mapped_column(String(64), default="")  # 平台侧 book_id
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    author: Mapped[str] = mapped_column(String(128), default="")
    genre: Mapped[str] = mapped_column(String(64), default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, nullable=True)
    read_count: Mapped[int] = mapped_column(Integer, default=0)  # 累计阅读人数
    bookshelf_count: Mapped[int] = mapped_column(Integer, default=0)  # 收藏人数
    created_at_source: Mapped[str] = mapped_column(String(64), default="")  # 平台侧创建时间 ISO
    synopsis: Mapped[str] = mapped_column(Text, default="")
    cover_url: Mapped[str] = mapped_column(String(512), default="")
    rank_info: Mapped[str] = mapped_column(Text, default="{}")  # JSON: {rank_type: position}
    source_url: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="meta")  # meta / crawling / done / failed
    crawled_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class HotNovelChapter(Base):
    __tablename__ = "hot_novel_chapters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_chapter_id: Mapped[str] = mapped_column(String(64), default="")
    chapter_number: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    # opening_pattern / thrill_distribution / character_template / dialogue_style
    # writing_style / foreshadow_technique / genre_formula
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_novel_id: Mapped[str] = mapped_column(String(64), nullable=True)
    source_file: Mapped[str] = mapped_column(String(512), default="")  # 教程导入时的文件路径
    tags: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class OptimizationLog(Base):
    __tablename__ = "optimization_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    target: Mapped[str] = mapped_column(String(64), nullable=False)  # prompt / workflow / model_config
    description: Mapped[str] = mapped_column(Text, default="")
    before_snapshot: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    after_snapshot: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    improvement_score: Mapped[float] = mapped_column(Float, nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
