# Track E: 学习 Agent 系统

独立可并行的学习 Agent 轨道：热门采集 + 自动拆书学习 + 提示词/工作流优化。

## 前置条件
- 依赖 Track C 的拆书引擎（可先用简化版 mock）
- 需要 Track A 的 `get_llm_for_stage("learning_agent")` 接口

## 交付物

### 热门采集 Agent
1. `backend/app/services/learning/hot_crawler.py`
   - 番茄热销榜/飙升榜/新书榜/完本榜 爬取
   - 起点各榜单爬取
   - 元数据采集: 书名/作者/题材/标签/字数/评分/简介
   - 免费章节/试读章节下载缓存
   - 每日自动运行 (APScheduler cron)

### 拆书学习 Agent
2. `backend/app/services/learning/book_learner.py`
   - 自动对采集的热门小说调用拆书引擎
   - 提取学习维度:
     - 开篇套路 (前3章钩子结构/冲突设置)
     - 爽点分布 (高潮在全文中的分布规律)
     - 人设模板 (高人气角色的人设共性)
     - 对话风格 (不同题材的对话特征)
     - 文风样本 (句式/修辞/叙事视角)
     - 伏笔手法 (埋设-回收时间跨度)
     - 题材公式 (同题材高分书的结构共性)
   - 结果存入知识库

### 知识库
3. `backend/app/services/learning/knowledge_base.py`
   - 分类存储: 套路库/文风库/节奏库/爽点库/模板库
   - 向量索引 (ChromaDB) + 结构化索引 (SQLite/PG)
   - 创作时上下文注入接口
   - 去重/合并/过期淘汰

### 优化 Agent
4. `backend/app/services/learning/optimizer.py`
   - 提示词优化: 对比当前产出 vs 热门作品，用 LLM 改进
   - 工作流优化: 分析 Token 消耗/质量，调整参数
   - 模型配置优化建议: 根据质量评分给出阶段模型调整建议
   - A/B 对比报告生成
   - 每周自动运行

## 阶段配置
- 所有学习 Agent 任务 → `learning_agent` (实用版: gemini-2.5-flash)
- 提示词优化 → `prompt_optimization` (实用版: claude-opus-medium)

## 数据模型 (供 Track A 建表)
```python
class HotNovelMeta:
    id: str
    platform: str  # fanqie / qidian
    title: str
    author: str
    genre: str
    tags: list[str]
    word_count: int
    rating: float | None
    synopsis: str
    rank_info: dict  # {rank_type: position}
    crawled_at: datetime

class KnowledgeEntry:
    id: str
    category: str  # opening_pattern, thrill_distribution, character_template, ...
    title: str
    content: str  # JSON or markdown
    source_novel_id: str | None
    tags: list[str]
    quality_score: float
    created_at: datetime
    expires_at: datetime | None

class OptimizationLog:
    id: str
    target: str  # prompt / workflow / model_config
    before_snapshot: dict
    after_snapshot: dict
    improvement_score: float | None
    applied: bool
    created_at: datetime
```

## 步骤
1. 番茄/起点榜单爬虫 (Playwright + httpx)
2. 元数据解析 + 存储
3. 免费章节下载器
4. 知识库 CRUD + 向量索引
5. 拆书学习 Agent (调用 Track C 拆书管线)
6. 学习结果→知识库存储
7. 优化 Agent (提示词/工作流)
8. APScheduler 定时任务配置
9. API 路由 + 测试

## 预计工时
4-5 天
