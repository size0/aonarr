# Track D: 发布引擎 + 数据采集

独立可并行的发布与数据轨道：Playwright 自动发布 + 平台数据采集 + 预测模型。

## 前置条件
- 迁移 PlotPilot-new 已有的 Playwright 代码 (fanqie_browser_publisher.py, qidian_browser_publisher.py)
- 需要 Track A 的数据模型约定（开发时可 mock）

## 交付物

### 发布引擎
1. `backend/app/services/publishing/fanqie_publisher.py` — 番茄小说自动发布
2. `backend/app/services/publishing/qidian_publisher.py` — 起点中文网自动发布
3. `backend/app/services/publishing/publish_scheduler.py` — 定时发布调度器
4. `backend/app/services/publishing/content_review.py` — 发布前敏感词/格式审核
5. 登录态管理 (Playwright storage_state 持久化)
6. 多平台同步发布 + 失败重试

### 数据采集
7. `backend/app/services/data/collector.py` — 作品数据采集器
   - 阅读量/收藏/推荐票/月票 (每日)
   - 章节阅读量/评论数 (每日)
   - 追更留存漏斗 (每周)
   - 评论情感分析
   - 排行榜排名变化
8. `backend/app/services/data/trend_analyzer.py` — 趋势分析

### 预测
9. `backend/app/services/data/predictor.py` — 阅读量/追更/签约预测
   - 冷启动: LLM 基于题材+简介+前3章做粗略预测
   - 数据积累后: 轻量回归模型

## 数据模型 (供 Track A 建表)
```python
class PublishJob:
    id: str
    novel_id: str
    chapter_id: str
    platform: Literal["fanqie", "qidian"]
    status: Literal["pending", "publishing", "success", "failed"]
    scheduled_at: datetime | None
    published_at: datetime | None
    retry_count: int
    error_message: str | None

class PlatformStats:
    id: str
    novel_id: str
    platform: str
    date: date
    reads: int
    favorites: int
    recommends: int
    comments: int
    rank: int | None
    revenue: float | None

class ChapterStats:
    chapter_id: str
    platform: str
    date: date
    reads: int
    comments: int
    retention_rate: float | None
```

## 来源代码 (可直接迁移)
- `d:\13250\桌面\PlotPilot-new\infrastructure\publishing\fanqie_browser_publisher.py`
- `d:\13250\桌面\PlotPilot-new\infrastructure\publishing\fanqie_login_state_manager.py`
- `d:\13250\桌面\PlotPilot-new\infrastructure\publishing\qidian_browser_publisher.py`
- `d:\13250\桌面\PlotPilot-new\infrastructure\publishing\qidian_login_state_manager.py`

## 步骤
1. 迁移并重构番茄 Publisher
2. 迁移并重构起点 Publisher
3. 定时发布调度器 (APScheduler)
4. 发布前审核模块
5. 数据采集器 (Playwright 爬取作家后台数据)
6. 趋势分析服务
7. 预测模型 (先 LLM 冷启动)
8. API 路由 + 测试

## 预计工时
3-4 天
