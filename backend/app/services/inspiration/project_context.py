"""项目全景知识 — 供灵感助理「墨语」了解 NovelForgeX 全部能力

每次对话时自动编译为上下文注入 system prompt，
让墨语能够回答关于项目架构、已有功能、Agent 配置等问题。
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_project_context(db: Session) -> str:
    """编译完整的项目知识上下文"""
    sections = [
        _project_overview(),
        _four_engines(),
        _api_capabilities(),
        _database_overview(db),
        _agents_context(),
        _event_engine_context(),
        _llm_config(db),
        _frontend_pages(),
    ]
    return "\n".join(s for s in sections if s)


def _project_overview() -> str:
    return """## NovelForgeX 项目全景

NovelForgeX 是一个 AI 驱动的长篇小说创作引擎，支持从灵感→大纲→章节→审核→发布的全流程。
技术栈: FastAPI + SQLAlchemy + SQLite (后端) / Vue3 + Vite + ECharts (前端)
LLM 支持: OpenAI / Anthropic / Gemini 三协议统一客户端，按阶段绑定不同模型。"""


def _four_engines() -> str:
    return """## 四大引擎

### 1. 创作引擎
- **大纲生成** (OutlineGenerator): 从前提生成分卷分章大纲
- **章节写作** (ChapterWriter): beat-by-beat 逐节拍写作 + SSE 流式
- **全托管** (AutopilotDaemon): 自动连续写多章，支持暂停/恢复
- **章后管线** (PostPipeline): 写完一章后自动提取摘要/事件/人物/张力评分/知识图谱/世界地图增长/记忆索引
- **上下文预算分配器** (ContextBudgetAllocator): T0-T3优先级，35000 token 预算智能分配
- **题材 Agent 体系**: 12个已注册 Agent，每个提供人设/写作规则/节拍模板/审计标准
- **职场事件发动机**: 专为职场规则爽文设计的结构化事件生成器

### 2. 拆书引擎
- **导入** (Importer): 上传 TXT/EPUB 拆书分析
- **切分** (Splitter): 智能章节切分
- **扫描** (Scanner): 实体/角色/地点扫描
- **提取** (Extractor): 章节级知识提取
- **聚合** (Aggregator): 全书级知识聚合
- **风格指纹** (StyleFingerprint): 提取作者写作风格指纹

### 3. 世界引擎
- **角色管理** (Character): 角色状态追踪、关系网络
- **世界地图** (WorldItem): 地点/势力/物品/规则自动增长
- **知识图谱** (KnowledgeGraph): 三元组 CRUD + 自动提取
- **时间线** (Timeline): 从章节事件聚合时间线
- **百科** (Encyclopedia): 角色+世界条目聚合
- **伏笔追踪** (Foreshadow): 埋线/回收管理
- **真相文件** (TruthManager): 世界观/角色/阵营设定文件

### 4. 审核引擎
- **10维质量雷达** (QualityRadar): naturalness/reading_power/pacing/dialogue/foreshadowing/continuity/ai_detect/vocab_diversity/emotion_arc/sentence_variety
- **一致性检查** (ConsistencyChecker): 前后文矛盾检测
- **风格漂移** (StyleDriftDetector): 写作风格偏移检测
- **张力心电图** (TensionECG): 全书张力曲线可视化
- **反AI味** (AntiDetect): 疲劳词替换 + LLM 深度改写
- **自动修订** (RevisionLoop): 审计→分级修订→再审计，最多3轮"""


def _api_capabilities() -> str:
    return """## 核心 API 端点 (166条)

