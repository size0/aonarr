# aonarr

aonarr 是一个面向网文作者的自托管自动连载工作台，用于把长篇小说生产流程拆成可配置、可追踪、可恢复的工作流。

它支持作品管理、故事设定、章节计划、正文起草、草稿审阅、自动修订、运行日志、成本统计和文稿导出，适合部署为单租户的创作后台。

## 功能概览

- **登录与工作台**：内置本地管理员登录和中文化创作首页。
- **作品管理**：创建作品、设置类型、目标章节数和单章字数。
- **生产工作台**：按单本书管理章节计划、运行任务、草稿审阅和导出。
- **故事设定**：维护故事前提、世界观摘要、文风设定和运行前检查项。
- **自动连载**：创建、暂停、继续、取消连载运行任务。
- **运行日志**：通过实时事件流查看章节规划、草稿生成、审阅和错误信息。
- **模型配置**：支持 OpenAI 兼容接口，并在界面中隐藏密钥。
- **提示词模板**：计划、起草、审阅、修订模板可在系统设置中编辑。
- **文稿导出**：将已通过章节导出为 Markdown/TXT。

## 技术栈

- **后端**：Python、FastAPI
- **前端**：Vue 3、Vite、TypeScript、Naive UI
- **默认存储**：JSON 本地存储
- **生产数据库预留**：PostgreSQL 迁移脚本
- **运行事件**：实时事件流
- **部署方式**：Docker Compose 自托管部署

## 当前状态

当前仓库已经包含可运行的 MVP：

- 管理员登录
- 模型配置管理
- 作品创建和项目数据读取
- 故事设定保存与就绪检查
- 自动连载任务创建、暂停、继续、取消
- 后台任务执行章节规划、正文起草、质量审阅和成本统计
- 运行日志实时更新
- 章节计划和草稿版本管理
- 可编辑提示词模板
- 草稿需修订时的人工质量门恢复
- Markdown/TXT 导出
- PostgreSQL schema 与 Docker Compose 基础配置

当前自动写作链路默认使用确定性占位生成，便于在真实模型提示词接入前完整测试产品流程。

## 本地运行后端

进入 `backend` 目录后执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
python -m uvicorn app.main:app --reload
```

健康检查：

```text
GET http://localhost:8000/api/v1/health
```

## 本地运行前端

进入 `frontend` 目录后执行：

```powershell
npm install
npm run dev
```

前端地址：

```text
http://localhost:5173
```

## 默认账号

```text
用户名：admin
密码：change-me
```

## 使用流程

1. 打开前端页面。
2. 使用默认账号登录。
3. 在系统设置中创建模型配置；默认 `LLM_MODE=mock`，不会调用外部模型。
4. 在工作台首页创建作品。
5. 进入生产工作台，完善故事设定。
6. 启动自动连载任务。
7. 在运行日志中查看实时进度。
8. 如果草稿需要修订，可在草稿审阅中通过、拒绝或标记修订。
9. 将已通过章节导出为文稿。

## 真实模型模式

后端支持在显式开启后调用 OpenAI 兼容的 `/chat/completions` 接口：

```powershell
$env:LLM_MODE = "live"
python -m uvicorn app.main:app --reload
```

模型配置字段：

- `provider_type`：例如 `openai_compatible`
- `base_url`：例如 `http://localhost:11434/v1` 或其它 OpenAI 兼容网关
- `model`：供应商暴露的模型名称
- `api_key`：用户自己的接口密钥

接口密钥会在 MVP 的本地存储中加密保存，并在 API 响应中脱敏。不要提交 `local-data` 目录。

## 提示词模板

系统内置以下模板：

- `serial_plan`
- `serial_draft`
- `serial_review`
- `serial_revision`

可以在前端「系统设置 / 提示词模板」中编辑，也可以通过接口维护：

```text
GET /api/v1/prompt-templates
PATCH /api/v1/prompt-templates/{template_id}
POST /api/v1/prompt-templates/{template_id}/reset
```

## 存储后端

MVP 默认使用 JSON 存储：

```text
STORAGE_BACKEND=json
```

PostgreSQL 初始化脚本位于：

```text
backend/migrations/001_initial_schema.sql
```

初始化已配置的 PostgreSQL 数据库：

```powershell
python scripts\apply_migrations.py
```

## 测试

进入 `backend` 目录后执行：

```powershell
pytest
```

如果当前 Python 环境中的 pytest 版本过旧，可以运行内置检查脚本：

```powershell
python scripts\smoke_check.py
python scripts\unit_check.py
```

## 上线前安全检查

- 修改 `ADMIN_PASSWORD`。
- 修改 `SECRET_KEY`。
- 确认 `.env`、`local-data`、导出文件和日志不会提交到仓库。
- 真实环境建议切换到 PostgreSQL。
- 接入真实模型前检查提示词模板和成本限制。
- 如果改用 Cookie 登录，需要补充 CSRF 策略。
- 保持模型接口密钥在响应和日志中脱敏。
