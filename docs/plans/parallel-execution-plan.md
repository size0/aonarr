# NovelForgeX 并行执行计划 — 多 AI 协作版

> 生成时间: 2026-05-05
> 项目路径: `D:\13250\桌面\NovelForgeX`
> 前端: `frontend/` (Vue 3 + TS + Naive UI + Vite, dev port 5173)
> 后端: `backend/` (FastAPI + SQLAlchemy + SQLite, port 8100)
> 前端代理: `vite.config.ts` 中 `/api` → `http://127.0.0.1:8100`

---

## 当前状态速览

| 层 | 完成度 | 说明 |
|---|---|---|
| 前端UI壳 | 90% | 11个页面已重新设计, 路由/布局/Pinia/API客户端齐全 |
| 后端API骨架 | 85% | 7大引擎路由+服务层骨架齐全 |
| 创作引擎 | 60% | autopilot/writer/pipeline 有实现, 前端未对接真实API |
| 拆书引擎 | 40% | 6步管线骨架在, LLM调用可能为TODO |
| 世界引擎 | 10% | 前端仅占位卡片 |
| 数据+预测 | 20% | 骨架在, 无真实采集/预测 |
| 学习Agent | 20% | 骨架在, 无真实爬虫 |

---

## 轨道分配 — 6 条独立轨道

```
轨道A: 创作引擎前后端打通     (改 frontend + backend, 核心链路)
轨道B: 拆书引擎真实LLM接入    (改 backend/app/services/analysis/, 纯后端)
轨道C: 世界引擎可视化          (改 frontend/src/views/WorldViewPage.vue, 纯前端)
轨道D: 大纲编辑器              (改 frontend/src/views/OutlinePage.vue + 新建后端API, 前后端)
轨道E: 数据采集+看板+预测      (改 backend/services/data/ + frontend DataBoard/Predict, 前后端)
轨道F: 提示词管理+角色CRUD     (改 frontend Prompts + 新建后端API, 前后端)
```

每条轨道**只碰自己的文件**，不会互相冲突。

---

## 轨道 A: 创作引擎前后端打通 ⭐ (最高优先级)

### 目标
让 StudioPage 的 AI 续写/全托管写作对接后端真实 SSE endpoint，实现完整写作链路。

### 涉及文件 (只改这些)
```
frontend/src/views/StudioPage.vue          ← 改: 对接真实SSE流
frontend/src/stores/creation.ts            ← 改: SSE连接管理
frontend/src/api/creation.ts               ← 改: 确认endpoint正确
backend/app/services/creation/chapter_writer.py  ← 检查: generate_chapter_stream()
backend/app/services/creation/context_builder.py ← 改: 接入ChromaDB向量检索
backend/app/services/creation/post_pipeline.py   ← 检查: 章后管线完整性
backend/app/llm/client.py                  ← 检查: 真实LLM调用是否工作
```

### 具体任务
1. **检查后端 LLM 调用链路**
   - `backend/app/llm/client.py` — 确认 `UnifiedLLMClient` 能真实调用 OpenAI-compatible API
   - `backend/app/llm/resolver.py` — 确认 `StageModelResolver.get_profile_for_stage("chapter_writing")` 返回有效配置
   - 如果 LLM client 是 mock/TODO，需要实现真实的 `generate()` 和 `generate_stream()` 方法

2. **打通 SSE 流式写作**
   - 后端: `GET /api/v1/creation/{novel_id}/chapter/{number}/stream` 已存在
   - 前端 `StudioPage.vue` 的 `startSSE()` 需要对接此 endpoint
   - 前端 `stores/creation.ts` 管理 SSE 连接状态
   - 确保 `EventSource` 正确解析 `data: {"type":"chunk","content":"..."}` 和 `data: {"type":"done"}`

3. **接入 ChromaDB 向量检索**
   - 安装: `pip install chromadb`
   - `context_builder.py` 中实现: 章节写入后 embed → 写作时检索相关段落
   - ChromaDB 集合按 novel_id 隔离

4. **全托管写作前端面板**
   - StudioPage 添加"全托管"按钮，对接 `POST /api/v1/creation/{novel_id}/autopilot/start`
   - 显示进度: 当前章/总章/已完成字数/状态
   - 暂停/继续/停止控制按钮

### 验证方式
```bash
# 后端启动
cd backend && python -m app.main
# 前端启动
cd frontend && npm run dev
# 测试: 创建作品 → 创建章节 → 点击AI续写 → 看到SSE流式文字输出
```

