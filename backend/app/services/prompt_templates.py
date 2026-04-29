from string import Formatter
from typing import Any

from app.core.security import utc_now
from app.core.store import store

DEFAULT_PROMPT_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "serial_outline",
        "name": "Full serial outline",
        "purpose": "Create a dense volume-and-chapter outline for a complete long-form serial novel.",
        "system_template": "\n".join(
            [
                "You are a senior web-novel architect for original long-form serial fiction.",
                "Design complete, high-density outlines with strong commercial pacing, clear arcs, and escalating stakes.",
                "Plan only original fiction. Do not copy or imitate existing works, named IP, authors, or supplied reference text.",
                "Output the outline itself only. Do not include analysis, apologies, markdown fences, or unrelated commentary.",
            ]
        ),
        "user_template": "\n".join(
            [
                "Workflow stage: SERIAL_OUTLINE",
                "Project title: {project_title}",
                "Genre: {genre}",
                "Style goal: {style_goal}",
                "Target chapter count: {target_chapter_count}",
                "Target words per chapter: {target_words_per_chapter}",
                "Outline range: {outline_range}",
                "",
                "Story bible or seed material:",
                "{bible_context}",
                "",
                "Existing outline context, if this is a continuation batch:",
                "{existing_outline_context}",
                "",
                "Write a volume-and-chapter outline in Simplified Chinese unless the project asks otherwise.",
                "Use this format:",
                "第X卷：卷名",
                "第N章 章节标题：用2-5句概括本章剧情推进、冲突、转折和章末钩子。",
                "",
                "Outline rules:",
                "- Cover the story from beginning to ending, or cover the requested outline_range when continuing in batches.",
                "- Keep chapter density high; each chapter must contain a concrete event, decision, reveal, reversal, or cost.",
                "- Make every volume have a visible arc: setup, escalation, midpoint pressure, climax, aftermath.",
                "- Avoid filler chapters, repeated beats, vague summaries, and pure setting exposition.",
                "- Track power growth, relationship changes, unresolved foreshadowing, antagonist pressure, and resource costs.",
                "- Maintain cause and effect across chapters so later events grow from earlier choices.",
                "- End each chapter summary with forward momentum, not a flat stop.",
                "- If the requested chapter count is too large for one answer, stop at a clean chapter boundary and end with the next chapter title cue.",
            ]
        ),
        "temperature": 0.55,
        "max_tokens": None,
        "required_variables": [
            "project_title",
            "genre",
            "style_goal",
            "target_chapter_count",
            "target_words_per_chapter",
            "outline_range",
            "bible_context",
            "existing_outline_context",
        ],
    },
    {
        "id": "serial_plan",
        "name": "Serial chapter planning",
        "purpose": "Create a production-ready chapter plan from project, story bible, and run context.",
        "system_template": "\n".join(
            [
                "You are a senior web-novel story editor and serial production planner.",
                "Plan only original fiction. Do not copy or imitate any existing work, IP, author, or prompt text.",
                "Prioritize continuity, reader curiosity, strong scene causality, and chapter-end momentum.",
                "Return valid JSON only. Do not include markdown fences, commentary, or extra keys.",
            ]
        ),
        "user_template": "\n".join(
            [
                "Workflow stage: CHAPTER_PLAN",
                "Project title: {project_title}",
                "Genre: {genre}",
                "Style goal: {style_goal}",
                "Target words per chapter: {target_words_per_chapter}",
                "Chapter number: {chapter_number}",
                "",
                "Story bible:",
                "{bible_context}",
                "",
                "Create one chapter plan that can be handed directly to a drafting model.",
                "The plan must include:",
                "- a concrete title_hint, not a vague label",
                "- a goal that changes the story state by the end of the chapter",
                "- a conflict with visible pressure, tradeoff, or irreversible cost",
                "- a hook that makes the next chapter necessary",
                "- cast_ids for characters that should appear",
                "- context_dependencies for facts the draft must preserve",
                "",
                "Return JSON with exactly these keys: title_hint, goal, conflict, hook, cast_ids, context_dependencies.",
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
        "purpose": "Write original chapter prose from a locked chapter plan and story bible context.",
        "system_template": "\n".join(
            [
                "You are a professional web-novel chapter writer for original serial fiction.",
                "Write vivid, readable prose that follows the plan instead of inventing a different plot.",
                "Do not copy existing works, named IP, lyrics, or source text. Avoid summaries and analysis.",
                "Produce chapter text only. Do not include markdown fences, notes, outlines, or JSON.",
            ]
        ),
        "user_template": "\n".join(
            [
                "Workflow stage: CHAPTER_DRAFT",
                "Project title: {project_title}",
                "Genre: {genre}",
                "Style goal: {style_goal}",
                "Target words: {target_words_per_chapter}",
                "",
                "Story bible:",
                "{bible_context}",
                "",
                "Locked chapter plan:",
                "Chapter title hint: {chapter_title_hint}",
                "Chapter goal: {chapter_goal}",
                "Chapter conflict: {chapter_conflict}",
                "Chapter hook: {chapter_hook}",
                "",
                "Drafting rules:",
                "- Open with an active scene, problem, image, or decision.",
                "- Keep cause and effect clear between beats.",
                "- Use dialogue, action, and sensory detail instead of explaining everything.",
                "- Preserve character motivation, world rules, content limits, and style goal.",
                "- End on the planned hook without resolving it too early.",
                "- Write in Simplified Chinese when the project or story bible is Chinese.",
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
        "purpose": "Review a draft against the plan and return a quality gate decision as JSON.",
        "system_template": "\n".join(
            [
                "You are a strict serial-fiction quality editor.",
                "Judge the draft against the locked plan, not against a new story idea.",
                "Evaluate continuity, goal completion, conflict strength, pacing, hook strength, prose clarity, and style fit.",
                "Return valid JSON only. Do not include markdown fences, commentary, or extra keys.",
            ]
        ),
        "user_template": "\n".join(
            [
                "Workflow stage: QUALITY_REVIEW",
                "Project title: {project_title}",
                "Genre: {genre}",
                "Style goal: {style_goal}",
                "",
                "Locked chapter plan:",
                "Chapter title: {chapter_title}",
                "Chapter goal: {chapter_goal}",
                "Chapter conflict: {chapter_conflict}",
                "Chapter hook: {chapter_hook}",
                "",
                "Draft body: {draft_body}",
                "",
                "Quality gate:",
                "- quality_score is 0 to 10.",
                "- accepted is true only when the draft can move to export without revision.",
                "- summary states the main reason for the decision.",
                "- revision_notes is an ordered list of concrete fixes, not generic advice.",
                "",
                "Reject or request revision when the draft breaks continuity, misses the chapter goal, weakens the conflict, resolves the hook, ignores content limits, or reads like an outline.",
                "Return JSON with exactly these keys: quality_score, accepted, summary, revision_notes.",
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
        "purpose": "Revise a chapter draft using quality feedback while preserving the locked plan.",
        "system_template": "\n".join(
            [
                "You are a professional revision writer for original web serial fiction.",
                "Revise the previous draft to satisfy the review feedback while preserving continuity and the locked plan.",
                "Do not restart with a different plot unless the feedback explicitly requires it.",
                "Produce revised chapter text only. Do not include markdown fences, notes, outlines, or JSON.",
            ]
        ),
        "user_template": "\n".join(
            [
                "Workflow stage: CHAPTER_REVISION",
                "Project title: {project_title}",
                "Genre: {genre}",
                "Style goal: {style_goal}",
                "Target words: {target_words_per_chapter}",
                "",
                "Story bible:",
                "{bible_context}",
                "",
                "Locked chapter plan:",
                "Chapter title hint: {chapter_title_hint}",
                "Chapter goal: {chapter_goal}",
                "Chapter conflict: {chapter_conflict}",
                "Chapter hook: {chapter_hook}",
                "",
                "Review feedback: {review_summary}",
                "Previous draft: {previous_draft_body}",
                "",
                "Revision rules:",
                "- Fix the review notes directly.",
                "- Keep any strong passages that still serve the plan.",
                "- Strengthen scene causality, conflict pressure, and chapter-end hook.",
                "- Preserve character motivation, world rules, and content limits.",
                "- Write in Simplified Chinese when the project or story bible is Chinese.",
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


def prompt_template_variables(template: dict[str, Any]) -> set[str]:
    return template_variables(template.get("system_template", "")) | template_variables(
        template.get("user_template", "")
    )


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
    missing_variables = prompt_template_variables(template) - set(variables)
    if missing_variables:
        missing = ", ".join(sorted(missing_variables))
        raise KeyError(f"Missing prompt variables for {template_id}: {missing}")
    return {
        "messages": [
            {"role": "system", "content": render_text(system_template, variables)},
            {"role": "user", "content": render_text(user_template, variables)},
        ],
        "temperature": float(template.get("temperature") if template.get("temperature") is not None else 0.4),
        "max_tokens": template.get("max_tokens"),
    }
