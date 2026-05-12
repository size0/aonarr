"""发布引擎 + 数据采集 基础测试"""
import json
import pytest
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.db.connection import Base, engine, SessionLocal
from app.models.publishing import PlatformStats
from app.services.publishing.login_manager import LoginStateManager
from app.services.publishing.scheduler import PublishScheduler
from app.services.data.collector import DataCollector
from app.services.data.predictor import ReadPredictor


def _drop_all_tables():
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        for table_name in Base.metadata.tables:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))


@pytest.fixture(autouse=True)
def setup_db():
    _drop_all_tables()
    Base.metadata.create_all(bind=engine)
    yield
    _drop_all_tables()


client = TestClient(app)


# ── LoginStateManager ────────────────────────────────────────────

class TestLoginStateManager:
    def test_status_no_file(self, tmp_path):
        sm = LoginStateManager("fanqie", state_dir=str(tmp_path))
        status = sm.get_status()
        assert status["ready"] is False
        assert status["exists"] is False
        assert status["platform"] == "fanqie"

    def test_save_and_load(self, tmp_path):
        sm = LoginStateManager("fanqie", state_dir=str(tmp_path))
        cookies = [{"name": "session", "value": "abc123", "domain": ".fanqienovel.com"}]
        result = sm.save_state(cookies)
        assert result["ready"] is True
        assert result["exists"] is True

        loaded = sm.load_state()
        assert loaded is not None
        assert len(loaded["cookies"]) == 1
        assert loaded["cookies"][0]["name"] == "session"

    def test_clear_state(self, tmp_path):
        sm = LoginStateManager("qidian", state_dir=str(tmp_path))
        sm.save_state([{"name": "sid", "value": "xyz"}])
        assert sm.is_ready() is True

        sm.clear_state()
        assert sm.is_ready() is False
        assert not Path(sm.state_file).exists()

    def test_is_ready(self, tmp_path):
        sm = LoginStateManager("fanqie", state_dir=str(tmp_path))
        assert sm.is_ready() is False
        sm.save_state([{"name": "tok", "value": "v"}])
        assert sm.is_ready() is True

    def test_corrupted_file(self, tmp_path):
        sm = LoginStateManager("fanqie", state_dir=str(tmp_path))
        Path(sm.state_file).write_text("not json", encoding="utf-8")
        status = sm.get_status()
        assert status["ready"] is False
        assert "损坏" in status["message"]

    def test_empty_cookies(self, tmp_path):
        sm = LoginStateManager("fanqie", state_dir=str(tmp_path))
        sm.save_state([])
        status = sm.get_status()
        assert status["ready"] is False
        assert "无有效cookies" in status["message"]


# ── API: Platforms ───────────────────────────────────────────────

