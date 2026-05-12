# NovelForgeX — AI 长篇小说创作引擎

集 **AI写作 · 拆书分析 · 世界构建 · 自动发布 · 数据预测 · 智能学习** 于一体的全链路网文创作平台。

## 核心能力

| 引擎 | 功能 |
|------|------|
| **创作引擎** | 自动驾驶写作 · 步骤式向导 · 章后管线 · 向量检索上下文 |
| **拆书引擎** | txt/epub/docx 导入 · 逆向大纲 · 人物图谱 · 文风指纹 |
| **世界引擎** | 人物关系图谱 · 世界地图 · 时间线 · 百科 · 伏笔台账 |
| **发布引擎** | 番茄/起点自动发布 · 定时调度 · 多平台同步 |
| **数据引擎** | 阅读量/追更采集 · 趋势分析 · 阅读量预测 |
| **学习引擎** | 热门采集 · 自动拆书学习 · 提示词优化 · 知识库 |
| **审核引擎** | 张力评分 · 文风漂移 · 一致性校对 · 质量雷达 |

## 模型配置

混合模式 + 双预设一键切换：
- **🔥 实用版** — claude-opus-4-7-medium 主力 + gemini-flash/pro 辅助 (~$10-20/天)
- **👑 旗舰版** — claude-opus-4.6-thinking 全链路最强 (~$200-300/天)

每个阶段可独立绑定 LLM Profile，运行时固定读取，零自动判断。

## 技术栈

- **后端**: Python 3.12 · FastAPI · SQLAlchemy · SQLite/PostgreSQL · ChromaDB · APScheduler · Playwright
- **前端**: Vue 3 · TypeScript · Vite · Naive UI · TailwindCSS · ECharts · D3.js · Tiptap
- **AI**: OpenAI / Anthropic / Gemini 多协议统一接入

## 项目结构

```
NovelForgeX/
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── api/       # 路由
│   │   ├── models/    # SQLAlchemy 模型
│   │   ├── schemas/   # Pydantic DTO
│   │   ├── services/  # 业务逻辑
│   │   ├── llm/       # LLM 接入层 + StageModelResolver
│   │   └── db/        # 数据库连接
│   ├── tests/
│   └── migrations/
├── frontend/          # Vue 3 前端
│   └── src/
│       ├── views/     # 页面
│       ├── components/
│       ├── stores/    # Pinia
│       ├── api/       # API 客户端
│       └── composables/
└── docs/plans/        # 计划文档
```

## 快速开始

```bash
# 后端
cd backend
pip install -e ".[dev]"
python -m app.main

# 前端
cd frontend
npm install
npm run dev
```

## 计划文档

详见 `docs/plans/`:
- `00-master-plan.md` — 总体计划
- `track-a-backend-core.md` — 后端骨架
- `track-b-frontend-shell.md` — 前端壳
- `track-c-book-analysis.md` — 拆书引擎
- `track-d-publishing-data.md` — 发布+数据
- `track-e-learning-agent.md` — 学习Agent
