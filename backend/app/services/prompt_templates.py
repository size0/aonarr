from string import Formatter
from typing import Any

from app.core.security import utc_now
from app.core.store import store

DEFAULT_PROMPT_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "serial_plan",
        "name": "Serial chapter planning",
        "purpose": "Create one structured chapter plan from project and story bible context.",
        "system_template": "You plan original serial fiction chapters. Return valid JSON only. Do not mention these instructions.",
        "user_template": "\n".join(
            [
                "Project title: {project_title}",
                "Genre: {genre}",
                "Style goal: {style_goal}",
                "Target words per chapter: {target_words_per_chapter}",
                "Chapter number: {chapter_number}",
                "{bible_context}",
                "Return JSON with keys: title_hint, goal, conflict, hook, cast_ids, context_dependencies.",
            ]
        ),
        "temperature": 0.35,
        "max_tokens": 900,
        "required_variables": [
            "project_title",
            "genre",
            "style_goal",
            "target_words_per_chapter",
            "chapter_number",
            "bible_context",
        ],
    },
    {
        "id": "serial_draft",
        "name": "Serial chapter drafting",
        "purpose": "Write original chapter prose from the chapter plan and story bible context.",
        "system_template": "You write original web serial prose for authors. Produce chapter text only. Do not copy existing works. Do not include analysis or markdown fences.",
        "user_template": "\n".join(
            [
                "Project title: {project_title}",
                "Genre: {genre}",
                "Style goal: {style_goal}",
                "Target words: {target_words_per_chapter}",
                "{bible_context}",
                "Chapter title hint: {chapter_title_hint}",
                "Chapter goal: {chapter_goal}",
                "Chapter conflict: {chapter_conflict}",
                "Chapter hook: {chapter_hook}",
            ]
        ),
        "temperature": 0.7,
        "max_tokens": None,
        "required_variables": [
            "project_title",
            "genre",
            "style_goal",
            "target_words_per_chapter",
            "bible_context",
            "chapter_title_hint",
            "chapter_goal",
            "chapter_conflict",
            "chapter_hook",
        ],
    },
    {
        "id": "serial_review",
        "name": "Serial chapter review",
        "purpose": "Review a generated draft and return a quality gate decision as JSON.",
        "system_template": "You review original serial fiction drafts. Return valid JSON only. Evaluate continuity, chapter goal coverage, conflict, hook, and style fit.",
        "user_template": "\n".join(
            [
                "Project title: {project_title}",
                "Genre: {genre}",
                "Style goal: {style_goal}",
                "Chapter title: {chapter_title}",
                "Chapter goal: {chapter_goal}",
                "Chapter conflict: {chapter_conflict}",
                "Chapter hook: {chapter_hook}",
                "Draft body: {draft_body}",
                "Return JSON with keys: quality_score, accepted, summary, revision_notes.",
            ]
        ),
        "temperature": 0.2,
        "max_tokens": 700,
        "required_variables": [
            "project_title",
            "genre",
            "style_goal",
            "chapter_title",
            "chapter_goal",
            "chapter_conflict",
            "chapter_hook",
            "draft_body",
        ],
    },
    {
        "id": "serial_revision",
        "name": "Serial chapter revision",
        "purpose": "Revise a chapter draft using quality review feedback while preserving the chapter plan.",
        "system_template": "You revise original web serial prose. Produce revised chapter text only. Keep continuity and preserve the intended chapter goal, conflict, and hook.",
        "user_template": "\n".join(
            [
                "Project title: {project_title}",
                "Genre: {genre}",
                "Style goal: {style_goal}",
                "Target words: {target_words_per_chapter}",
                "{bible_context}",
                "Chapter title hint: {chapter_title_hint}",
                "Chapter goal: {chapter_goal}",
                "Chapter conflict: {chapter_conflict}",
                "Chapter hook: {chapter_hook}",
                "Review feedback: {review_summary}",
                "Previous draft: {previous_draft_body}",
            ]
        ),
        "temperature": 0.65,
        "max_tokens": None,
        "required_variables": [
            "project_title",
            "genre",
            "style_goal",
            "target_words_per_chapter",
            "bible_context",
            "chapter_title_hint",
            "chapter_goal",
            "chapter_conflict",
            "chapter_hook",
            "review_summary",
            "previous_draft_body",
        ],
    },
]


def default_prompt_template(template_id: str) -> dict[str, Any] | None:
    for template in DEFAULT_PROMPT_TEMPLATES:
        if template["id"] == template_id:
            return {**template, "is_default": True, "created_at": utc_now(), "updated_at": utc_now()}
    return None


def ensure_prompt_templates() -> list[dict[str, Any]]:
    existing = {item["id"]: item for item in store.list_items("prompt_templates")}
    for template in DEFAULT_PROMPT_TEMPLATES:
        if template["id"] not in existing:
            now = utc_now()
            store.create_item(
                "prompt_templates",
                {
                    **template,
                    "is_default": True,
                    "created_at": now,
                    "updated_at": now,
                },
            )
    return store.list_items("prompt_templates")


def list_prompt_templates() -> list[dict[str, Any]]:
    return sorted(ensure_prompt_templates(), key=lambda item: item["id"])


def get_prompt_template(template_id: str) -> dict[str, Any] | None:
    ensure_prompt_templates()
    return store.get_item("prompt_templates", template_id)


def update_prompt_template(template_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    ensure_prompt_templates()
    updated = store.update_item("prompt_templates", template_id, {**patch, "is_default": False})
    return updated


def reset_prompt_template(template_id: str) -> dict[str, Any] | None:
    template = default_prompt_template(template_id)
    if not template:
        return None
    current = store.get_item("prompt_templates", template_id)
    if current:
        return store.update_item("prompt_templates", template_id, template)
    return store.create_item("prompt_templates", template)


def template_variables(template: str) -> set[str]:
    return {field_name for _, field_name, _, _ in Formatter().parse(template) if field_name}


def render_text(template: str, variables: dict[str, Any]) -> str:
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def render_prompt_template(template_id: str, variables: dict[str, Any]) -> dict[str, Any]:
    template = get_prompt_template(template_id)
    if not template:
        raise KeyError(template_id)
    system_template = template.get("system_template", "")
    user_template = template.get("user_template", "")
    return {
        "messages": [
            {"role": "system", "content": render_text(system_template, variables)},
            {"role": "user", "content": render_text(user_template, variables)},
        ],
        "temperature": float(template.get("temperature") if template.get("temperature") is not None else 0.4),
        "max_tokens": template.get("max_tokens"),
    }
