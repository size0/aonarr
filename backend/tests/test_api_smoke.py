import os
import tempfile

from fastapi.testclient import TestClient

_tmp_data = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _tmp_data.name
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "change-me"

from app.api.auth import login_attempts
from app.core.config import get_settings
from app.core.security import new_token, utc_after, utc_now
from app.core.store import store
from app.main import app, create_app
from app.services.prompt_templates import prompt_template_variables

client = TestClient(app)


def auth_headers() -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "change-me"},
    )
    assert response.status_code == 200
    token = response.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_uses_configured_admin_username() -> None:
    response = client.post("/api/v1/auth/login", json={"username": "root", "password": "change-me"})
    assert response.status_code == 401


def test_sse_token_requires_admin_and_returns_short_lived_token() -> None:
    unauthorized = client.post("/api/v1/auth/sse-token")
    assert unauthorized.status_code == 401

    response = client.post("/api/v1/auth/sse-token", headers=auth_headers())
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["token_type"] == "sse"
    assert payload["token"]
    assert payload["expires_at"]


def test_bearer_token_cannot_access_sse_stream() -> None:
    headers = auth_headers()
    bearer_token = headers["Authorization"].removeprefix("Bearer ")
    response = client.get(
        f"/api/v1/projects/proj-test/runs/run-test/events/stream?sse_token={bearer_token}"
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_expired_sse_token_is_rejected() -> None:
    token = new_token()
    store.create_session(token, "admin", utc_after(-1), "sse")
    response = client.get(
        f"/api/v1/projects/proj-test/runs/run-test/events/stream?sse_token={token}"
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_login_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300")
    get_settings.cache_clear()
    login_attempts.clear()
    try:
        for _ in range(2):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "limited", "password": "wrong"},
            )
            assert response.status_code == 401
        limited = client.post(
            "/api/v1/auth/login",
            json={"username": "limited", "password": "wrong"},
        )
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
    finally:
        login_attempts.clear()
        get_settings.cache_clear()


def test_production_rejects_default_credentials(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "change-me")
    monkeypatch.setenv("SECRET_KEY", "dev-secret-change-me")
    get_settings.cache_clear()
    try:
        try:
            create_app()
        except RuntimeError as exc:
            assert "production" in str(exc)
        else:
            raise AssertionError("create_app should reject default production credentials")
    finally:
        get_settings.cache_clear()


def test_health_check() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"
    assert response.json()["data"]["storage"]["backend"] == "json"


