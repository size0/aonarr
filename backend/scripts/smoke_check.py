import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory() as tmpdir:
    os.environ["DATA_DIR"] = tmpdir

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    health = client.get("/api/v1/health")
    assert health.status_code == 200, health.text
    assert health.json()["data"]["storage"]["backend"] == "json"

    unauthorized = client.get("/api/v1/projects")
    assert unauthorized.status_code == 401, unauthorized.text

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "change-me"})
    assert login.status_code == 200, login.text
    token = login.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    settings_response = client.get("/api/v1/runtime/settings", headers=headers)
    assert settings_response.status_code == 200, settings_response.text
    assert settings_response.json()["data"]["llm_mode"] == "mock"
    assert settings_response.json()["data"]["revision_max_attempts"] == 1
    assert settings_response.json()["data"]["storage_backend"] == "json"

    templates_response = client.get("/api/v1/prompt-templates", headers=headers)
    assert templates_response.status_code == 200, templates_response.text
    templates = templates_response.json()["data"]
    assert {template["id"] for template in templates} >= {"serial_plan", "serial_draft", "serial_review", "serial_revision"}

    profile_response = client.post(
        "/api/v1/llm-profiles",
        headers=headers,
        json={
            "name": "Smoke Profile",
            "provider_type": "openai_compatible",
            "base_url": "http://localhost:11434/v1",
            "model": "demo-model",
            "api_key": "secret-key",
        },
    )
    assert profile_response.status_code == 201, profile_response.text
    profile = profile_response.json()["data"]
    assert "api_key" not in profile

    test_profile_response = client.post(f"/api/v1/llm-profiles/{profile['id']}/test", headers=headers)
    assert test_profile_response.status_code == 200, test_profile_response.text
    assert test_profile_response.json()["data"]["success"] is True
    assert test_profile_response.json()["data"]["mode"] == "mock"

    project_response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "title": "Smoke Novel",
            "genre": "玄幻",
            "target_chapter_count": 30,
            "target_words_per_chapter": 2000,
            "style_goal": "Fast paced",
            "default_llm_profile_id": profile["id"],
        },
    )
    assert project_response.status_code == 201, project_response.text
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
    assert bible_response.status_code == 200, bible_response.text

    readiness = client.get(f"/api/v1/projects/{project['id']}/bible/readiness", headers=headers)
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["data"]["ready"] is True

    run_response = client.post(
        f"/api/v1/projects/{project['id']}/runs",
        headers=headers,
        json={"mode": "full_auto", "start_chapter_number": 1, "target_chapter_count": 1, "cost_limit": 1},
    )
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()["data"]

    events = client.get(f"/api/v1/projects/{project['id']}/runs/{run['id']}/events", headers=headers)
    assert events.status_code == 200, events.text

print("smoke_check_ok")
