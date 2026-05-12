# Track A: 后端骨架 + LLM路由层

独立可并行的后端基础设施轨道：FastAPI项目初始化、数据模型、多模型阶段配置、API骨架。

## 前置条件
- 无依赖，最先启动

## 交付物
1. `NovelForgeX/backend/` 完整 FastAPI 项目骨架
2. 数据模型 (SQLAlchemy): Novel, Chapter, Character, WorldItem, AnalysisJob, PublishJob, LearningJob
3. `StageModelResolver` + 双预设(实用版/旗舰版) + LLMProfile CRUD
4. OpenAI-compatible 统一 LLM 接入层 (支持 openai/anthropic/gemini 三协议)
5. API 路由骨架: `/api/v1/novels`, `/chapters`, `/analysis`, `/publishing`, `/learning`, `/settings`
6. SQLite + PostgreSQL 双模数据库连接
7. APScheduler 定时任务框架
8. pytest 测试骨架

## 接口约定 (供其他轨道对接)

```python
# 其他轨道的服务只需调用这个接口获取对应阶段的LLM
from app.llm.resolver import get_llm_for_stage
llm = get_llm_for_stage("chapter_writing")  # 返回配置好的 LLM client
await llm.generate(prompt, config)

# 数据模型统一用 Pydantic schema
from app.schemas.novel import NovelCreate, NovelDTO
from app.schemas.chapter import ChapterCreate, ChapterDTO
from app.schemas.analysis import AnalysisJobCreate, AnalysisJobDTO
```

## 步骤
1. `uv init NovelForgeX && cd NovelForgeX` 初始化项目
2. pyproject.toml 依赖: fastapi, uvicorn, sqlalchemy, pydantic, chromadb, apscheduler, playwright, httpx
3. 创建 `backend/app/` 目录结构
4. 数据模型 + Alembic 迁移
5. LLMProfile 表 + StageModelResolver + 双预设
6. 统一 LLM 接入层 (参考 PlotPilot 的 DynamicLLMService)
7. API 路由骨架 (先返回 mock 数据)
8. 基础测试

## 预计工时
2-3 天
