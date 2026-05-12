"""后端 API 冒烟测试"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.connection import Base, engine


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


# ── Health ────────────────────────────────────────────────────────

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_root():
    resp = client.get("/api/v1")
    assert resp.status_code == 200
    assert "endpoints" in resp.json()


# ── Novels CRUD ───────────────────────────────────────────────────

def test_create_novel():
    resp = client.post("/api/v1/novels/", json={
        "title": "测试小说",
        "genre": "玄幻",
        "tags": ["热血", "升级"],
        "synopsis": "一个测试简介",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试小说"
    assert data["genre"] == "玄幻"
    assert data["tags"] == ["热血", "升级"]
    return data["id"]


def test_list_novels():
    client.post("/api/v1/novels/", json={"title": "小说A"})
    client.post("/api/v1/novels/", json={"title": "小说B"})
    resp = client.get("/api/v1/novels/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_novel():
    create_resp = client.post("/api/v1/novels/", json={"title": "查询测试"})
    novel_id = create_resp.json()["id"]
    resp = client.get(f"/api/v1/novels/{novel_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "查询测试"


def test_update_novel():
    create_resp = client.post("/api/v1/novels/", json={"title": "更新前"})
    novel_id = create_resp.json()["id"]
    resp = client.patch(f"/api/v1/novels/{novel_id}", json={"title": "更新后", "status": "writing"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "更新后"
    assert resp.json()["status"] == "writing"


def test_delete_novel():
    create_resp = client.post("/api/v1/novels/", json={"title": "待删除"})
    novel_id = create_resp.json()["id"]
    resp = client.delete(f"/api/v1/novels/{novel_id}")
    assert resp.status_code == 204
    resp = client.get(f"/api/v1/novels/{novel_id}")
    assert resp.status_code == 404


def test_get_novel_not_found():
    resp = client.get("/api/v1/novels/nonexistent")
    assert resp.status_code == 404


# ── Chapters ──────────────────────────────────────────────────────

def test_create_chapter():
    novel = client.post("/api/v1/novels/", json={"title": "章节测试"}).json()
    resp = client.post(f"/api/v1/novels/{novel['id']}/chapters", json={
        "number": 1,
        "title": "第一章",
        "content": "这是第一章的内容" * 100,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["number"] == 1
    assert data["title"] == "第一章"
    assert data["word_count"] > 0


def test_list_chapters():
    novel = client.post("/api/v1/novels/", json={"title": "章节列表"}).json()
    client.post(f"/api/v1/novels/{novel['id']}/chapters", json={"number": 1, "title": "第1章"})
    client.post(f"/api/v1/novels/{novel['id']}/chapters", json={"number": 2, "title": "第2章"})
    resp = client.get(f"/api/v1/novels/{novel['id']}/chapters")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── Characters ────────────────────────────────────────────────────

def test_create_character():
    novel = client.post("/api/v1/novels/", json={"title": "人物测试"}).json()
    resp = client.post(f"/api/v1/novels/{novel['id']}/characters", json={
        "name": "主角",
        "role": "protagonist",
        "description": "天赋异禀的少年",
        "traits": ["聪明", "坚毅"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "主角"
    assert data["role"] == "protagonist"


def test_list_characters():
    novel = client.post("/api/v1/novels/", json={"title": "人物列表"}).json()
    client.post(f"/api/v1/novels/{novel['id']}/characters", json={"name": "角色A"})
    client.post(f"/api/v1/novels/{novel['id']}/characters", json={"name": "角色B"})
    resp = client.get(f"/api/v1/novels/{novel['id']}/characters")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── Analysis ──────────────────────────────────────────────────────

def test_list_analysis_jobs():
    resp = client.get("/api/v1/analysis/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Publishing ────────────────────────────────────────────────────

def test_list_publish_jobs():
    resp = client.get("/api/v1/publishing/jobs")
    assert resp.status_code == 200


def test_list_platforms():
    resp = client.get("/api/v1/publishing/platforms")
    assert resp.status_code == 200
    platforms = resp.json()
    assert any(p["id"] == "fanqie" for p in platforms)


# ── Learning ──────────────────────────────────────────────────────

def test_list_knowledge():
    resp = client.get("/api/v1/learning/knowledge")
    assert resp.status_code == 200


def test_list_hot_novels():
    resp = client.get("/api/v1/learning/hot-novels")
    assert resp.status_code == 200


# ── LLM Settings ─────────────────────────────────────────────────

def test_get_model_config():
    resp = client.get("/api/v1/settings/llm/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_preset" in data
    assert "profiles" in data
    assert "bindings" in data
    assert "available_stages" in data
    assert len(data["available_stages"]) == 11


def test_create_and_bind_profile():
    # 创建 profile
    resp = client.post("/api/v1/settings/llm/profiles", json={
        "name": "测试模型",
        "protocol": "openai",
        "base_url": "http://localhost:8080/v1",
        "api_key": "sk-test-1234567890abcdef",
        "model": "gpt-4",
    })
    assert resp.status_code == 201
    profile = resp.json()
    assert profile["name"] == "测试模型"
    assert "****" in profile["api_key_masked"]

    # 绑定到阶段
    resp = client.post("/api/v1/settings/llm/bind-stage", json={
        "stage": "chapter_writing",
        "profile_id": profile["id"],
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 验证绑定生效
    config = client.get("/api/v1/settings/llm/config").json()
    assert config["active_preset"] == "custom"
    bindings = {b["stage"]: b for b in config["bindings"]}
    assert "chapter_writing" in bindings
    assert bindings["chapter_writing"]["profile_id"] == profile["id"]


def test_invalid_stage_binding():
    resp = client.post("/api/v1/settings/llm/bind-stage", json={
        "stage": "invalid_stage",
        "profile_id": "some-id",
    })
    assert resp.status_code == 400
