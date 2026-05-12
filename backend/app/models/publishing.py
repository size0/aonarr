"""发布与数据采集模型"""
import uuid
from datetime import datetime, date, timezone


from sqlalchemy import String, Integer, Float, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.connection import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), ForeignKey("novels.id"), nullable=False)
    chapter_id: Mapped[str] = mapped_column(String(64), ForeignKey("chapters.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # fanqie / qidian
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending / publishing / success / failed
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PlatformStats(Base):
    __tablename__ = "platform_stats"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    stat_date: Mapped[date] = mapped_column(Date, nullable=False)
    reads: Mapped[int] = mapped_column(Integer, default=0)
    favorites: Mapped[int] = mapped_column(Integer, default=0)
    recommends: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int] = mapped_column(Integer, nullable=True)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
