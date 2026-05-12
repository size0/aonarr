"""拆书分析数据模型"""
import uuid
from datetime import datetime, timezone


from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.connection import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_title: Mapped[str] = mapped_column(String(256), nullable=False)
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending / scanning / extracting / aggregating / done / failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    result_summary: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class AnalysisChapterResult(Base):
    __tablename__ = "analysis_chapter_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("analysis_jobs.id"), nullable=False)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_title: Mapped[str] = mapped_column(String(256), default="")
    characters: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    events: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    relationships: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    foreshadows: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    summary: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