def test_auth_required_for_projects() -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_runtime_settings() -> None:
    response = client.get("/api/v1/runtime/settings", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["data"]["llm_mode"] == "mock"
    assert response.json()["data"]["revision_max_attempts"] == 1
    assert response.json()["data"]["storage_backend"] == "json"


def test_prompt_templates() -> None:
    headers = auth_headers()
    response = client.get("/api/v1/prompt-templates", headers=headers)
    assert response.status_code == 200
    templates = response.json()["data"]
    expected_template_ids = {
        "serial_outline",
        "serial_plan",
        "serial_draft",
        "serial_review",
        "serial_revision",
    }
    assert {template["id"] for template in templates} >= expected_template_ids
    template_by_id = {template["id"]: template for template in templates}
    for template_id in expected_template_ids:
        template = template_by_id[template_id]
        assert set(template["required_variables"]) == prompt_template_variables(template)
    assert "Workflow stage: SERIAL_OUTLINE" in template_by_id["serial_outline"]["user_template"]
    assert "第X卷：卷名" in template_by_id["serial_outline"]["user_template"]
    assert "Workflow stage: CHAPTER_PLAN" in template_by_id["serial_plan"]["user_template"]
    assert "context_dependencies" in template_by_id["serial_plan"]["user_template"]
    assert "Quality gate:" in template_by_id["serial_review"]["user_template"]
    assert "Revision rules:" in template_by_id["serial_revision"]["user_template"]

    patch_response = client.patch(
        "/api/v1/prompt-templates/serial_plan",
        headers=headers,
        json={"temperature": 0.4},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["is_default"] is False

    reset_response = client.post("/api/v1/prompt-templates/serial_plan/reset", headers=headers)
    assert reset_response.status_code == 200
    assert reset_response.json()["data"]["is_default"] is True


def test_create_profile_project_and_bible_readiness() -> None:
    headers = auth_headers()

    profile_response = client.post(
        "/api/v1/llm-profiles",
        headers=headers,
        json={
            "name": "Test Profile",
            "provider_type": "openai_compatible",
            "base_url": "http://localhost:11434/v1",
            "model": "demo-model",
            "api_key": "secret-key",
        },
    )
    assert profile_response.status_code == 201
    profile = profile_response.json()["data"]
    assert "api_key" not in profile

    project_response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "title": "Test Novel",
            "genre": "玄幻",
            "target_chapter_count": 30,
            "target_words_per_chapter": 2000,
            "style_goal": "Fast paced",
            "default_llm_profile_id": profile["id"],
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()["data"]

    bible_response = client.put(
        f"/api/v1/projects/{project['id']}/bible",
        headers=headers,
        json={
            "premise": "A clean-room test premise.",
            "world_summary": "A test world.",
            "tone_profile": "Direct.",
            "content_limits": [],
            "cast_members": [
                {
                    "id": "cast-1",
                    "name": "Hero",
                    "role": "protagonist",
                    "motivation": "Win",
                    "voice_hint": "Short sentences",
                    "forbidden_actions": [],
                }
            ],
            "places": [],
            "plot_lines": [
                {
                    "id": "plot-1",
                    "name": "Main plot",
                    "goal": "Finish the arc",
                    "stakes": "Failure",
                    "current_state": "Start",
                }
            ],
            "constraint_rules": [],
        },
    )
    assert bible_response.status_code == 200

    readiness_response = client.get(
        f"/api/v1/projects/{project['id']}/bible/readiness",
        headers=headers,
    )
    assert readiness_response.status_code == 200
    assert readiness_response.json()["data"]["ready"] is True

    test_profile_response = client.post(
        f"/api/v1/llm-profiles/{profile['id']}/test",
        headers=headers,
    )
    assert test_profile_response.status_code == 200
    assert test_profile_response.json()["data"]["success"] is True
    assert test_profile_response.json()["data"]["mode"] == "mock"


def test_export_response_hides_file_ref() -> None:
    headers = auth_headers()
    project_response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "title": "Export Novel",
            "genre": "玄幻",
            "target_chapter_count": 30,
            "target_words_per_chapter": 2000,
            "style_goal": "Fast paced",
            "default_llm_profile_id": None,
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()["data"]
    now = utc_now()
    store.create_item(
        "drafts",
        {
            "id": store.new_id("draft"),
            "project_id": project["id"],
            "chapter_plan_id": "plan-test",
            "serial_run_id": "run-test",
            "chapter_number": 1,
            "title": "第一章",
            "body": "测试正文",
            "word_count": 4,
            "version": 1,
            "status": "accepted",
            "quality_score": 8,
            "review_summary": "ok",
            "created_by": "test",
            "created_at": now,
            "updated_at": now,
        },
    )

    export_response = client.post(
        f"/api/v1/projects/{project['id']}/exports",
        headers=headers,
        json={"format": "markdown"},
    )
    assert export_response.status_code == 202
    export_item = export_response.json()["data"]
    assert "file_ref" not in export_item
    assert export_item["download_url"].endswith(f"/exports/{export_item['id']}/file")

    get_response = client.get(
        f"/api/v1/projects/{project['id']}/exports/{export_item['id']}",
        headers=headers,
    )
    assert get_response.status_code == 200
    get_item = get_response.json()["data"]
    assert "file_ref" not in get_item
    assert get_item["download_url"] == export_item["download_url"]