### 接口约定 (其他轨道不要改)
```
POST /api/v1/creation/{novel_id}/outline
POST /api/v1/creation/{novel_id}/chapter/{number}/beats
POST /api/v1/creation/{novel_id}/chapter/{number}/generate
GET  /api/v1/creation/{novel_id}/chapter/{number}/stream
POST /api/v1/creation/{novel_id}/chapter/{number}/post-pipeline
POST /api/v1/creation/{novel_id}/autopilot/start|stop|pause|resume
GET  /api/v1/creation/{novel_id}/autopilot/status
```

---

## 轨道 B: 拆书引擎真实 LLM 接入 (高优先级)

### 目标
让 BookLab 上传文件后能跑完整拆书管线，产出真实的逆向大纲/人物图谱/时间线/文风指纹。

### 涉及文件 (只改这些)
```
backend/app/services/analysis/importer.py           ← 改: txt/epub/docx导入
backend/app/services/analysis/chapter_splitter.py   ← 改: 智能切分
backend/app/services/analysis/entity_scanner.py     ← 改: 实体预扫描(jieba+LLM)
backend/app/services/analysis/chapter_extractor.py  ← 改: LLM逐章提取
backend/app/services/analysis/aggregator.py         ← 改: 全局聚合
backend/app/services/analysis/style_fingerprint.py  ← 改: 文风分析
backend/app/api/analysis.py                         ← 检查: API路由完整性
backend/app/models/analysis.py                      ← 检查: 数据模型
```

### 具体任务
1. **文件导入** — `importer.py`
   - `.txt` 直接读取
   - `.epub` 用 `ebooklib` 解析 (`pip install ebooklib beautifulsoup4`)
   - `.docx` 用 `python-docx` 解析 (`pip install python-docx`)

2. **智能切分** — `chapter_splitter.py`
   - 正则匹配: `第\d+章`, `Chapter \d+`, `卷\d+` 等模式
   - 无章节标记时按字数切分 (每3000-5000字一章)

3. **实体预扫描** — `entity_scanner.py`
   - 用 jieba 分词提取人名候选 (`pip install jieba`)
   - 可选: 调用 LLM 确认和补充

4. **逐章深度提取** — `chapter_extractor.py`
   - 调用 LLM (`get_llm_for_stage("book_analysis_extract")`)
   - 提取: 摘要、人物、事件、关系、伏笔
   - JSON Schema 约束输出格式

5. **全局聚合** — `aggregator.py`
   - 合并所有章节的人物/事件/关系
   - 去重 + 构建人物关系图
   - 生成全书逆向大纲

6. **文风指纹** — `style_fingerprint.py`
   - 句长分布、词频、修辞统计
   - 可选 LLM 分析 (`get_llm_for_stage("style_detection")`)

### 验证方式
```bash
# 单元测试
cd backend && python -m pytest tests/ -k "analysis" -v
# 集成测试: 上传一个 .txt 文件 → 等待分析完成 → 查看结果
```

### 接口约定 (已存在, 不改路由)
```
POST /api/v1/analysis/upload         ← 上传文件
GET  /api/v1/analysis/jobs           ← 任务列表
GET  /api/v1/analysis/jobs/{id}      ← 任务详情
GET  /api/v1/analysis/jobs/{id}/chapters  ← 章节分析结果
DELETE /api/v1/analysis/jobs/{id}    ← 删除任务
```

---

## 轨道 C: 世界引擎可视化 (纯前端)

### 目标
WorldViewPage 四个 Tab 从占位变为真实可视化组件。

### 涉及文件 (只改这些)
```
frontend/src/views/WorldViewPage.vue    ← 重写: 4个子Tab
frontend/src/components/               ← 新建:
  CharacterGraph.vue                   ← D3.js/vis-network 力导向图
  TimelineView.vue                     ← 多泳道时间线
  WorldMap.vue                         ← 地图标注 (简化版)
  WikiBrowser.vue                      ← 百科浏览器
frontend/package.json                  ← 添加: d3, @types/d3 (或 vis-network)
```

### 具体任务
1. **人物关系图谱** — `CharacterGraph.vue`
   - 安装 `npm install d3 @types/d3` 或 `npm install vis-network`
   - 力导向图: 节点=人物(大小按出场次数), 边=关系(标注关系类型)
   - 点击节点弹出人物详情
   - 暂时用 mock 数据, 预留 `props: { characters, relations }` 接口

2. **时间线** — `TimelineView.vue`
   - 左侧时间轴, 右侧事件卡片
   - 支持按章节/时间排列
   - 不同颜色标识不同故事线
   - 暂时用 mock 数据

