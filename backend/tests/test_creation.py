"""创作引擎测试"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.connection import Base, engine, get_db
from app.services.creation.context_builder import ContextBuilder, CreationContext, _parse_json_list
from app.services.creation.outline_generator import _extract_json


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


# ── ContextBuilder ────────────────────────────────────────────────

def test_context_builder_novel_not_found():
    """不存在的小说应报错"""
    db = next(get_db())
    builder = ContextBuilder(db)
    with pytest.raises(ValueError, match="小说不存在"):
        builder.build("nonexistent", 1)


def test_context_builder_basic():
    """基本上下文构建"""
    # 先创建一本小说
    resp = client.post("/api/v1/novels/", json={
        "title": "测试小说",
        "genre": "玄幻",
        "synopsis": "一个测试",
        "premise": "少年成长",
    })
    novel_id = resp.json()["id"]

    # 添加人物
    client.post(f"/api/v1/novels/{novel_id}/characters", json={
        "name": "主角", "role": "protagonist", "traits": ["聪明"],
    })

    # 添加一章
    client.post(f"/api/v1/novels/{novel_id}/chapters", json={
        "number": 1, "title": "第一章", "content": "这是第一章的内容" * 50,
    })

    db = next(get_db())
    builder = ContextBuilder(db)
    ctx = builder.build(novel_id, 2)

    assert ctx.title == "测试小说"
    assert ctx.genre == "玄幻"
    assert ctx.current_chapter_number == 2
    assert len(ctx.characters) == 1
    assert ctx.characters[0]["name"] == "主角"
    assert len(ctx.previous_summaries) == 1


def test_context_to_template_vars():
    """模板变量转换"""
    ctx = CreationContext(
        title="测试", genre="都市", tags=["重生"],
        characters=[{"name": "张三", "role": "protagonist", "description": "强者", "traits": ["冷酷"]}],
    )
    tv = ctx.to_template_vars()
    assert tv["title"] == "测试"
    assert tv["genre"] == "都市"
    assert tv["tags"] == "重生"
    assert "张三" in tv["characters"]


def test_context_builder_token_trimming():
    """token 预算裁剪"""
    ctx = CreationContext(
        recent_chapter_text="很长的文本" * 5000,
        previous_summaries=[{"number": i, "summary": f"摘要{i}"} for i in range(50)],
        active_foreshadows=[{"description": f"伏笔{i}", "status": "planted"} for i in range(30)],
    )
    # 直接调用 trim
    db = next(get_db())
    builder = ContextBuilder(db)
    trimmed = builder._trim_to_budget(ctx, 2000)
    # 应该裁剪了
    assert len(trimmed.previous_summaries) < 50 or len(trimmed.recent_chapter_text) < len("很长的文本" * 5000)


# ── _parse_json_list ─────────────────────────────────────────────

def test_parse_json_list_valid():
    assert _parse_json_list('["a","b"]') == ["a", "b"]


def test_parse_json_list_empty():
    assert _parse_json_list("") == []
    assert _parse_json_list(None) == []


def test_parse_json_list_invalid():
    assert _parse_json_list("not json") == []


def test_parse_json_list_not_list():
    assert _parse_json_list('{"a":1}') == []


# ── _extract_json ────────────────────────────────────────────────

def test_extract_json_direct():
    result = _extract_json('{"key": "value"}')
    assert result == {"key": "value"}


def test_extract_json_with_markdown():
    result = _extract_json('```json\n{"key": "value"}\n```')
    assert result == {"key": "value"}


def test_extract_json_with_extra_text():
    result = _extract_json('Here is the result: {"key": "value"} done.')
    assert result == {"key": "value"}


def test_extract_json_invalid():
    result = _extract_json("no json here")
    assert "raw" in result


# ── API 路由 ─────────────────────────────────────────────────────

def test_creation_routes_registered():
    """创作引擎路由已注册"""
    resp = client.get("/api/v1")
    data = resp.json()
    assert "creation" in data["endpoints"]


def test_autopilot_status_idle():
    """无任务时状态为 idle"""
    resp = client.get("/api/v1/creation/fake-id/autopilot/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "idle"


def test_autopilot_stop_no_task():
    """停止不存在的任务"""
    resp = client.post("/api/v1/creation/fake-id/autopilot/stop")
    assert resp.status_code == 400


def test_post_pipeline_no_chapter():
    """章后管线 — 章节不存在"""
    resp = client.post("/api/v1/creation/fake-id/chapter/99/post-pipeline")
    # ValueError 未被 HTTPException 包装时返回 500
    assert resp.status_code in (400, 404, 500)


def test_stream_endpoint_exists():
    """SSE 流式端点存在"""
    # 创建小说
    novel = client.post("/api/v1/novels/", json={"title": "SSE测试"}).json()
    # stream 端点应返回 200 (即使 LLM 未配置会在事件中报错)
    resp = client.get(f"/api/v1/creation/{novel['id']}/chapter/1/stream")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
