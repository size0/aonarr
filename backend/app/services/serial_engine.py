import threading
import time
from typing import Any

from app.core.config import get_settings
from app.core.security import utc_now
from app.core.store import store
from app.services.llm_client import (
    LLMCallResult,
    LLMClientError,
    chat_completion,
    llm_live_enabled,
    parse_json_object,
)
from app.services.prompt_templates import render_prompt_template

RUNNING_THREADS: set[str] = set()


def emit(run: dict, level: str, event_type: str, message: str, **extra: object) -> dict:
    return store.append_event(
        {
            "serial_run_id": run["id"],
            "project_id": run["project_id"],
            "level": level,
            "event_type": event_type,
            "message": message,
            **extra,
        }
    )


def make_plan(project: dict, run: dict, chapter_number: int) -> dict:
    return {
        "id": store.new_id("plan"),
        "project_id": project["id"],
        "serial_run_id": run["id"],
        "chapter_number": chapter_number,
        "title_hint": f"第 {chapter_number} 章：新的转折",
        "goal": f"推进《{project['title']}》第 {chapter_number} 章的主线目标。",
        "conflict": "主角面临一个必须立即选择的外部阻力。",
        "hook": "章末留下一个能推动下一章的问题。",
        "cast_ids": [],
        "context_dependencies": ["当前为 MVP 模拟规划，后续接入真实 LLM。"],
        "status": "planned",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def text_value(value: Any, fallback: str, limit: int = 500) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()[:limit]
    return fallback


def string_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return cleaned or fallback
    return fallback


def number_value(value: Any, fallback: float, minimum: float = 0, maximum: float = 10) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed))


def bool_value(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "pass", "accepted"}:
            return True
        if lowered in {"false", "no", "fail", "rejected"}:
            return False
    return fallback


def bible_context(bible: dict | None) -> str:
    if not bible:
        return "No story bible has been saved."
    cast = [
        {
            "id": member.get("id"),
            "name": member.get("name"),
            "role": member.get("role"),
            "motivation": member.get("motivation"),
            "voice_hint": member.get("voice_hint"),
        }
        for member in bible.get("cast_members", [])[:12]
    ]
    plot_lines = [
        {
            "name": line.get("name"),
            "goal": line.get("goal"),
            "stakes": line.get("stakes"),
            "current_state": line.get("current_state"),
        }
        for line in bible.get("plot_lines", [])[:8]
    ]
    return "\n".join(
        [
            f"Premise: {bible.get('premise', '')}",
            f"World: {bible.get('world_summary', '')}",
            f"Tone: {bible.get('tone_profile', '')}",
            f"Cast: {cast}",
            f"Plot lines: {plot_lines}",
            f"Limits: {bible.get('content_limits', [])}",
            f"Rules: {bible.get('constraint_rules', [])}",
        ]
    )


def project_prompt_variables(project: dict, bible: dict | None) -> dict[str, Any]:
    return {
        "project_title": project["title"],
        "genre": project["genre"],
        "style_goal": project["style_goal"],
        "target_words_per_chapter": project["target_words_per_chapter"],
        "bible_context": bible_context(bible),
    }


