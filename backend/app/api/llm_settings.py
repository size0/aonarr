"""LLM 模型配置 API — 双预设 + 阶段绑定 + 远程模型拉取"""
from __future__ import annotations

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.llm.resolver import StageModelResolver
from app.llm.profiles import LLMProfile
from app.llm.presets import ALL_STAGES, STAGE_LABELS
from app.schemas.llm import (
    LLMProfileCreate, LLMProfileUpdate, LLMProfileDTO,
    StageBindingDTO, SetStageBindingRequest, ApplyPresetRequest,
    StageModelConfigDTO,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/llm", tags=["llm-settings"])


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _resolver(db: Session = Depends(get_db)) -> StageModelResolver:
    return StageModelResolver(db)


# ── 全量配置读取 ──────────────────────────────────────────────────

@router.get("/config", response_model=StageModelConfigDTO)
def get_model_config(resolver: StageModelResolver = Depends(_resolver)):
    profiles = resolver.get_all_profiles()
    bindings = resolver.get_all_bindings()
    profile_map = {p.id: p for p in profiles}

    binding_dtos = []
    for b in bindings:
        p = profile_map.get(b.profile_id)
        binding_dtos.append(StageBindingDTO(
            stage=b.stage,
            stage_label=STAGE_LABELS.get(b.stage, b.stage),
            profile_id=b.profile_id,
            profile_name=p.name if p else "未知",
            model=b.model_override if b.model_override else (p.model if p else ""),
            preset_name=b.preset_name,
            model_override=b.model_override,
        ))

    return StageModelConfigDTO(
        active_preset=resolver.get_active_preset(),
        profiles=[
            LLMProfileDTO(
                id=p.id, name=p.name, protocol=p.protocol,
                base_url=p.base_url, api_key_masked=_mask_key(p.api_key),
                model=p.model, temperature=p.temperature,
                max_tokens=p.max_tokens, timeout_seconds=p.timeout_seconds,
                notes=p.notes,
            )
            for p in profiles
        ],
        bindings=binding_dtos,
        available_stages=[
            {"stage": s, "label": STAGE_LABELS.get(s, s)}
            for s in ALL_STAGES
        ],
    )


# ── Profile CRUD ──────────────────────────────────────────────────

@router.post("/profiles", response_model=LLMProfileDTO, status_code=201)
def create_profile(body: LLMProfileCreate, resolver: StageModelResolver = Depends(_resolver)):
    profile = LLMProfile(
        id=str(uuid.uuid4()),
        name=body.name, protocol=body.protocol,
        base_url=body.base_url, api_key=body.api_key,
        model=body.model, temperature=body.temperature,
        max_tokens=body.max_tokens, timeout_seconds=body.timeout_seconds,
        notes=body.notes,
    )
    created = resolver.create_profile(profile)
    return LLMProfileDTO(
        id=created.id, name=created.name, protocol=created.protocol,
        base_url=created.base_url, api_key_masked=_mask_key(created.api_key),
        model=created.model, temperature=created.temperature,
        max_tokens=created.max_tokens, timeout_seconds=created.timeout_seconds,
        notes=created.notes,
    )


@router.patch("/profiles/{profile_id}", response_model=LLMProfileDTO)
def update_profile(profile_id: str, body: LLMProfileUpdate,
                   resolver: StageModelResolver = Depends(_resolver)):
    updates = body.model_dump(exclude_unset=True)
    updated = resolver.update_profile(profile_id, updates)
    if not updated:
        raise HTTPException(404, "Profile 不存在")
    return LLMProfileDTO(
        id=updated.id, name=updated.name, protocol=updated.protocol,
        base_url=updated.base_url, api_key_masked=_mask_key(updated.api_key),
        model=updated.model, temperature=updated.temperature,
        max_tokens=updated.max_tokens, timeout_seconds=updated.timeout_seconds,
        notes=updated.notes,
    )


@router.delete("/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: str, resolver: StageModelResolver = Depends(_resolver)):
    if not resolver.delete_profile(profile_id):
        raise HTTPException(404, "Profile 不存在")


@router.post("/profiles/{profile_id}/test")
async def test_profile_connection(profile_id: str, resolver: StageModelResolver = Depends(_resolver)):
    """测试 LLM Profile 连接：向端点发送一个极简请求验证可达性"""
    profiles = resolver.get_all_profiles()
    profile = next((p for p in profiles if p.id == profile_id), None)
    if not profile:
        raise HTTPException(404, "Profile 不存在")

    base_url = (profile.base_url or "").rstrip("/")
    if not base_url:
        return {"success": False, "error": "未配置 base_url"}

    headers = {}
    if profile.api_key:
        headers["Authorization"] = f"Bearer {profile.api_key}"

    # 1) 先测 /models 端点
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{base_url}/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                model_count = len(data.get("data", []))
                return {
                    "success": True,
                    "message": f"连接成功，可用模型 {model_count} 个",
                    "model": profile.model,
                    "status_code": 200,
                }
            # 非 200 也返回信息
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
    except httpx.TimeoutException:
        return {"success": False, "error": "连接超时（15s）"}
    except Exception as e:
        return {"success": False, "error": str(e)[:300]}


# ── 预设 & 阶段绑定 ──────────────────────────────────────────────

@router.post("/apply-preset")
def apply_preset(body: ApplyPresetRequest, resolver: StageModelResolver = Depends(_resolver)):
    resolver.apply_preset(body.preset_name)
    return {"ok": True, "preset": body.preset_name}


@router.post("/bind-stage")
def bind_stage(body: SetStageBindingRequest, resolver: StageModelResolver = Depends(_resolver)):
    if body.stage not in ALL_STAGES:
        raise HTTPException(400, f"无效阶段: {body.stage}")
    resolver.set_stage_binding(body.stage, body.profile_id, body.model_override)
    return {"ok": True, "stage": body.stage, "profile_id": body.profile_id, "model_override": body.model_override}


# ── 远程模型拉取 ──────────────────────────────────────────────────

@router.get("/fetch-models")
async def fetch_remote_models(
    base_url: str = Query(..., description="API base URL, e.g. http://120.48.178.14:3003/v1"),
    api_key: str = Query("", description="API key"),
    timeout: int = Query(15, ge=1, le=60),
):
    """从远程 OpenAI 兼容端点拉取可用模型列表"""
    url = base_url.rstrip("/") + "/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(504, f"请求 {url} 超时({timeout}s)")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"远程返回错误: {e.response.text[:500]}")
    except Exception as e:
        raise HTTPException(502, f"无法连接 {url}: {e}")

    models_raw = data.get("data", [])
    models = [
        {
            "id": m.get("id", ""),
            "owned_by": m.get("owned_by", ""),
            "created": m.get("created"),
        }
        for m in models_raw
        if m.get("id")
    ]
    models.sort(key=lambda x: (x["owned_by"], x["id"]))

    return {"count": len(models), "models": models}


@router.get("/fetch-models/{profile_id}")
async def fetch_models_by_profile(
    profile_id: str,
    resolver: StageModelResolver = Depends(_resolver),
):
    """根据已有 Profile 的 base_url 和 api_key 拉取模型列表"""
    profile = resolver.get_all_profiles()
    target = next((p for p in profile if p.id == profile_id), None)
    if not target:
        raise HTTPException(404, "Profile 不存在")

    url = target.base_url.rstrip("/") + "/models"
    headers = {}
    if target.api_key:
        headers["Authorization"] = f"Bearer {target.api_key}"

    try:
        async with httpx.AsyncClient(timeout=target.timeout_seconds) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(504, f"请求 {url} 超时")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"远程返回错误: {e.response.text[:500]}")
    except Exception as e:
        raise HTTPException(502, f"无法连接 {url}: {e}")

    models_raw = data.get("data", [])
    models = [
        {
            "id": m.get("id", ""),
            "owned_by": m.get("owned_by", ""),
            "created": m.get("created"),
        }
        for m in models_raw
        if m.get("id")
    ]
    models.sort(key=lambda x: (x["owned_by"], x["id"]))

    return {
        "profile_id": profile_id,
        "profile_name": target.name,
        "base_url": target.base_url,
        "current_model": target.model,
        "count": len(models),
        "models": models,
    }