3. **世界地图** — `WorldMap.vue`
   - 简化版: SVG 画布 + 标注点
   - 用户可添加地点标注
   - 后续可接入真实地图库

4. **百科浏览器** — `WikiBrowser.vue`
   - 左侧分类树(人物/地点/物品/势力/设定)
   - 右侧详情卡片
   - 搜索过滤

### 设计规范
- 使用项目已有 CSS 变量: `var(--primary)`, `var(--gray-200)`, `var(--radius)` 等
- 卡片样式参考已有页面的 `.feature-card` 风格
- 空状态使用 emoji + 标题 + 描述的三行结构

### 验证方式
```bash
cd frontend && npm run dev
# 访问 /world → 四个Tab都有可交互的组件
```

---

## 轨道 D: 大纲编辑器 (前后端)

### 目标
OutlinePage 从占位变为可交互的树形大纲编辑器。

### 涉及文件 (只改这些)
```
frontend/src/views/OutlinePage.vue      ← 重写: 树形编辑器
frontend/src/api/outline.ts             ← 新建: 大纲API客户端
frontend/src/stores/outline.ts          ← 新建: 大纲Pinia store
backend/app/api/outline.py              ← 新建: 大纲CRUD路由
backend/app/models/novel.py             ← 改: 添加Outline模型(注意不改已有Novel/Chapter)
backend/app/main.py                     ← 改: 注册outline router (加一行)
```

### 数据模型
```python
# 大纲节点 (backend/app/models/novel.py 追加)
class OutlineNode(Base):
    __tablename__ = "outline_nodes"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    novel_id = Column(String, ForeignKey("novels.id"), nullable=False)
    parent_id = Column(String, ForeignKey("outline_nodes.id"), nullable=True)
    level = Column(String)  # "volume" | "act" | "chapter" | "scene" | "beat"
    title = Column(String, default="")
    summary = Column(Text, default="")
    sort_order = Column(Integer, default=0)
    metadata_json = Column(Text, default="{}")  # 额外数据
    created_at = Column(DateTime, default=func.now())
```

### API 设计
```
GET    /api/v1/novels/{novel_id}/outline          ← 获取大纲树
POST   /api/v1/novels/{novel_id}/outline          ← 创建节点
PATCH  /api/v1/novels/{novel_id}/outline/{node_id} ← 更新节点
DELETE /api/v1/novels/{novel_id}/outline/{node_id} ← 删除节点
POST   /api/v1/novels/{novel_id}/outline/reorder   ← 批量排序
```

### 前端功能
- 树形视图: 卷 → 幕 → 章 → 场景 → 节拍
- 拖拽排序 (可用 `vuedraggable` 或 HTML5 DnD)
- 点击节点编辑标题/摘要
- 右键菜单: 添加子节点/删除/上移/下移
- 一键"AI 生成大纲" 按钮 → 调用 `POST /api/v1/creation/{novel_id}/outline`

---

## 轨道 E: 数据采集 + 看板 + 预测 (前后端)

### 目标
DataBoard 显示真实 ECharts 图表, Predict 接入 LLM 冷启动预测。

### 涉及文件 (只改这些)
```
backend/app/services/data/collector.py   ← 改: Playwright数据采集
backend/app/services/data/predictor.py   ← 改: LLM冷启动预测
backend/app/api/data_collect.py          ← 新建: 数据采集API
backend/app/api/prediction.py            ← 新建: 预测API
backend/app/main.py                      ← 改: 注册新router (加两行)
frontend/src/views/DataBoardPage.vue     ← 改: ECharts图表
frontend/src/views/PredictPage.vue       ← 改: 对接预测API
frontend/src/api/data.ts                 ← 新建: 数据API客户端
```

### 数据看板 — ECharts
- 折线图: 阅读量/收藏/追更 (按天)
- 柱状图: 各章节阅读量
- 漏斗图: 读者留存
- 先用 mock 数据渲染, 预留API接口

### 预测引擎 — LLM 冷启动
```python
# backend/app/services/data/predictor.py
async def predict_novel_performance(genre, synopsis, first_chapters):
    """用LLM做冷启动预测 (无历史数据时)"""
    llm = get_llm_for_stage("prediction")
    prompt = f"""分析以下小说的市场表现潜力:
    题材: {genre}
    简介: {synopsis}
    前三章: {first_chapters[:3000]}
    
    请返回JSON: {{
      "estimated_daily_reads": "...",
      "follow_rate": "..%",
      "signing_probability": "..%",
      "genre_heat": "...",
      "risk_warnings": ["..."],
      "optimization_suggestions": ["..."]
    }}"""
    return await llm.generate(prompt)
```

