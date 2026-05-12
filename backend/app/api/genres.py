"""题材规则 API"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.genre_profile import list_genres, get_genre, load_all_genres

router = APIRouter(prefix="/genres", tags=["genres"])


@router.get("")
def get_all_genres():
    """列出所有可用题材（轻量摘要）"""
    return list_genres()


@router.get("/{genre_id}")
def get_genre_detail(genre_id: str):
    """获取完整题材规则"""
    profile = get_genre(genre_id)
    if not profile:
        raise HTTPException(404, f"题材不存在: {genre_id}")
    return profile.to_dict()


@router.get("/{genre_id}/prompt")
def get_genre_prompt(genre_id: str):
    """获取该题材的可注入 prompt 文本"""
    profile = get_genre(genre_id)
    if not profile:
        raise HTTPException(404, f"题材不存在: {genre_id}")
    return {"genre_id": genre_id, "prompt_section": profile.to_prompt_section()}


@router.get("/{genre_id}/fatigue-words")
def get_fatigue_words(genre_id: str):
    """获取题材的疲劳词表"""
    profile = get_genre(genre_id)
    if not profile:
        raise HTTPException(404, f"题材不存在: {genre_id}")
    return {"genre_id": genre_id, "fatigue_words": profile.fatigue_words}


@router.post("/reload")
def reload_genres():
    """重新加载所有题材文件"""
    genres = load_all_genres(force_reload=True)
    return {"reloaded": len(genres), "ids": list(genres.keys())}