class TestPlatformsAPI:
    def test_list_platforms(self):
        resp = client.get("/api/v1/publishing/platforms")
        assert resp.status_code == 200
        platforms = resp.json()
        ids = [p["id"] for p in platforms]
        assert "fanqie" in ids
        assert "qidian" in ids
        for p in platforms:
            assert "login_ready" in p
            assert "name" in p

    def test_login_status(self):
        resp = client.get("/api/v1/publishing/platforms/fanqie/login-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "fanqie"
        assert "ready" in data

    def test_login_status_unknown_platform(self):
        resp = client.get("/api/v1/publishing/platforms/unknown/login-status")
        assert resp.status_code == 404

    def test_clear_login(self):
        resp = client.delete("/api/v1/publishing/platforms/fanqie/login")
        assert resp.status_code == 200
        assert resp.json()["ready"] is False


# ── API: Jobs ────────────────────────────────────────────────────

class TestJobsAPI:
    @pytest.fixture(autouse=True)
    def _reset_scheduler(self):
        """Ensure scheduler is in a clean state for each test."""
        scheduler = PublishScheduler.get_instance()
        if not scheduler._started:
            scheduler.start()
        yield

    def _create_novel_and_chapter(self):
        novel = client.post("/api/v1/novels/", json={"title": "发布测试书"}).json()
        chapter = client.post(
            f"/api/v1/novels/{novel['id']}/chapters",
            json={"number": 1, "title": "第1章 测试", "content": "这是测试内容" * 50},
        ).json()
        return novel["id"], chapter["id"]

    def test_list_jobs_empty(self):
        resp = client.get("/api/v1/publishing/jobs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_schedule_publish(self):
        novel_id, chapter_id = self._create_novel_and_chapter()
        resp = client.post("/api/v1/publishing/schedule", json={
            "novel_id": novel_id,
            "platform": "fanqie",
            "chapter_ids": [chapter_id],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "scheduled"
        assert data["count"] == 1
        assert data["jobs"][0]["chapter_id"] == chapter_id

    def test_schedule_no_chapters(self):
        novel = client.post("/api/v1/novels/", json={"title": "空书"}).json()
        resp = client.post("/api/v1/publishing/schedule", json={
            "novel_id": novel["id"],
            "platform": "fanqie",
        })
        assert resp.status_code == 400

    def test_cancel_job(self):
        novel_id, chapter_id = self._create_novel_and_chapter()
        create_resp = client.post("/api/v1/publishing/schedule", json={
            "novel_id": novel_id,
            "platform": "fanqie",
            "chapter_ids": [chapter_id],
        })
        job_id = create_resp.json()["jobs"][0]["id"]

        resp = client.delete(f"/api/v1/publishing/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_nonexistent_job(self):
        resp = client.delete("/api/v1/publishing/jobs/nonexistent")
        assert resp.status_code == 404

    def test_list_jobs_with_filters(self):
        novel_id, chapter_id = self._create_novel_and_chapter()
        client.post("/api/v1/publishing/schedule", json={
            "novel_id": novel_id,
            "platform": "fanqie",
            "chapter_ids": [chapter_id],
        })

        resp = client.get(f"/api/v1/publishing/jobs?novel_id={novel_id}")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        resp = client.get("/api/v1/publishing/jobs?platform=fanqie")
        assert resp.status_code == 200

        resp = client.get("/api/v1/publishing/jobs?status=pending")
        assert resp.status_code == 200


# ── API: Stats ───────────────────────────────────────────────────

class TestStatsAPI:
    def test_get_stats_empty(self):
        resp = client.get("/api/v1/publishing/stats/some-novel-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data["novel_id"] == "some-novel-id"
        assert data["count"] == 0

    def test_get_stats_with_data(self):
        db = SessionLocal()
        try:
            stat = PlatformStats(
                novel_id="test-novel",
                platform="fanqie",
                stat_date=date.today(),
                reads=1000,
                favorites=50,
                recommends=200,
                comments=10,
            )
            db.add(stat)
            db.commit()
        finally:
            db.close()

        resp = client.get("/api/v1/publishing/stats/test-novel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["records"][0]["reads"] == 1000

    def test_get_stats_filter_platform(self):
        resp = client.get("/api/v1/publishing/stats/test-novel?platform=fanqie")
        assert resp.status_code == 200


# ── API: Scheduler status ────────────────────────────────────────

class TestSchedulerAPI:
    def test_scheduler_status(self):
        # Ensure scheduler is started so we get a valid response
        scheduler = PublishScheduler.get_instance()
        if not scheduler._started:
            scheduler.start()
        resp = client.get("/api/v1/publishing/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert "scheduled_jobs" in data


# ── DataCollector unit tests ─────────────────────────────────────

class TestDataCollector:
    def test_normalize_stats(self):
        collector = DataCollector()
        result = collector._normalize_stats({
            "reads": "1.5万",
            "favorites": "300",
            "recommends": "2亿",
            "comments": None,
        })
        assert result["reads"] == 15000
        assert result["favorites"] == 300
        assert result["recommends"] == 200000000
        assert result["comments"] == 0

    def test_normalize_stats_comma(self):
        collector = DataCollector()
        result = collector._normalize_stats({"reads": "1,234,567"})
        assert result["reads"] == 1234567

    def test_get_history_empty(self):
        collector = DataCollector()
        history = collector.get_history("nonexistent", "fanqie")
        assert history == []


# ── ReadPredictor unit tests ─────────────────────────────────────

class TestReadPredictor:
    def test_fallback_prediction(self):
        predictor = ReadPredictor()
        result = predictor._fallback_prediction("fanqie", 7, [])
        assert result["method"] == "fallback_baseline"
        assert len(result["predictions"]) == 7
        for p in result["predictions"]:
            assert p["predicted_reads"] >= 0
            assert 0 < p["confidence"] <= 1

    def test_fallback_with_history(self):
        predictor = ReadPredictor()
        history = [{"reads": 500, "favorites": 20, "date": "2025-01-01"}]
        result = predictor._fallback_prediction("fanqie", 3, history)
        assert result["predictions"][0]["predicted_reads"] >= 500

    def test_parse_llm_response_valid(self):
        predictor = ReadPredictor()
        raw = json.dumps({
            "predictions": [{"day": 1, "predicted_reads": 100, "confidence": 0.8}],
            "reasoning": "test",
            "suggestions": ["do x"],
        })
        result = predictor._parse_llm_response(raw)
        assert len(result["predictions"]) == 1

    def test_parse_llm_response_codeblock(self):
        predictor = ReadPredictor()
        raw = '```json\n{"predictions": [], "reasoning": "ok"}\n```'
        result = predictor._parse_llm_response(raw)
        assert result["reasoning"] == "ok"

    def test_parse_llm_response_invalid(self):
        predictor = ReadPredictor()
        result = predictor._parse_llm_response("not json at all")
        assert "predictions" in result

    def test_predict_cold_start_no_llm(self):
        predictor = ReadPredictor()
        result = predictor.predict("test-id", "fanqie", days_ahead=5)
        assert result["method"] == "fallback_baseline"
        assert len(result["predictions"]) == 5

    def test_predict_with_history(self):
        # Insert history data
        db = SessionLocal()
        try:
            for i in range(10):
                stat = PlatformStats(
                    novel_id="hist-novel",
                    platform="fanqie",
                    stat_date=date(2025, 1, i + 1),
                    reads=100 + i * 10,
                    favorites=10 + i,
                    recommends=20 + i * 2,
                    comments=5,
                )
                db.add(stat)
            db.commit()
        finally:
            db.close()

        predictor = ReadPredictor()
        result = predictor.predict("hist-novel", "fanqie", days_ahead=7)
        assert result["method"] == "statistical"
        assert result["data_points"] == 10
        assert len(result["predictions"]) == 7


# ── PublishScheduler unit tests ──────────────────────────────────

class TestPublishScheduler:
    def test_singleton(self):
        s1 = PublishScheduler.get_instance()
        s2 = PublishScheduler.get_instance()
        assert s1 is s2

    def test_get_scheduled_jobs(self):
        scheduler = PublishScheduler.get_instance()
        if not scheduler._started:
            scheduler.start()
        jobs = scheduler.get_scheduled_jobs()
        assert isinstance(jobs, list)