| 模块 | 关键端点 | 功能 |
|------|----------|------|
| 小说管理 | GET/POST /novels | 增删改查小说 |
| 大纲 | POST /creation/{id}/outline | 生成大纲 |
| 章节写作 | POST /creation/{id}/chapter/{n}/generate | 生成章节 |
| 全托管 | POST /creation/{id}/autopilot/start | 自动写多章 |
| 事件发动机 | POST /event-engine/generate | 职场事件生成 |
| 角色 | GET/POST /novels/{id}/characters | 角色管理 |
| 世界地图 | GET/POST /novels/{id}/world | 世界条目 |
| 知识图谱 | GET/POST /novels/{id}/knowledge-graph | 三元组 |
| 时间线 | GET /novels/{id}/timeline | 时间线 |
| 百科 | GET /novels/{id}/encyclopedia | 百科聚合 |
| 真相文件 | GET/PUT /novels/{id}/truth/{key} | 设定文件 |
| 审计 | POST /audit/{id}/chapters/{n}/quality | 质量审计 |
| 反AI味 | POST /audit/{id}/chapters/{n}/anti-detect | 去AI味 |
| 修订 | POST /audit/{id}/chapters/{n}/revision-loop | 自动修订 |
| 拆书 | POST /analysis/upload | 上传拆书 |
| 学习 | POST /learning/trigger-crawl | 热门书采集 |
| 灵感助理 | POST /inspiration/chat | 你(墨语)的对话接口 |
| 题材Agent | GET /theme-agents | 列出所有Agent |
| 提示词 | GET/POST /prompts | 模板管理 |
| LLM设置 | GET /settings/llm/config | 模型配置 |
| 发布 | POST /publishing/schedule | 定时发布 |"""


def _database_overview(db: Session) -> str:
    """数据库表和数据量概览"""
    try:
        from sqlalchemy import text
        result = db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ))
        tables = [r[0] for r in result]

        lines = [f"## 数据库 ({len(tables)} 张表)"]
        for t in tables:
            try:
                cnt = db.execute(text(f"SELECT COUNT(*) FROM [{t}]")).scalar()
                if cnt > 0:
                    lines.append(f"- {t}: {cnt} 条")
            except Exception:
                pass
        return "\n".join(lines)
    except Exception as e:
        return f"## 数据库\n(读取失败: {e})"


def _agents_context() -> str:
    """编译所有已注册的题材 Agent"""
    try:
        from app.services.creation.theme.theme_registry import get_theme_registry
        registry = get_theme_registry()
        agents = registry.list_agents()
        if not agents:
            return ""
        lines = ["## 已注册题材 Agent"]
        for a in agents:
            beats_count = len(a.get_beat_templates()) if hasattr(a, 'get_beat_templates') else 0
            rules = a.writing_rules[:3] if a.writing_rules else []
            rules_text = "; ".join(rules)
            lines.append(f"- **{a.genre_name}** (`{a.genre_key}`): {beats_count}组节拍 | {rules_text}")
        return "\n".join(lines)
    except Exception:
        return ""


def _event_engine_context() -> str:
    """编译事件发动机信息"""
    try:
        from app.services.creation.zhichang_event_engine import EVENT_TYPES
        lines = [
            "## 职场破局编剧 Agent（事件发动机）",
            "**状态**: 已部署，API: POST /api/v1/event-engine/generate",
            f"**内置事件类型** ({len(EVENT_TYPES)}种): {', '.join(EVENT_TYPES)}",
            "**输出**: 结构化12字段 — 事件标题/冲突起因/反派目的/反派手段/主角表面反应/"
            "主角暗中布局/关键证据/反转触发点/反派反噬/主角收获/章节大纲/爽点台词",
            "**三阶段**: 生存期(直属领导/同事)→破局期(大客户/跨部门/派系)→上位期(高层博弈/夺权)",
            "**铁律**: ①主角不主动害人 ②反派不降智 ③每事件推进主线 ④不重复手段 ⑤爽点来自对方越界 ⑥证据必须具体 ⑦反转在公开场合",
            "**输入**: protagonist_name/role/stage/existing_antagonists/last_event_result/"
            "conflict_direction/forbidden_elements/intensity",
        ]
        return "\n".join(lines)
    except Exception:
        return ""


def _llm_config(db: Session) -> str:
    """编译 LLM 配置信息"""
    try:
        from app.llm.profiles import LLMProfileRow, StageBindingRow
        profiles = db.query(LLMProfileRow).order_by(LLMProfileRow.sort_order).all()
        bindings = db.query(StageBindingRow).all()

        if not profiles:
            return ""

        binding_map = {b.stage: b.profile_id for b in bindings}
        profile_map = {p.id: p for p in profiles}  # noqa: F841

        lines = ["## LLM 模型配置"]
        for p in profiles:
            stages = [s for s, pid in binding_map.items() if pid == p.id]
            stages_text = ", ".join(stages) if stages else "未绑定"
            lines.append(f"- **{p.name}** ({p.model}): {stages_text} | temp={p.temperature}")
        return "\n".join(lines)
    except Exception:
        return ""


def _frontend_pages() -> str:
    return """## 前端页面
- **仪表盘** (DashboardPage): 新建小说、选择题材/标签、快速入口
- **工作台** (StudioPage): 左侧章节列表 + 中间编辑器 + 右侧审核面板(10维雷达图/问题/修订)
- **蓝图** (BlueprintPage): 大纲树 + 角色卡 + 世界地图 + 知识图谱 + 时间线
- **拆书** (AnalysisPage): 上传小说拆解分析
- **学习** (LearningPage): 热门书库 + 知识库 + 提示词优化
- **灵感** (InspirationPage): 你(墨语)的对话界面 + session管理 + 记忆系统
- **设置** (SettingsPage): LLM模型管理 + 阶段绑定 + 提示词模板"""
