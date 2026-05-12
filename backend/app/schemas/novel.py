"""小说/章节/人物 Pydantic DTO"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class NovelCreate(BaseModel):
    title: str
    genre: str = ""
    tags: list[str] = Field(default_factory=list)
    synopsis: str = ""
    premise: str = ""
    world_setting: str = ""
    target_word_count: int = 0
    target_chapter_count: int = 200
    words_per_chapter: int = 2000


class NovelUpdate(BaseModel):
    title: Optional[str] = None
    genre: Optional[str] = None
    tags: Optional[list[str]] = None
    synopsis: Optional[str] = None
    premise: Optional[str] = None
    world_setting: Optional[str] = None
    target_word_count: Optional[int] = None
    target_chapter_count: Optional[int] = None
    words_per_chapter: Optional[int] = None
    status: Optional[str] = None


class NovelDTO(BaseModel):
    id: str
    title: str
    genre: str
    tags: list[str]
    synopsis: str
    premise: str
    world_setting: str
    target_word_count: int
    target_chapter_count: int
    words_per_chapter: int
    current_word_count: int
    chapter_count: int
    status: str
    auto_approve_mode: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChapterCreate(BaseModel):
    number: int
    title: str = ""
    content: str = ""


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None


class ChapterDTO(BaseModel):
    id: str
    novel_id: str
    number: int
    title: str
    content: str
    summary: str
    word_count: int
    status: str
    tension_score: float
    model_used: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CharacterCreate(BaseModel):
    name: str
    role: str = "supporting"
    description: str = ""
    traits: list[str] = Field(default_factory=list)


class CharacterDTO(BaseModel):
    id: str
    novel_id: str
    name: str
    role: str
    description: str
    traits: list[str]
    first_appearance: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
