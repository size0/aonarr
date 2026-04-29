from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.bible import router as bible_router
from app.api.chapters import router as chapters_router
from app.api.costs import router as costs_router
from app.api.exports import router as exports_router
from app.api.health import router as health_router
from app.api.llm_profiles import router as llm_profiles_router
from app.api.prompt_templates import router as prompt_templates_router
from app.api.projects import router as projects_router
from app.api.runtime import router as runtime_router
from app.api.runs import router as runs_router
from app.core.config import get_settings
from app.core.errors import http_exception_handler, unhandled_exception_handler


def create_app() -> FastAPI:
    app = FastAPI(title="aonarr API", version="0.1.0")
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(llm_profiles_router, prefix="/api/v1")
    app.include_router(prompt_templates_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(runtime_router, prefix="/api/v1")
    app.include_router(bible_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(chapters_router, prefix="/api/v1")
    app.include_router(exports_router, prefix="/api/v1")
    app.include_router(costs_router, prefix="/api/v1")
    return app


app = create_app()
