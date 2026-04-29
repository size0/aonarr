from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.errors import api_error
from app.core.security import decrypt_secret, encrypt_secret, mask_secret, utc_now
from app.core.store import store
from app.models.schemas import LLMProfileCreate, LLMProfileUpdate
from app.services.llm_client import test_llm_profile

router = APIRouter(prefix="/llm-profiles", tags=["llm-profiles"])


def public_profile(profile: dict) -> dict:
    result = {key: value for key, value in profile.items() if key != "api_key_encrypted"}
    try:
        result["secret_ref"] = mask_secret(decrypt_secret(profile.get("api_key_encrypted", "")))
    except Exception:
        result["secret_ref"] = "••••"
    return result


@router.get("")
def list_profiles(_: dict[str, str] = Depends(require_admin)) -> dict[str, list[dict]]:
    return {"data": [public_profile(profile) for profile in store.list_items("llm_profiles")]}


@router.post("", status_code=201)
def create_profile(payload: LLMProfileCreate, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    now = utc_now()
    profile = payload.model_dump(exclude={"api_key"})
    profile.update(
        {
            "id": store.new_id("llm"),
            "api_key_encrypted": encrypt_secret(payload.api_key),
            "status": "untested",
            "created_at": now,
            "updated_at": now,
        }
    )
    return {"data": public_profile(store.create_item("llm_profiles", profile))}


@router.get("/{profile_id}")
def get_profile(profile_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    profile = store.get_item("llm_profiles", profile_id)
    if not profile:
        raise api_error(404, "not_found", "LLM profile not found")
    return {"data": public_profile(profile)}


@router.patch("/{profile_id}")
def update_profile(profile_id: str, payload: LLMProfileUpdate, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    patch = payload.model_dump(exclude_unset=True)
    if "api_key" in patch:
        patch["api_key_encrypted"] = encrypt_secret(patch.pop("api_key"))
        patch["status"] = "untested"
    updated = store.update_item("llm_profiles", profile_id, patch)
    if not updated:
        raise api_error(404, "not_found", "LLM profile not found")
    return {"data": public_profile(updated)}


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: str, _: dict[str, str] = Depends(require_admin)) -> None:
    in_use = any(project.get("default_llm_profile_id") == profile_id for project in store.list_items("projects"))
    if in_use:
        raise api_error(409, "profile_in_use", "LLM profile is used by at least one project")
    if not store.delete_item("llm_profiles", profile_id):
        raise api_error(404, "not_found", "LLM profile not found")


@router.post("/{profile_id}/test")
def test_profile(profile_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    profile = store.get_item("llm_profiles", profile_id)
    if not profile:
        raise api_error(404, "not_found", "LLM profile not found")
    if not profile.get("base_url") or not profile.get("model"):
        store.update_item("llm_profiles", profile_id, {"status": "invalid"})
        return {
            "data": {
                "success": False,
                "latency_ms": 0,
                "model_returned": None,
                "error_code": "llm_profile_invalid",
                "error_message": "Base URL or model is missing",
                "mode": "mock",
            }
        }
    result = test_llm_profile(profile)
    store.update_item("llm_profiles", profile_id, {"status": "valid" if result["success"] else "invalid"})
    return {"data": result}
