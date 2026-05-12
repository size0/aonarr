"""拆书分析 Pydantic DTO"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AnalysisJobCreate(BaseModel):
    novel_title: str
    source_file: str


class AnalysisJobDTO(BaseModel):
    id: str
    novel_title: str
    source_file: str
    status: str
    progress: float
    chapter_count: int
    result_summary: dict
    error_message: str
    created_at: datetime
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class AnalysisChapterDTO(BaseModel):
    id: str
    job_id: str
    chapter_number: int
    chapter_title: str
    characters: list[dict]
    events: list[dict]
    relationships: list[dict]
    foreshadows: list[dict]
    summary: str
    word_count: int

    class Config:
        from_attributes = True
