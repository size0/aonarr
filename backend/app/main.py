"""NovelForgeX 后端入口"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# 加载 .env 文件（项目根目录或 backend 目录）
def _load_dotenv():
    for candidate in (
        Path(__file__).resolve().parent.parent.parent.parent / ".env",  # repo_root/.env
        Path(__file__).resolve().parent.parent / ".env",                # backend/.env
    ):
        if candidate.is_file():
            with open(candidate, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())
            break

_load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.db.connection import init_db, SessionLocal  # noqa: E402
from app.db.seed_prompts import seed_prompts  # noqa: E402
import app.models.memory  # noqa: F401, E402
from app.scheduler import start_scheduler, shutdown_scheduler, register_default_jobs  # noqa: E402
from app.api.novels import router as novels_router  # noqa: E402
from app.api.analysis import router as analysis_router  # noqa: E402
from app.api.publishing import router as publishing_router  # noqa: E402
from app.api.learning import router as learning_router  # noqa: E402
from app.api.llm_settings import router as llm_settings_router  # noqa: E402
from app.api.audit import router as audit_router  # noqa: E402
from app.api.creation import router as creation_router  # noqa: E402
from app.api.data_collect import router as data_collect_router  # noqa: E402
from app.api.prediction import router as prediction_router  # noqa: E402
from app.api.prompts import router as prompts_router  # noqa: E402
from app.api.characters import router as characters_router  # noqa: E402
from app.api.outline import router as outline_router  # noqa: E402
from app.api.world import router as world_router  # noqa: E402
from app.api.truth import router as truth_router  # noqa: E402
from app.api.genres import router as genres_router  # noqa: E402
from app.api.memory import router as memory_router  # noqa: E402
from app.api.inspiration import router as inspiration_router  # noqa: E402
from app.api.knowledge import router as knowledge_router  # noqa: E402
from app.api.event_engine import router as event_engine_router  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("novelforge")


def _ensure_gpt55_profile():
    """启动时确保 GPT-5.5 Profile 存在并绑定相关阶段（从环境变量读取）"""
    import os
    import uuid
    from app.llm.profiles import LLMProfileRow, StageBindingRow, LLMConfigMeta

    base_url = os.getenv("GPT55_BASE_URL", "")
    api_key = os.getenv("GPT55_API_KEY", "")
    model = os.getenv("GPT55_MODEL", "gpt-5.5")
    if not base_url or not api_key:
        logger.info("GPT55_BASE_URL / GPT55_API_KEY 未设置，跳过自动注入")
        return

    db = SessionLocal()
    try:
        existing = db.query(LLMProfileRow).filter(LLMProfileRow.model == model).first()
        if existing:
            pid = existing.id
        else:
            pid = str(uuid.uuid4())
            db.add(LLMProfileRow(
                id=pid, name=f"{model} (auto)", protocol="openai",
                base_url=base_url,
                api_key=api_key,
                model=model, temperature=0.7, max_tokens=8192,
                timeout_seconds=600, notes=f"{model} auto-injected from env", sort_order=11,
            ))
            db.flush()
            logger.info("已创建 %s Profile: %s", model, pid)

        for stage in ("outline_planning", "book_analysis_deep", "audit_review", "prediction"):
            b = db.query(StageBindingRow).filter_by(stage=stage).first()
            if b:
                b.profile_id = pid
                b.preset_name = "custom"
            else:
                db.add(StageBindingRow(stage=stage, profile_id=pid, preset_name="custom"))

        meta = db.query(LLMConfigMeta).filter_by(key="active_preset").first()
        if meta:
            meta.value = "custom"

        db.commit()
        logger.info("%s 绑定完成: outline_planning, book_analysis_deep, audit_review, prediction", model)
    except Exception as e:
        db.rollback()
        logger.warning("%s Profile 设置跳过: %s", model, e)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NovelForgeX 启动中...")
    init_db()
    logger.info("数据库表已就绪")
    _ensure_gpt55_profile()
    seed_prompts()
    register_default_jobs()
    start_scheduler()
    # 启动发布调度器（独立于全局 APScheduler）
    from app.services.publishing.scheduler import PublishScheduler
    publish_scheduler = PublishScheduler.get_instance()
    publish_scheduler.start()
    yield
    publish_scheduler.shutdown()
    shutdown_scheduler()
    from app.llm.client import close_all_clients
    await close_all_clients()
    logger.info("NovelForgeX 已关闭")


app = FastAPI(
    title="NovelForgeX API",
    description="AI 长篇小说创作引擎",
    version="0.1.0",
    lifespan=lifespan,
)

_CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(novels_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(publishing_router, prefix="/api/v1")
app.include_router(learning_router, prefix="/api/v1")
app.include_router(llm_settings_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(creation_router, prefix="/api/v1")
app.include_router(data_collect_router, prefix="/api/v1")
app.include_router(prediction_router, prefix="/api/v1")
app.include_router(prompts_router, prefix="/api/v1")
app.include_router(characters_router, prefix="/api/v1")
app.include_router(outline_router, prefix="/api/v1")
app.include_router(world_router, prefix="/api/v1")
app.include_router(truth_router, prefix="/api/v1")
app.include_router(genres_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(inspiration_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(event_engine_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "NovelForgeX"}


@app.get("/api/v1")
def api_root():
    return {
        "service": "NovelForgeX",
        "version": "0.1.0",
        "endpoints": {
            "novels": "/api/v1/novels",
            "analysis": "/api/v1/analysis",
            "publishing": "/api/v1/publishing",
            "learning": "/api/v1/learning",
            "creation": "/api/v1/creation",
            "llm_settings": "/api/v1/settings/llm",
            "audit": "/api/v1/audit",
            "data": "/api/v1/data",
            "prediction": "/api/v1/prediction",
            "prompts": "/api/v1/prompts",
            "characters": "/api/v1/novels/{novel_id}/characters",
            "outline": "/api/v1/novels/{novel_id}/outline",
            "world": "/api/v1/novels/{novel_id}/world",
            "timeline": "/api/v1/novels/{novel_id}/timeline",
            "encyclopedia": "/api/v1/novels/{novel_id}/encyclopedia",
            "truth": "/api/v1/novels/{novel_id}/truth",
            "genres": "/api/v1/genres",
            "memory": "/api/v1/memory",
        },
    }