### API
```
POST /api/v1/prediction/evaluate   ← 写前预评估
GET  /api/v1/data/overview         ← 数据概览
GET  /api/v1/data/chapter-stats    ← 章节级数据
```

---

## 轨道 F: 提示词管理 + 角色 CRUD (前后端)

### 目标
PromptsPage 支持提示词模板的增删改查, 新增角色管理API。

### 涉及文件 (只改这些)
```
frontend/src/views/PromptsPage.vue      ← 改: CRUD界面
frontend/src/api/prompts.ts             ← 新建: 提示词API
backend/app/api/prompts.py              ← 新建: 提示词CRUD路由
backend/app/models/prompt.py            ← 新建: Prompt模型
backend/app/api/characters.py           ← 新建: 角色CRUD路由
backend/app/main.py                     ← 改: 注册新router (加两行)
```

### 提示词模型
```python
class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    id = Column(String, primary_key=True)
    stage = Column(String)  # chapter_writing, outline_planning, etc.
    name = Column(String)
    content = Column(Text)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
```

### 角色 API
```
GET    /api/v1/novels/{novel_id}/characters
POST   /api/v1/novels/{novel_id}/characters
PATCH  /api/v1/novels/{novel_id}/characters/{id}
DELETE /api/v1/novels/{novel_id}/characters/{id}
```

---

## ⚠️ 并行执行注意事项

### 文件冲突防范
```
backend/app/main.py — 多个轨道需要添加 router 注册
   → 约定: 每个轨道只在文件末尾添加一行 app.include_router(...)
   → 不要重新排列或修改已有的 include_router 行

backend/app/models/novel.py — 轨道D需要添加OutlineNode
   → 只在文件末尾追加新class，不改已有的 Novel/Chapter/Character

frontend/package.json — 轨道C可能需要添加 d3
   → 只 npm install 新包，不改已有依赖版本
```

### 各轨道的独占文件
```
轨道A 独占: StudioPage.vue, stores/creation.ts, api/creation.ts, services/creation/*
轨道B 独占: services/analysis/*
轨道C 独占: WorldViewPage.vue, components/CharacterGraph|Timeline|WorldMap|Wiki
轨道D 独占: OutlinePage.vue, api/outline.ts, stores/outline.ts, api/outline.py
轨道E 独占: DataBoardPage.vue, PredictPage.vue, api/data.ts, services/data/*, api/prediction.py
轨道F 独占: PromptsPage.vue, api/prompts.ts, api/prompts.py, models/prompt.py, api/characters.py
```

### 共享文件修改规则
| 文件 | 允许操作 | 规则 |
|------|---------|------|
| `backend/app/main.py` | 追加 router | 只在末尾加 `app.include_router()` |
| `backend/app/models/novel.py` | 追加模型 | 只在文件末尾追加新 class |
| `frontend/package.json` | 安装新包 | 只 `npm install xxx`，不改版本 |
| `frontend/src/router/index.ts` | 已有全部路由 | **不要改** |
| `frontend/src/App.vue` | 全局布局 | **不要改** |

### LLM 配置
后端 LLM 调用统一通过:
```python
from app.llm.resolver import StageModelResolver
resolver = StageModelResolver()
profile = resolver.get_profile_for_stage("chapter_writing")  # 获取配置
client = UnifiedLLMClient(profile)  # 创建客户端
result = await client.generate(prompt)  # 调用
```
所有轨道共用同一套 LLM 接入层，不要各自实现。

---

## 推荐执行顺序

```
第一批 (同时开始, 无依赖):
├── 轨道A: 创作引擎打通      ← AI-1 (最重要, 分配最强的AI)
├── 轨道B: 拆书引擎LLM       ← AI-2 (纯后端, 独立性最高)
└── 轨道C: 世界可视化         ← AI-3 (纯前端, 独立性最高)

第二批 (第一批完成后):
├── 轨道D: 大纲编辑器         ← AI-1 或 AI-2
└── 轨道E: 数据+预测          ← AI-3

第三批:
└── 轨道F: 提示词+角色        ← 任意AI
```

---

## 验证清单

每条轨道完成后自行验证:
- [ ] `cd backend && python -m app.main` 启动无报错
- [ ] `cd frontend && npm run dev` 启动无报错
- [ ] 相关页面功能可正常操作
- [ ] 没有改到其他轨道的独占文件
