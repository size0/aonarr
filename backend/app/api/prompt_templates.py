from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.errors import api_error
from app.models.schemas import PromptTemplateUpdate
from app.services.prompt_templates import (
    get_prompt_template,
    list_prompt_templates,
    reset_prompt_template,
    update_prompt_template,
)

router = APIRouter(prefix="/prompt-templates", tags=["prompt-templates"])


@router.get("")
def list_templates(_: dict[str, str] = Depends(require_admin)) -> dict[str, list[dict]]:
    return {"data": list_prompt_templates()}


@router.get("/{template_id}")
def get_template(template_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    template = get_prompt_template(template_id)
    if not template:
        raise api_error(404, "not_found", "Prompt template not found")
    return {"data": template}


@router.patch("/{template_id}")
def update_template(
    template_id: str,
    payload: PromptTemplateUpdate,
    _: dict[str, str] = Depends(require_admin),
) -> dict[str, dict]:
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        template = get_prompt_template(template_id)
        if not template:
            raise api_error(404, "not_found", "Prompt template not found")
        return {"data": template}
    updated = update_prompt_template(template_id, patch)
    if not updated:
        raise api_error(404, "not_found", "Prompt template not found")
    return {"data": updated}


@router.post("/{template_id}/reset")
def reset_template(template_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, dict]:
    template = reset_prompt_template(template_id)
    if not template:
        raise api_error(404, "not_found", "Prompt template not found")
    return {"data": template}
