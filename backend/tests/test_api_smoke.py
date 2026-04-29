import os
import tempfile

from fastapi.testclient import TestClient

_tmp_data = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _tmp_data.name
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "change-me"

from app.main import app

client = TestClient(app)


def auth_headers() -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "change-me"})
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
    assert {template["id"] for template in templates} >= {"serial_plan", "serial_draft", "serial_review", "serial_revision"}

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

    readiness_response = client.get(f"/api/v1/projects/{project['id']}/bible/readiness", headers=headers)
    assert readiness_response.status_code == 200
    assert readiness_response.json()["data"]["ready"] is True

    test_profile_response = client.post(f"/api/v1/llm-profiles/{profile['id']}/test", headers=headers)
    assert test_profile_response.status_code == 200
    assert test_profile_response.json()["data"]["success"] is True
    assert test_profile_response.json()["data"]["mode"] == "mock"