def make_live_plan(
    project: dict, run: dict, profile: dict, chapter_number: int
) -> tuple[dict, LLMCallResult]:
    bible = store.get_bible(project["id"])
    prompt = render_prompt_template(
        "serial_plan",
        {
            **project_prompt_variables(project, bible),
            "chapter_number": chapter_number,
        },
    )
    result = chat_completion(
        profile,
        prompt["messages"],
        temperature=prompt["temperature"],
        max_tokens=prompt["max_tokens"],
    )
    payload = parse_json_object(result.text)
    plan = {
        "id": store.new_id("plan"),
        "project_id": project["id"],
        "serial_run_id": run["id"],
        "chapter_number": chapter_number,
        "title_hint": text_value(payload.get("title_hint"), f"第 {chapter_number} 章：新的转折", 120),
        "goal": text_value(payload.get("goal"), f"推进《{project['title']}》第 {chapter_number} 章。"),
        "conflict": text_value(payload.get("conflict"), "主角面临一个必须立即选择的阻力。"),
        "hook": text_value(payload.get("hook"), "章末留下一个推动下一章的问题。"),
        "cast_ids": string_list(payload.get("cast_ids"), []),
        "context_dependencies": string_list(payload.get("context_dependencies"), ["Live LLM generated plan."]),
        "status": "planned",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    return plan, result


def make_draft(project: dict, plan: dict, version: int) -> dict:
    title = plan["title_hint"]
    body = "\n\n".join(
        [
            f"{title}",
            f"这是《{project['title']}》的第 {plan['chapter_number']} 章 MVP 示例正文。",
            "系统已经根据章节计划生成了一个可替换的草稿，用于验证自动连载、版本、质检、成本统计与导出链路。",
            f"本章目标：{plan['goal']}",
            f"本章冲突：{plan['conflict']}",
            f"章末钩子：{plan['hook']}",
            "后续 Phase 会把这里替换为真实 LLM 生成结果。",
        ]
    )
    return {
        "id": store.new_id("draft"),
        "project_id": project["id"],
        "chapter_plan_id": plan["id"],
        "serial_run_id": plan["serial_run_id"],
        "chapter_number": plan["chapter_number"],
        "title": title,
        "body": body,
        "word_count": len(body),
        "version": version,
        "status": "accepted",
        "quality_score": 7.5,
        "review_summary": "MVP deterministic draft accepted by basic quality gate.",
        "created_by": "system",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def make_live_draft(
    project: dict, plan: dict, profile: dict, version: int
) -> tuple[dict, LLMCallResult]:
    bible = store.get_bible(project["id"])
    prompt = render_prompt_template(
        "serial_draft",
        {
            **project_prompt_variables(project, bible),
            "chapter_title_hint": plan["title_hint"],
            "chapter_goal": plan["goal"],
            "chapter_conflict": plan["conflict"],
            "chapter_hook": plan["hook"],
        },
    )
    result = chat_completion(
        profile,
        prompt["messages"],
        temperature=prompt["temperature"],
        max_tokens=prompt["max_tokens"],
    )
    body = result.text.strip()
    draft = {
        "id": store.new_id("draft"),
        "project_id": project["id"],
        "chapter_plan_id": plan["id"],
        "serial_run_id": plan["serial_run_id"],
        "chapter_number": plan["chapter_number"],
        "title": plan["title_hint"],
        "body": body,
        "word_count": len(body),
        "version": version,
        "status": "draft",
        "quality_score": None,
        "review_summary": "Awaiting live LLM review.",
        "created_by": "llm",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    return draft, result


def make_live_revision_draft(
    project: dict, plan: dict, previous_draft: dict, profile: dict, version: int
) -> tuple[dict, LLMCallResult]:
    bible = store.get_bible(project["id"])
    prompt = render_prompt_template(
        "serial_revision",
        {
            **project_prompt_variables(project, bible),
            "chapter_title_hint": plan["title_hint"],
            "chapter_goal": plan["goal"],
            "chapter_conflict": plan["conflict"],
            "chapter_hook": plan["hook"],
            "review_summary": previous_draft.get("review_summary") or "No review summary.",
            "previous_draft_body": previous_draft["body"][:12000],
        },
    )
    result = chat_completion(
        profile,
        prompt["messages"],
        temperature=prompt["temperature"],
        max_tokens=prompt["max_tokens"],
    )
    body = result.text.strip()
    draft = {
        "id": store.new_id("draft"),
        "project_id": project["id"],
        "chapter_plan_id": plan["id"],
        "serial_run_id": plan["serial_run_id"],
        "chapter_number": plan["chapter_number"],
        "title": plan["title_hint"],
        "body": body,
        "word_count": len(body),
        "version": version,
        "status": "draft",
        "quality_score": None,
        "review_summary": f"Revision v{version} awaiting live LLM review.",
        "created_by": "llm_revision",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    return draft, result


def make_live_review(project: dict, plan: dict, draft: dict, profile: dict) -> tuple[dict, LLMCallResult]:
    prompt = render_prompt_template(
        "serial_review",
        {
            "project_title": project["title"],
            "genre": project["genre"],
            "style_goal": project["style_goal"],
            "chapter_title": draft["title"],
            "chapter_goal": plan["goal"],
            "chapter_conflict": plan["conflict"],
            "chapter_hook": plan["hook"],
            "draft_body": draft["body"][:12000],
        },
    )
    result = chat_completion(
        profile,
        prompt["messages"],
        temperature=prompt["temperature"],
        max_tokens=prompt["max_tokens"],
    )
    payload = parse_json_object(result.text)
    score = number_value(payload.get("quality_score"), 7.0)
    accepted = bool_value(payload.get("accepted"), score >= 7)
    revision_notes = string_list(payload.get("revision_notes"), [])
    summary = text_value(payload.get("summary"), "Live LLM review completed.", 700)
    if revision_notes:
        summary = f"{summary} Revision notes: {'; '.join(revision_notes[:5])}"
    return {
        "status": "accepted" if accepted else "needs_revision",
        "quality_score": round(score, 2),
        "review_summary": summary,
    }, result


def pause_run_for_llm_error(run_id: str, run: dict, exc: LLMClientError, cost: float) -> None:
    store.update_item(
        "runs",
        run_id,
        {
            "status": "paused",
            "failure_code": exc.code,
            "failure_message": exc.message,
            "estimated_cost": round(cost, 4),
        },
    )
    emit(run, "error", "run_paused", "Run paused because the LLM call failed", step="llm")


def should_stop(run_id: str) -> bool:
    run = store.get_item("runs", run_id)
    return not run or run["status"] in {"paused", "cancelled", "failed", "succeeded"}


def run_serial_engine(run_id: str) -> None:
    if run_id in RUNNING_THREADS:
        return
    RUNNING_THREADS.add(run_id)
    try:
        run = store.get_item("runs", run_id)
        if not run:
            return
        project = store.get_item("projects", run["project_id"])
        if not project:
            return
        profile = store.get_item("llm_profiles", run["llm_profile_id"])
        use_live_llm = llm_live_enabled()

        store.update_item("runs", run_id, {"status": "planning", "started_at": utc_now()})
        run = store.get_item("runs", run_id)
        emit(run, "info", "run_started", "Serial run started")
        time.sleep(0.4)

        start = run["start_chapter_number"]
        end = start + run["target_chapter_count"]
        cost = float(run.get("estimated_cost") or 0)
        completed = int(run.get("completed_chapter_count") or 0)

        for chapter_number in range(start + completed, end):
            if should_stop(run_id):
                return

            run = store.get_item("runs", run_id)
            store.update_item("runs", run_id, {"status": "planning"})
            emit(run, "info", "planning_started", f"Planning chapter {chapter_number}", step="planning", chapter_number=chapter_number)
            time.sleep(0.5)
            if use_live_llm and profile:
                try:
                    plan, plan_result = make_live_plan(project, run, profile, chapter_number)
                    cost += plan_result.estimated_cost
                    plan_token_input = plan_result.token_input
                    plan_token_output = plan_result.token_output
                except LLMClientError as exc:
                    pause_run_for_llm_error(run_id, run, exc, cost)
                    return
            else:
                plan = make_plan(project, run, chapter_number)
                plan_token_input = 0
                plan_token_output = 0
            store.create_item("plans", plan)
            emit(
                run,
                "info",
                "planning_completed",
                f"Chapter {chapter_number} plan created",
                step="planning",
                chapter_number=chapter_number,
                token_input=plan_token_input,
                token_output=plan_token_output,
                estimated_cost=round(cost, 4),
            )

            if run["mode"] == "plan_only":
                completed += 1
                store.update_item(
                    "runs",
                    run_id,
                    {
                        "completed_chapter_count": completed,
                        "estimated_cost": round(cost, 4),
                    },
                )
                continue

            if should_stop(run_id):
                return
            store.update_item("runs", run_id, {"status": "drafting"})
            run = store.get_item("runs", run_id)
            emit(run, "info", "chapter_draft_started", f"Drafting chapter {chapter_number}", step="drafting", chapter_number=chapter_number)
            time.sleep(0.7)
            version = 1 + len([
                draft
                for draft in store.list_items("drafts")
                if draft["project_id"] == project["id"] and draft["chapter_number"] == chapter_number
            ])
            if use_live_llm and profile:
                try:
                    draft, draft_result = make_live_draft(project, plan, profile, version)
                    cost += draft_result.estimated_cost
                    draft_token_input = draft_result.token_input
                    draft_token_output = draft_result.token_output
                except LLMClientError as exc:
                    pause_run_for_llm_error(run_id, run, exc, cost)
                    return
            else:
                draft = make_draft(project, plan, version)
                cost += 0.03
                draft_token_input = 1200
                draft_token_output = 900
            draft = store.create_item("drafts", draft)
            emit(
                run,
                "info",
                "chapter_draft_completed",
                f"Chapter {chapter_number} draft completed",
                step="drafting",
                chapter_number=chapter_number,
                token_input=draft_token_input,
                token_output=draft_token_output,
                estimated_cost=round(cost, 4),
            )

            if run.get("cost_limit") is not None and cost >= float(run["cost_limit"]):
                store.update_item(
                    "runs",
                    run_id,
                    {
                        "status": "paused",
                        "failure_code": "cost_limit_exceeded",
                        "failure_message": "Run cost limit exceeded",
                        "estimated_cost": round(cost, 4),
                    },
                )
                emit(run, "warn", "run_paused", "Run paused because cost limit was exceeded", step="cost_guard")
                return

            if should_stop(run_id):
                return
            store.update_item("runs", run_id, {"status": "reviewing", "estimated_cost": round(cost, 4)})
            run = store.get_item("runs", run_id)
            emit(run, "info", "chapter_review_started", f"Reviewing chapter {chapter_number}", step="reviewing", chapter_number=chapter_number)
            time.sleep(0.4)
            revision_attempt = 0
            while True:
                if use_live_llm and profile:
                    try:
                        review_patch, review_result = make_live_review(project, plan, draft, profile)
                        cost += review_result.estimated_cost
                        draft = store.update_item("drafts", draft["id"], review_patch) or draft
                        review_token_input = review_result.token_input
                        review_token_output = review_result.token_output
                    except LLMClientError as exc:
                        pause_run_for_llm_error(run_id, run, exc, cost)
                        return
                else:
                    review_token_input = 0
                    review_token_output = 0
                review_passed = draft.get("status") == "accepted"
                emit(
                    run,
                    "info" if review_passed else "warn",
                    "chapter_review_passed" if review_passed else "chapter_review_needs_revision",
                    f"Chapter {chapter_number} {'passed quality gate' if review_passed else 'needs revision'}",
                    step="reviewing",
                    chapter_number=chapter_number,
                    token_input=review_token_input,
                    token_output=review_token_output,
                    quality_score=draft.get("quality_score"),
                    estimated_cost=round(cost, 4),
                    revision_attempt=revision_attempt,
                )
                if review_passed or not use_live_llm or not profile:
                    break
                if revision_attempt >= max(0, get_settings().revision_max_attempts):
                    break
                if run.get("cost_limit") is not None and cost >= float(run["cost_limit"]):
                    break
                if should_stop(run_id):
                    return

                revision_attempt += 1
                next_version = 1 + len([
                    item
                    for item in store.list_items("drafts")
                    if item["project_id"] == project["id"] and item["chapter_number"] == chapter_number
                ])
                store.update_item("runs", run_id, {"status": "drafting", "estimated_cost": round(cost, 4)})
                run = store.get_item("runs", run_id)
                emit(
                    run,
                    "info",
                    "chapter_revision_started",
                    f"Revising chapter {chapter_number}, attempt {revision_attempt}",
                    step="revision",
                    chapter_number=chapter_number,
                    revision_attempt=revision_attempt,
                )
                try:
                    draft, revision_result = make_live_revision_draft(project, plan, draft, profile, next_version)
                    cost += revision_result.estimated_cost
                    draft = store.create_item("drafts", draft)
                except LLMClientError as exc:
                    pause_run_for_llm_error(run_id, run, exc, cost)
                    return
                emit(
                    run,
                    "info",
                    "chapter_revision_completed",
                    f"Chapter {chapter_number} revision {revision_attempt} completed",
                    step="revision",
                    chapter_number=chapter_number,
                    token_input=revision_result.token_input,
                    token_output=revision_result.token_output,
                    estimated_cost=round(cost, 4),
                    revision_attempt=revision_attempt,
                )
                if run.get("cost_limit") is not None and cost >= float(run["cost_limit"]):
                    break
                store.update_item("runs", run_id, {"status": "reviewing", "estimated_cost": round(cost, 4)})
                run = store.get_item("runs", run_id)
                emit(
                    run,
                    "info",
                    "chapter_review_started",
                    f"Reviewing chapter {chapter_number} revision {revision_attempt}",
                    step="reviewing",
                    chapter_number=chapter_number,
                    revision_attempt=revision_attempt,
                )
                time.sleep(0.2)

            if run.get("cost_limit") is not None and cost >= float(run["cost_limit"]):
                store.update_item(
                    "runs",
                    run_id,
                    {
                        "status": "paused",
                        "failure_code": "cost_limit_exceeded",
                        "failure_message": "Run cost limit exceeded",
                        "estimated_cost": round(cost, 4),
                    },
                )
                emit(run, "warn", "run_paused", "Run paused because cost limit was exceeded", step="cost_guard")
                return

            if not review_passed:
                store.update_item(
                    "runs",
                    run_id,
                    {
                        "status": "paused",
                        "failure_code": "quality_gate_needs_revision",
                        "failure_message": draft.get("review_summary") or "Chapter draft needs revision",
                        "estimated_cost": round(cost, 4),
                    },
                )
                emit(run, "warn", "run_paused", "Run paused because chapter review requested revision", step="reviewing")
                return

            completed += 1
            store.update_item(
                "runs",
                run_id,
                {
                    "completed_chapter_count": completed,
                    "estimated_cost": round(cost, 4),
                },
            )

        run = store.get_item("runs", run_id)
        store.update_item("runs", run_id, {"status": "succeeded", "finished_at": utc_now()})
        emit(run, "info", "run_succeeded", "Serial run completed")
    except Exception as exc:
        run = store.get_item("runs", run_id)
        if run:
            store.update_item(
                "runs",
                run_id,
                {"status": "failed", "failure_code": "internal_error", "failure_message": str(exc), "finished_at": utc_now()},
            )
            emit(run, "error", "run_failed", "Serial run failed")
    finally:
        RUNNING_THREADS.discard(run_id)


def start_run_worker(run_id: str) -> None:
    thread = threading.Thread(target=run_serial_engine, args=(run_id,), daemon=True)
    thread.start()
