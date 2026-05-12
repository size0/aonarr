# Track F · Managed Agents 多本书并发生产系统 RFC

> **目标**：把 NovelForgeX 从"单 agent 自动化 pipeline"升级为"多 agent 协作的小说生产系统"，支持同时生产 3 本 100 万字（300 章 / 3-5 卷）级别的小说，全流程自动化 + 关键节点人审。
>
> **基线**：当前 `autopilot.py` + `chapter_writer.py` + `post_pipeline.py` 已具备单本书 pipeline 能力。本 RFC 在此基础上增量演进，**不重写现有任何模块**。
>
> **参考**：Anthropic Engineering《Scaling Managed Agents: Decoupling the brain from the hands》
>
> **写作日期**：2026-05-12

---

## 0. TL;DR

- **角色升级**：墨语从"创作顾问"升级为"总编"，新增"责编 × N"层，原有 chapter_writer / planner / observer / reflector 降为"作者层 worker"。
- **审核分层**：按一本书的 4 个生命周期阶段（立项 → 冷启动 → 稳定 → 长跑）分别设计审核密度，避免"每章全审"的成本爆炸。
- **状态新增**：在现有 SQLite 表之上**新增** `event`、`book_state`、`review`、`task`、`foreshadow_ledger` 等表，**不动**现有任何表。
- **关键能力**：伏笔回收账本（必备）、人物弧线追踪、主题漂移检测、用户改稿学习闭环。
- **6 周路线图**：每周一个可上线的里程碑，每一周完成后都能立刻验证收益。
- **100 万字成本预算**：单本书 LLM 成本约 $50-80（Sonnet 主力 + Haiku 调度），300 章生产周期 7-14 天。

---

## 1. 背景

### 1.1 当前状态（截至 2026-05-12）

**已具备**（参见 `@d:\13250\桌面\NovelForgeX\backend\app\services\creation`）：

- `autopilot.py` · 单本书 _run_loop，支持 checkpoint 恢复
- `outline_generator.py` · 大纲生成
- `planner.py` · 章节节拍规划
- `chapter_writer.py` · beat-by-beat 写作
- `composer.py` + `context_builder.py` · 上下文编排
- `context_budget_allocator.py` · 35K token 智能预算
- `observer.py` · 章后事实提取
- `reflector.py` · 真相文件更新
- `post_pipeline.py` · 章后管线串联
- `memory_compiler.py` · 三层记忆
- `vector_store.py` · 向量检索
- `theme/` · 12 个题材 agent
- `audit/` · 质量雷达 + 一致性 + 风格漂移 + 反 AI 味 + revision_loop
- `inspiration/engine.py` · 墨语对话 agent + 跨 session 记忆

**当前局限**：

1. **单 agent pipeline，非 multi-agent 协作**：流程在 Python 代码中写死，AI 没有动态决策权。
2. **顺序生产**：章节必须串行（第 N 章必须等第 N-1 章完成才能开始）。
3. **状态散落在多张表**：`Chapter` / `TruthFile` / `MemoryIndex` / `AutopilotCheckpoint`，无法形成"事件流"做 fork、回放、跨 agent 共享。
4. **无并发多书能力**：autopilot 一次只能跑一本书。
5. **墨语只能聊天**：`stream_generate` 模式，不能真正调用其他 agent 的能力。
6. **审核机制简单**：revision_loop 是固定 3 轮，不分阶段、不分维度。
7. **无伏笔账本自动检查**：`Foreshadow` 模型存在但无自动监督机制。
8. **无用户改稿学习闭环**：用户在 StudioPage 改稿后，系统不学习偏好。

### 1.2 目标场景

用户上"工作台"：「写 3 本番茄火的题材」，或「指定题材，写 3 本」。

```
用户：「写 3 本番茄火的题材的小说，每本 100 万字」
   ↓
墨语（总编）：
   - 跑趋势分析 → 给出 5 个题材梗概
   - 用户挑 3 个 → 立项
   ↓
3 本书并发立项：
   - 每本：生成大纲 → 世界观 → 角色卡 → 真相文件初版
   - 用户审一次（人在回路 ✋）→ 进入冷启动期
   ↓
3 本书并发生产（独立管线）：
   - 每本一个责编 agent 全程负责
   - 责编派任务给作者组（写作/审计/修订）
   - 责编每章审稿、维护连续性
   - 总编每 10 章看一次卷次报告
   - 用户前 3 章必审，后续每 50 章看一次
   ↓
100 万字完成（约 7-14 天）：
   - 每本约 300 章，约 1500-3000 个 LLM 调用
   - 单本成本约 $50-80
   - 用户参与时间：约 5-10 小时（关键节点决策）
```

### 1.3 非目标（明确不做的）

- **不**重写现有任何模块（autopilot/chapter_writer/post_pipeline 全部保留）
- **不**迁移到 K8s / CubeSandbox（个人项目阶段，Python asyncio 协程足够）
- **不**做云端 SaaS 化（继续本地部署，单用户）
- **不**做 agent ↔ agent 跨网络协议（同进程内函数调用 + Event Stream 即可）
- **不**做 outcomes 评估服务（Anthropic 自己都还在 beta）

---

## 2. 核心概念

### 2.1 角色定义

| 角色 | 中文名 | 数量 | 职责 | 模型 |
|---|---|---|---|---|
| Editor in Chief | **总编 · 墨语** | 1 | 跨书统筹 / 立项 / 关键节点审 / 资源调度 / 用户对接 | Gemini Flash（小） |
| Managing Editor | **责编** | N（一本书一个） | 单本书全程负责 / 每章审稿 / 维护连续性 / 派活给作者 | Claude Sonnet（中） |
| Writer | **作者** | N | 写章节正文（beat-by-beat） | Claude Opus（大） |
| Auxiliary Workers | **作者助理** | N（每本书一组） | 节拍规划 / 一致性检查 / 风格审计 / 反 AI 味 / 修订 | Sonnet / Haiku（中小） |
| User | **出品人** | 1 | 立项确认 / 前 3 章定调 / 关键节点决策 / 终审 | 人 |

**为什么这么分模型**：写作是创作（贵且必须），审核是判定（快且高频），调度是路由（小模型足够）。这是 token efficiency 的核心。

### 2.2 关键名词

- **Book** — 一本书的元数据 + 当前生命周期阶段（沿用现有 `Novel` 表 + 新增 `book_state` 表）
- **Session** — 一本书的一次"生产 session"，可以 fork、回滚（新增 `session` 表）
- **Event** — append-only 事件流，每个 agent 的每个动作都写入（新增 `event` 表）
- **Task** — 任务图节点，描述"谁要做什么、依赖谁"（新增 `task` 表）
- **Review** — 一次审稿记录，含决策（pass/revise/rewrite/ask_user）和批注（新增 `review` 表）
- **Annotation** — 一条具体批注（新增 `annotation` 表）
- **Foreshadow Ledger** — 伏笔回收账本（沿用现有 `Foreshadow` + 新增自动检查机制）
- **Style Rule** — 从 diff-draft-final 沉淀的风格规则（新增 `style_rule` 表）
- **Lifecycle Stage** — 一本书的 4 个生命周期阶段：`incubation` / `cold_start` / `stable` / `long_run`

### 2.3 解耦的两轴（对应 Anthropic 博客）

```
brain ⟂ hands       :  墨语/责编/作者 都是 brain，audit/anti_detect/revision 是 hands
brain ⟂ session     :  所有 agent 共享 event stream，自己脑子里只装"目录页"
```

**实操含义**：
- 一个 brain（agent）的进程崩了，从 event stream 接着跑（你的 `resume_from_checkpoint` 已经是这个思路）
- 同一份 event stream 可以喂给不同 brain（墨语审稿时看的、责编改稿时看的、作者写下一章时看的，都是同一份）
- brain 之间不通过函数调用直接通信，而是通过往 event stream 写事件来"喊话"

---

## 3. 总体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         用户 / 出品人                              │
│  - 立项确认                                                       │
│  - 前 3 章定调                                                    │
│  - 关键节点决策                                                   │
│  - 周报阅读                                                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│  L1 · 总编 · 墨语（1 个 agent，多书统筹）                          │
│  - 跨书全局视图（每本书 1 页书报）                                 │
│  - 立项 → 派责编                                                  │
│  - 关键节点审（前 3 章、卷末、主题漂移）                           │
│  - 资源调度（LLM 配额分配）                                       │
│  - 用户对接（周报、决策请求）                                     │
│  context: 3 本书的书报 + 用户偏好 + 平台趋势                       │
│  model:   Gemini Flash                                            │
└──┬──────────────┬──────────────┬───────────────────────────────┘
   │              │              │
┌──▼──────┐  ┌────▼──────┐  ┌────▼──────┐
│ L2 责编 A│  │ L2 责编 B│  │ L2 责编 C│
│ 都市爽文 │  │ 玄幻热血 │  │ 职场重生 │
│ - 每章审 │  │          │  │          │
│ - 维护   │  │          │  │          │
│   真相   │  │          │  │          │
│ - 伏笔   │  │          │  │          │
│ - 派活   │  │          │  │          │
│ - 出书报 │  │          │  │          │
│ ctx:本书 │  │          │  │          │
│ model:   │  │          │  │          │
│ Sonnet   │  │          │  │          │
└──┬───────┘  └────┬─────┘  └────┬─────┘
   │              │              │
┌──▼──────────────▼──────────────▼─────────────────────────────────┐
│  L3 · 作者层（每本书一组）                                          │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐               │
│  │ Planner │ Writer  │ StyleAud│ ConsAud │ AntiAI  │ Revisor       │
│  │ Sonnet  │ Opus    │ Haiku   │ Haiku   │ Sonnet  │ Sonnet        │
│  └─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘               │
└──────────────────────────────────────────────────────────────────┘

           ↓ 所有 agent 写入

┌──────────────────────────────────────────────────────────────────┐
│       共享 Event Stream（按 book_id / session_id 分区）            │
│   event-001 book_id=A session=main type=chapter_start ts=...      │
│   event-002 book_id=A session=main type=writer_spawned ts=...     │
│   event-003 book_id=A session=main type=draft_completed ts=...    │
│   event-004 book_id=A session=main type=review_passed ts=...      │
│   event-005 book_id=A session=main type=foreshadow_planted ts=... │
│   ...                                                              │
│   - append-only，永远不删                                          │
│   - 支持 fork（从某个 event 切分支）                                │
│   - 支持回放（重建任意时刻的状态）                                  │
│   - 支持切片读（按位置 / 按类型 / 按时间范围）                      │
└──────────────────────────────────────────────────────────────────┘
```

### 3.1 组件交互（一次完整章节生产）

```
1. Coordinator (总编 or 责编) 决定写第 N 章
   → 写 event: chapter_start

2. 责编派 Planner 规划本章节拍
   → Planner 读 event stream 中的 outline / 上章摘要
   → 输出本章 beat plan
   → 写 event: beat_plan_completed

3. 责编派 Writer 写正文（可并发派多个辅助 worker）
   ├─ Writer 读 beat plan + 相关历史片段
   ├─ Writer 流式生成正文
   ├─ 并发：StyleAuditor 在 50% 时介入早停检查
   └─ 写 event: draft_completed

4. 责编审稿（编辑模式）
   ├─ 读 draft + 真相文件 + 伏笔账本
   ├─ 调 quality_radar（10 维评分）
   ├─ 调 consistency_checker
   ├─ 调 style_drift
   ├─ 跑硬约束检查（规则匹配）
   └─ 输出 Review + Annotations
   → 写 event: review_completed

5. 责编分流决策
   ├─ pass → 入库，触发图 2 流程
   ├─ revise → 调 RevisionLoop（你已有）
   ├─ rewrite → 退回作者重写（带批注）
   └─ ask_user → 推到用户面前

6. 入库后触发"连续性回写"（你的图 2）
   ├─ Observer 提取事实
   ├─ Reflector 更新真相文件
   ├─ 更新人物状态
   ├─ 更新世界地图
   ├─ 更新伏笔账本（新埋/已回收）
   └─ 写 event: continuity_updated

7. 责编向总编出"章节日志"（小型摘要）
   → 写 event: editor_report

8. 触发下一章
```

---

## 4. 数据模型设计

### 4.1 新增表（核心）

#### 4.1.1 `event`（事件流，最重要）

```sql
CREATE TABLE events (
    id              BIGSERIAL PRIMARY KEY,           -- 全局有序
    book_id         TEXT NOT NULL,                   -- 关联 Novel
    session_id      TEXT NOT NULL,                   -- 支持 fork 的 session
    parent_session  TEXT,                            -- fork 时记录父 session
    seq             BIGINT NOT NULL,                 -- session 内有序
    event_type      TEXT NOT NULL,                   -- 见 4.1.1.1
    actor           TEXT NOT NULL,                   -- 谁写的 event（agent 名）
    payload         JSONB NOT NULL,                  -- 事件载荷
    chapter_number  INT,                             -- 关联章节（可选）
    parent_event_id BIGINT,                          -- 因果链（可选）
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_events_book_session ON events (book_id, session_id, seq);
CREATE INDEX ix_events_book_chapter ON events (book_id, chapter_number);
CREATE INDEX ix_events_type ON events (event_type);
```

##### 4.1.1.1 事件类型清单

```
# 生命周期
book_created
book_phase_changed              { from, to }

# 章节生产
chapter_started                 { chapter_number, target_words }
beat_plan_completed             { beats: [...] }
writer_spawned                  { worker_id, model }
writer_progress                 { tokens, percent }
draft_completed                 { word_count, draft_path }
early_stop_triggered            { reason }

# 审核
review_started                  { reviewer, dimensions }
review_completed                { score, decision, annotations: [...] }
hard_rule_violation             { rule, evidence }
revision_requested              { focus: [...], original_score }
revision_completed              { new_score, diff_summary }
chapter_passed                  { final_score }
chapter_rejected                { reasons: [...], escalated_to }

# 连续性
observer_extracted              { facts: [...] }
truth_file_updated              { keys: [...], diff }
foreshadow_planted              { id, description, deadline }
foreshadow_recovered            { id, recovery_chapter }
foreshadow_overdue              { id }
character_state_updated         { character_id, changes }
world_item_added                { item }

# 跨章节审核
volume_review_started           { volume }
volume_review_completed         { report }
arc_consistency_check           { results }
theme_drift_alert               { drift_score, theme }

# 用户介入
user_decision_requested         { question, options, evidence }
user_decision_received          { choice, reason }
user_edit_applied               { chapter, diff }
user_preference_inferred        { rule }

# Fork / Branch
session_forked                  { from_event_id, new_session_id }
branch_merged                   { source_session, target_session }
```

#### 4.1.2 `book_state`（生命周期）

```sql
CREATE TABLE book_states (
    book_id           TEXT PRIMARY KEY,
    phase             TEXT NOT NULL,        -- incubation/cold_start/stable/long_run/completed/paused
    current_chapter   INT NOT NULL DEFAULT 0,
    target_chapters   INT NOT NULL,         -- 用户指定的目标
    current_volume    INT DEFAULT 1,
    quality_avg       FLOAT,                -- 最近 10 章平均质量分
    style_baseline_id TEXT,                 -- 风格基线（用于漂移检测）
    last_user_review_at TIMESTAMPTZ,
    next_user_review_chapter INT,           -- 下次需要用户审的章节
    paused_reason     TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);
```

#### 4.1.3 `session`（生产 session 管理）

```sql
CREATE TABLE sessions (
    id                TEXT PRIMARY KEY,
    book_id           TEXT NOT NULL,
    parent_session_id TEXT,                 -- fork 来源
    forked_at_event   BIGINT,               -- fork 时的 event id
    branch_name       TEXT NOT NULL,        -- main / experiment-... / rewrite-ch52-...
    status            TEXT NOT NULL,        -- active / merged / abandoned
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    merged_at         TIMESTAMPTZ
);
```

#### 4.1.4 `task`（任务图节点）

```sql
CREATE TABLE tasks (
    id                TEXT PRIMARY KEY,
    book_id           TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    chapter_number    INT,
    task_type         TEXT NOT NULL,        -- plan / write / audit / revise / observe / reflect / ...
    agent_name        TEXT NOT NULL,        -- writer / planner / quality_radar / ...
    status            TEXT NOT NULL,        -- pending / running / done / failed / blocked / waiting_user
    depends_on        JSONB,                -- ["task_id_1", "task_id_2"]
    input_payload     JSONB,
    output_payload    JSONB,
    error             TEXT,
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    retry_count       INT DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_tasks_status ON tasks (status, book_id);
```

#### 4.1.5 `review`（审稿记录）

```sql
CREATE TABLE reviews (
    id                TEXT PRIMARY KEY,
    book_id           TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    chapter_number    INT NOT NULL,
    reviewer          TEXT NOT NULL,        -- editor_in_chief / managing_editor / user
    decision          TEXT NOT NULL,        -- pass / revise / rewrite / ask_user
    overall_score     FLOAT,
    dimensions        JSONB,                -- {naturalness: 8, pacing: 6, ...}
    summary           TEXT,                 -- 编辑总评
    escalated_from    TEXT,                 -- 从哪个 review 升级而来
    escalated_to      TEXT,                 -- 升级到哪个 review
    decided_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE annotations (
    id                TEXT PRIMARY KEY,
    review_id         TEXT NOT NULL REFERENCES reviews(id),
    location          JSONB,                -- {paragraph: 3, char_range: [12, 45]}
    category          TEXT NOT NULL,        -- consistency / style / pacing / foreshadow / hard_rule / ...
    severity          TEXT NOT NULL,        -- info / warning / blocker
    issue             TEXT NOT NULL,
    suggestion        TEXT,
    evidence          JSONB,                -- 引用证据（其他章节 / 真相文件）
    auto_fixable      BOOLEAN DEFAULT FALSE,
    fixed             BOOLEAN DEFAULT FALSE
);
```

#### 4.1.6 `style_rule`（学习沉淀的风格规则）

```sql
CREATE TABLE style_rules (
    id                TEXT PRIMARY KEY,
    book_id           TEXT,                 -- NULL = 全局规则
    rule_type         TEXT NOT NULL,        -- diction / pacing / dialogue / metaphor / structure
    description       TEXT NOT NULL,
    examples          JSONB,                -- [{before, after, context}]
    source            TEXT NOT NULL,        -- diff_draft_final / user_explicit / hard_rule
    confidence        FLOAT,                -- 0-1
    applied_count     INT DEFAULT 0,
    last_applied_at   TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
```

#### 4.1.7 `foreshadow_check`（伏笔自动检查记录）

> `Foreshadow` 表已存在，新增检查历史

```sql
CREATE TABLE foreshadow_checks (
    id                TEXT PRIMARY KEY,
    book_id           TEXT NOT NULL,
    check_at_chapter  INT NOT NULL,
    active_count      INT,
    overdue_count     INT,
    recovered_in_window INT,
    new_planted_in_window INT,
    overdue_ids       JSONB,                -- 强制回收的伏笔 id
    next_check_at     INT,                  -- 下一次检查的章节
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.2 改造现有表

**不动现有任何字段**，只在以下表新增字段：

```sql
ALTER TABLE chapters ADD COLUMN session_id TEXT;       -- 关联生产 session
ALTER TABLE chapters ADD COLUMN review_id TEXT;        -- 最终审稿记录

ALTER TABLE foreshadows ADD COLUMN recovery_deadline INT;  -- 必须在第几章前回收
ALTER TABLE foreshadows ADD COLUMN priority TEXT;          -- low / normal / high / critical
```

### 4.3 索引策略

- `events`：按 `(book_id, session_id, seq)` 主索引，按 `(book_id, chapter_number)` 辅助索引
- `tasks`：按 `(status, book_id)` 索引（调度器频繁查询）
- 现有 SQLite 已有的索引全部保留

---

## 5. 角色定义（详细）

### 5.1 总编 · 墨语

**身份**：跨书的全局协调者，用户的主要对话对象。

**职责清单**：

| 时机 | 动作 |
|---|---|
| 用户发起立项 | 跑趋势分析 → 生成 N 个梗概 → 与用户确认 |
| 立项确认后 | 为每本书 spawn 一个责编 agent |
| 每天 / 每生产 50 章 | 生成"周报"，推送给用户 |
| 责编请求升级时 | 仲裁 |
| 主题漂移警报 | 介入决策（必要时让用户拍板） |
| 用户主动询问 | 用对话方式回答（保留现有对话能力） |
| 卷末 | 总结上卷 + 规划下卷 |

**上下文边界**（永远不爆）：

```
墨语脑子里装的：
  - 用户偏好（MemoryFact，最多 30 条）
  - 平台趋势（build_assistant_context，缓存）
  - 3 本书的"书报"（每本 ≤ 500 字摘要）
  - 当前对话上下文（最近 6 轮）
  - 待决策事项队列

墨语脑子里不装的：
  ❌ 任何章节正文
  ❌ 任何具体批注（去 events 表查）
  ❌ 任何 worker 的对话流水
```

**模型选择**：Gemini Flash（快、便宜、上下文够用）

**实现位置**：`@d:\13250\桌面\NovelForgeX\backend\app\services\inspiration\editor_in_chief.py`（新增）

### 5.2 责编（Managing Editor）

**身份**：一本书的全程负责人。

**职责清单**：

| 触发 | 动作 |
|---|---|
| 立项后启动 | 生成本书大纲 / 世界观 / 角色卡 / 真相文件初版 |
| 每章作者写完 | 全维度审稿 → 决策 |
| 审稿不通过 | 派 RevisionLoop 或退回作者重写 |
| 每 5 章 | 跑伏笔回收检查 |
| 每 10 章 | 出书报给总编 |
| 每 10 章 | 跑人物弧线审计 |
| 每卷末 | 出卷次报告 |
| 卡在硬约束 | 升级到总编 |

**上下文边界**：

```
责编脑子里装的：
  - 本书的真相文件索引（标题列表，不读正文）
  - 伏笔账本当前快照
  - 最近 10 章摘要（500 字/章）
  - 当前正在审的章节正文
  - 本书风格基线指纹

责编脑子里不装的：
  ❌ 全书所有章节正文（去 events 查切片）
  ❌ 其他书的任何信息
  ❌ 作者的具体节拍生成过程
```

**模型选择**：Claude Sonnet（判断力 + 速度）

**实现位置**：`@d:\13250\桌面\NovelForgeX\backend\app\services\agents\managing_editor.py`（新增）

### 5.3 作者（Writer）

**身份**：写章节正文。复用现有 `chapter_writer.py`，**仅在调用接口上包装**。

**改造点**：

- 把 `chapter_writer.write()` 包装成 `WriterAgent.execute(task_payload)`
- 输入：task_payload 包含 beat plan、引用片段、风格示例
- 输出：写入 event stream（流式 progress + 最终 draft_completed event）

**模型选择**：Claude Opus（创作质量为先）

**实现位置**：`@d:\13250\桌面\NovelForgeX\backend\app\services\agents\writer_agent.py`（新增，仅作为 wrapper）

### 5.4 作者助理（Auxiliary Workers）

复用现有：

| Worker | 复用 | 模型 |
|---|---|---|
| Planner | `planner.py` | Sonnet |
| StyleAuditor | `audit/style_drift_detector.py` | Haiku |
| ConsistencyAuditor | `audit/consistency_checker.py` | Haiku |
| AntiDetect | `audit/anti_detect.py` | Sonnet |
| Revisor | `audit/revision_loop.py` | Sonnet |
| Observer | `observer.py` | Sonnet |
| Reflector | `reflector.py` | Sonnet |
| QualityRadar | `audit/quality_radar.py` | Sonnet |

**改造点**：每个 worker 在执行后向 event stream append 一个 event。

---

## 6. 审核机制（用户最关心的部分）

### 6.1 按生命周期阶段的审核密度

#### 阶段 1：立项期（前 3-7 天）

```
触发：用户发起立项
持续：直到大纲 + 世界观 + 角色卡 + 真相文件初版完成并通过用户审

每本书的工作：
  1. 总编 → 跑趋势分析 + 生成 5 个梗概（用户选 3 个）
  2. 总编 → 为每本书 spawn 责编
  3. 责编 → 生成大纲（分卷 + 每卷分章范围 + 主线）
  4. 责编 → 生成世界观（地点 / 势力 / 规则 / 力量体系）
  5. 责编 → 生成主要角色卡（主角 + 3-5 个配角）
  6. 责编 → 生成真相文件初版（核心设定）
  7. 用户审（✋ 必审） → 通过 → 进入冷启动期

成本估算（单本）：约 $2-5
人审时间（单本）：30-60 分钟
```

#### 阶段 2：冷启动期（第 1-10 章）

```
关键性：决定整本书的调性，最重要的一段

每章流程：
  1. 责编 → 派 Planner 规划本章节拍
  2. 责编 → 派 Writer 写正文
  3. 责编 → 并行跑 StyleAud / ConsAud / 早停检查
  4. 责编 → 全维度审稿（10 维质量 + 一致性 + 风格 + 伏笔 + 节奏）
  5. 决策：
     - pass → 入库 → 触发图 2 连续性回写
     - revise → 派 Revisor → 复审
     - rewrite → 退回作者，附带具体批注 → 重写
     - 升级 → 总编介入
  6. 入库后：Observer + Reflector + 伏笔账本更新

特殊：前 3 章用户必审（定调）
       4-10 章总编每 3 章过一次

成本估算（单本 10 章）：约 $3-5
人审时间（单本前 3 章）：30-90 分钟
```

#### 阶段 3：稳定期（第 10-50 章）

```
特点：流程已稳定，审核密度降低，速度提升

每章流程：
  1. 责编 → 派 Writer 写正文（保留早停检查）
  2. 责编 → 速审（只跑 quality_radar）
  3. 分流：
     - 分数 > 80 → 自动入库 ✅
     - 分数 70-80 → 自动 revision_loop → 复审 → 入库
     - 分数 60-70 → 退回作者重写一次
     - 分数 < 60 → 升级总编
  4. 入库后：完整图 2 连续性回写

每 5 章：
  - 责编跑"伏笔回收检查"
  - 责编跑"风格一致性"对比基线指纹

每 10 章：
  - 责编出书报给总编
  - 总编决定要不要让用户看一眼

成本估算（单本 40 章）：约 $10-15
人审时间（单本 40 章）：可选，0-30 分钟
```

#### 阶段 4：长跑期（第 50 章+）

```
特点：从"单章质量"转向"长程一致性"
关键挑战：100 万字的真正考验

每章流程：与稳定期相同（基础审核）

每 5 章：
  - 伏笔回收审计（强制）
  - overdue 伏笔 → 强制本章/下章回收

每 10 章：
  - 人物弧线审计
  - 主角性格漂移检测
  - 配角戏份分布

每 20 章：
  - 主题漂移检测
  - 抽样 5 章让 LLM 判断主题密度

每 30 章：
  - 总编做"卷次总结"
  - 规划下一卷

每 50 章：
  - 用户做"出品人审片"（必审 ✋）
  - 满意度评分 + 方向调整意见

成本估算（单本 250 章）：约 $35-60
人审时间（单本 250 章）：约 2-4 小时
```

#### 阶段 5：完结期

```
- 末卷收尾审核（总编 + 用户）
- 全书一致性终审
- 全书风格一致性报告
- 输出最终稿
```

### 6.2 审核维度（按阶段开启）

| 维度 | 立项 | 冷启动 | 稳定 | 长跑 | 实现 |
|---|---|---|---|---|---|
| 10 维质量雷达 | – | ✅ 每章 | ✅ 每章 | ✅ 每章 | `quality_radar.py` |
| 一致性检查 | – | ✅ 每章 | ✅ 5章/次 | ✅ 5章/次 | `consistency_checker.py` |
| 风格漂移 | 基线 | ✅ 每章 | ✅ 10章/次 | ✅ 5章/次 | `style_drift_detector.py` |
| 反 AI 味 | – | ✅ 必跑 | 视分数 | 视分数 | `anti_detect.py` |
| 伏笔回收 | 初始化 | ✅ 5章/次 | ✅ 5章/次 | ✅ 5章/次 | **NEW** |
| 人物弧线 | 初始化 | – | ✅ 10章/次 | ✅ 10章/次 | **NEW** |
| 主题漂移 | 基线 | – | – | ✅ 20章/次 | **NEW** |
| 张力曲线 | – | ✅ 每章 | ✅ 5章/次 | ✅ 5章/次 | `tension_ecg`（已有） |

### 6.3 硬约束规则（一票否决，0 LLM 成本）

```python
HARD_RULES = [
    # === 真相文件类 ===
    {
        "id": "protagonist_name_immutable",
        "description": "主角姓名必须等于 truth_file['protagonist']['name']",
        "category": "consistency",
        "severity": "blocker",
        "check": lambda draft, ctx: ctx.protagonist_name in draft,
    },
    {
        "id": "core_rules_immutable",
        "description": "本卷核心规则不可推翻",
        "check": "...",
    },
    
    # === 伏笔类 ===
    {
        "id": "foreshadow_recovery_deadline",
        "description": "已埋伏笔的回收期 < 50 章",
        "check": "...",
    },
    {
        "id": "no_duplicate_foreshadow",
        "description": "已声明的伏笔不可重复埋",
        "check": "...",
    },
    
    # === 时序类 ===
    {
        "id": "timeline_monotonic",
        "description": "时间线不可倒流（除非显式回忆）",
        "check": "...",
    },
    
    # === 角色状态类 ===
    {
        "id": "dead_character_stays_dead",
        "description": "已死亡角色不可复活（除非有显式伏笔）",
        "check": "...",
    },
    
    # === 字数类 ===
    {
        "id": "chapter_word_range",
        "description": "本章字数 ∈ [2800, 4500]",
        "check": lambda draft, ctx: 2800 <= len(draft) <= 4500,
    },
    
    # === 结构类 ===
    {
        "id": "no_outline_skip",
        "description": "本章必须包含大纲指定节拍的核心事件",
        "check": "...",
    },
]
```

**特点**：
- 全部规则匹配，**不调用 LLM**
- 0 成本必检
- 任一违反 → blocker → 直接退回作者
- 沉淀过程：用户每次手改时如果触发了规则，规则置信度 +1；如果用户允许"违反"，规则降级

**实现位置**：`@d:\13250\桌面\NovelForgeX\backend\app\services\audit\hard_rules.py`（新增）

### 6.4 仲裁机制

```
情境：责编速审"通过"，但 ConsistencyAuditor 报"和第 5 章矛盾"

仲裁流程：

Step 1 · 同层冲突
  责编内部权衡（看冲突严重度）：
    - blocker → 强制升级
    - warning → 责编自主决策
    - info → 写入 annotation 但通过

Step 2 · 责编拿不准
  升级到总编，附带：
    - 冲突双方的事件 id
    - 责编的初步判断
    - 候选方案（pass / revise / rewrite）

Step 3 · 总编也拿不准
  推给用户决策，附带完整证据链：
    - 第 51 章某处 [event-XXX]
    - 第 5 章某处 [event-YYY]
    - 真相文件相关条目
    - 责编理由
    - 总编理由
    - 候选选项

Step 4 · 用户决策
  - 用户选择 → 沉淀为新规则（下次同类问题自动判定）
  - 写入 events: user_decision_received + user_preference_inferred
```

---

## 7. 关键流程（详细 sequence）

### 7.1 用户发起：「写 3 本番茄火的小说」

```
T0  USER → POST /managed/projects/start
         { goal: "写 3 本番茄火的题材", count: 3, target_words: 1_000_000 }

T1  API → 总编墨语 EditorInChief.start_project(...)

T2  墨语 → 跑 build_assistant_context（已有）
         → 用 Gemini Flash 生成 5 个梗概候选
         → 写 events:
             [event: project_started]
             [event: synopses_generated × 5]

T3  墨语 → 推送给用户："请从 5 个梗概中选 3 个"

T4  USER → POST /managed/projects/{pid}/confirm-synopses
         { selected: [synopsis_1_id, synopsis_3_id, synopsis_5_id] }

T5  墨语 → 为每个选定梗概创建一本 Novel + book_state
         → 为每本书 spawn ManagingEditor
         → 写 events:
             [event: book_created × 3]
             [event: managing_editor_spawned × 3]

T6  3 个责编并发启动（asyncio.gather）：
    责编 A → 生成大纲 / 世界观 / 角色卡 / 真相文件初版
    责编 B → 同上
    责编 C → 同上

T7  3 本书都准备好 → 总编通知用户："3 本书的设定已就绪，请审"

T8  USER → 审 3 本书的初版（可改、可拒）
         → POST /managed/books/{bid}/approve-setup

T9  3 本书的 book_state.phase 切换到 cold_start
    每本书启动各自的生产 daemon
```

### 7.2 单章生产（冷启动期）

```
责编 A · 决定写第 3 章
   ↓
write event: chapter_started { ch: 3 }
   ↓
创建任务图：
   task_1: Planner   deps: []
   task_2: Writer    deps: [task_1]
   task_3: StyleAud  deps: [task_2] parallel
   task_4: ConsAud   deps: [task_2] parallel  
   task_5: Editor审  deps: [task_2, task_3, task_4]
   ↓
TaskExecutor 调度：
   task_1 → planner.create_plan(ch=3)
            写 event: beat_plan_completed
   task_2 → writer.write(beats, refs)
            流式写 events: writer_progress
            最终 event: draft_completed
   task_3 & task_4 并发跑
   task_5 → 责编审稿
            读 events: draft_completed, style_audit, consistency
            调 quality_radar
            跑 HARD_RULES
            决策...
   ↓
责编决策：score=72 → revise
   ↓
spawn task_6: Revisor deps: [task_5]
   task_6 → revision_loop.revise(focus=...)
            写 event: revision_completed
   ↓
责编复审：score=84 → pass
   ↓
write event: chapter_passed { score: 84 }
   ↓
入库（沿用现有 chapter 表写入）
   ↓
触发"图 2 连续性回写"：
   - Observer 写 event: observer_extracted
   - Reflector 写 event: truth_file_updated
   - 伏笔账本更新 写 event: foreshadow_planted/recovered
   - 角色状态更新 写 event: character_state_updated
   ↓
责编向总编出"章节日志"
   write event: editor_report
   ↓
准备写下一章
```

### 7.3 关键节点：用户审核（前 3 章定调）

```
冷启动期第 3 章入库后
   ↓
责编 → 检查 book_state.next_user_review_chapter
   → 命中（== 3）
   ↓
责编 → 暂停下一章生产
   write event: user_decision_requested
   {
     question: "前 3 章已完成，请审定调",
     evidence: [chapter_1.id, chapter_2.id, chapter_3.id],
     options: ["approve", "request_changes", "rewrite_from", "abandon"]
   }
   ↓
推送用户（前端 InspirationPage 浮窗 + 邮件/推送）
   ↓
USER → POST /managed/books/{bid}/user-review
       { 
         decision: "approve",
         feedback: "节奏挺好，第 2 章配角戏份再多一点"
       }
   ↓
墨语 → 解析用户反馈
   → 提取规则："配角戏份占比应提高"
   → 写 events:
       user_decision_received
       user_preference_inferred { rule: "..." }
       style_rule_added
   ↓
责编 → 接收规则更新
   → book_state.phase → stable
   → next_user_review_chapter += 50
   → 恢复下一章生产
```

### 7.4 长跑期：伏笔回收审计

```
责编 · 每 5 章触发
   ↓
读 foreshadow 表：所有 status = active 的伏笔
   ↓
对每条伏笔：
   if planted_at + recovery_deadline < current_chapter:
       → status = overdue
       → 写 event: foreshadow_overdue
   elif current_chapter - planted_at > recovery_deadline * 0.7:
       → 标记为 "urgent_recovery_window"
       → 在下章的 task_1 (Planner) 中强制注入

接下来 1-3 章内：
   Planner 收到 urgent_recovery_window 信号
   → 生成 beat plan 时强制包含"回收伏笔 X"节拍
   → Writer 必须在文中体现回收
   → Editor 审稿时确认"回收触发"
   → 写 event: foreshadow_recovered
```

### 7.5 长跑期：主题漂移检测

```
总编 · 每 20 章触发
   ↓
从最近 20 章中抽样 5 章
   ↓
用 Sonnet 跑主题密度分析：
   prompt: "本书的核心主题是 X，请评估下面 5 章中
            主题表达的密度（0-10）和具体体现位置"
   ↓
对比 expected_density（从立项时定义）：
   - 漂移 < 10% → 通过
   - 漂移 10-30% → 警报，下一卷规划时调整
   - 漂移 > 30% → 严重，推用户决策
   ↓
写 event: theme_drift_alert
```

---

## 8. API 设计

### 8.1 新增端点

```
# 项目管理
POST   /managed/projects/start
  body: { goal, count, target_words, preferred_genres?, model_tier? }
  → { project_id, synopses: [...] }

POST   /managed/projects/{pid}/confirm-synopses
  body: { selected: [synopsis_id, ...] }
  → { books: [...] }

GET    /managed/projects/{pid}
  → { status, books: [...], events_count, cost_so_far }

# 单本书
GET    /managed/books/{bid}
  → { state, current_chapter, quality_avg, next_review_chapter, ... }

POST   /managed/books/{bid}/approve-setup
POST   /managed/books/{bid}/pause
POST   /managed/books/{bid}/resume
POST   /managed/books/{bid}/user-review
  body: { decision, feedback?, changes? }

GET    /managed/books/{bid}/weekly-report
  → 总编生成的周报

# 事件流（用于调试和前端实时展示）
GET    /managed/books/{bid}/events
  query: ?from_seq=...&type=...&limit=...
  → SSE 流，按 seq 推送

# Fork / Branch
POST   /managed/books/{bid}/fork
  body: { from_event_id, branch_name, purpose }
  → { new_session_id }

POST   /managed/books/{bid}/merge
  body: { source_session, target_session }

# 审稿台（让用户直接看墨语的审稿）
GET    /managed/books/{bid}/reviews
GET    /managed/reviews/{rid}
  → { decision, annotations, evidence, ... }

# 学习闭环（diff-draft-final）
POST   /managed/books/{bid}/chapter/{n}/finalize
  body: { user_final_text }
  → { lessons: [...], rules_sedimented: [...] }

GET    /managed/books/{bid}/style-rules
```

### 8.2 现有端点保留

所有现有 `/api/v1/...` 端点保留，新功能在 `/managed/...` 命名空间下，便于切换。

---

## 9. 6 周开发计划（详细到文件级）

### 第 1 周 · 墨语主编模式（验证可行性）

**目标**：让墨语真的能审你的某一章，输出结构化批注。

**新建文件**：

```
@d:\13250\桌面\NovelForgeX\backend\app\services\inspiration\editor_mode.py
  - 类：MuyuEditor
  - 方法：review_chapter(db, novel_id, chapter_number) -> ReviewResult
  - 行为：
    1. 读章节正文
    2. 并发跑 quality_radar / consistency / style_drift
    3. 用 EDITOR_SYSTEM prompt 让 LLM 综合
    4. 返回结构化 Review + Annotations

@d:\13250\桌面\NovelForgeX\backend\app\services\inspiration\editor_prompts.py
  - EDITOR_SYSTEM 提示词
  - REVIEW_OUTPUT_SCHEMA（pydantic）

@d:\13250\桌面\NovelForgeX\backend\app\services\audit\hard_rules.py
  - HARD_RULES 列表
  - 函数：run_hard_rules(draft, ctx) -> list[Violation]

@d:\13250\桌面\NovelForgeX\backend\app\routes\managed.py
  - POST /managed/books/{bid}/chapter/{n}/review
```

**改造文件**：

- `@d:\13250\桌面\NovelForgeX\backend\app\main.py`：注册 managed 路由

**验收**：

```bash
curl -X POST http://localhost:8000/managed/books/{bid}/chapter/3/review

返回：
{
  "decision": "revise",
  "score": 72,
  "summary": "主线推进合格，中段对话密度过高（47%），建议拆解",
  "annotations": [
    {
      "location": {"paragraph": 3, "char_range": [120, 380]},
      "category": "pacing",
      "severity": "warning",
      "issue": "连续 3 个长对话",
      "suggestion": "建议改为动作 + 对白交替",
      "auto_fixable": true
    },
    ...
  ],
  "next_action": "trigger_revision_loop"
}
```

**Token 成本**：单次审稿 ≈ $0.05（Sonnet）

---

### 第 2 周 · Event Stream 基础

**目标**：建立 append-only 事件流，所有现有动作都能写入。

**新建文件**：

```
@d:\13250\桌面\NovelForgeX\backend\app\models\events.py
  - 类：Event（SQLAlchemy）
  - 类：Session
  - 索引定义

@d:\13250\桌面\NovelForgeX\backend\app\services\events\event_store.py
  - 类：EventStore
  - 方法：
    - append(book_id, session_id, event_type, payload, actor, ...)
    - get_events(book_id, session_id, from_seq=0, limit=100, types=None)
    - get_events_by_chapter(book_id, chapter_number)
    - fork_session(book_id, from_event_id, branch_name) -> new_session_id
    - get_session_state(session_id) -> 重建状态

@d:\13250\桌面\NovelForgeX\backend\app\services\events\event_types.py
  - 所有 event_type 常量
  - payload schema（pydantic）
```

**改造文件**：

- `autopilot.py`：每个关键节点 append event（不影响现有逻辑）
- `chapter_writer.py`：开始/进度/完成都 append event
- `post_pipeline.py`：每个子步骤 append event
- `editor_mode.py`（第 1 周做的）：审稿动作 append event

**Migration**：

```
@d:\13250\桌面\NovelForgeX\backend\alembic\versions\xxx_add_events.py
  - 创建 events 表
  - 创建 sessions 表
```

**验收**：

```bash
GET /managed/books/{bid}/events?limit=50

返回最近 50 条事件，能看到：
- chapter_started
- writer_progress (多条流式)
- draft_completed
- review_started
- review_completed
- chapter_passed
- observer_extracted
- truth_file_updated
- ...
```

---

### 第 3 周 · 多本书并发管线

**目标**：能同时跑 2-3 本书，互不打架。

**新建文件**：

```
@d:\13250\桌面\NovelForgeX\backend\app\models\book_state.py
  - 类：BookState

@d:\13250\桌面\NovelForgeX\backend\app\services\agents\book_daemon.py
  - 类：BookProductionDaemon
  - 每本书一个独立的 asyncio Task
  - 内部 run_loop 类似现有 autopilot 但解耦

@d:\13250\桌面\NovelForgeX\backend\app\services\agents\daemon_pool.py
  - 类：DaemonPool
  - 管理所有 BookProductionDaemon 的生命周期
  - 提供 spawn / pause / resume / stop

@d:\13250\桌面\NovelForgeX\backend\app\services\agents\llm_quota.py
  - 类：LLMQuotaScheduler
  - 全局 LLM 配额分配
  - 按 priority 排队
  - 防止单本书烧光配额
```

**改造文件**：

- `autopilot.py`：保留为单本书 daemon 的内核
- `main.py`：app 启动时初始化 DaemonPool

**验收**：

```bash
# 启动 2 本书
POST /managed/projects/start { count: 2, ... }
POST /managed/projects/{pid}/confirm-synopses { ... }

# 观察两本书同时跑
GET /managed/projects/{pid}
返回：
{
  "books": [
    { "id": "book_a", "phase": "cold_start", "current_chapter": 3, ... },
    { "id": "book_b", "phase": "cold_start", "current_chapter": 2, ... }
  ],
  "active_workers": 6,
  "queued_tasks": 12
}
```

---

### 第 4 周 · 责编层 + 总编层分层

**目标**：把现有 autopilot 拆成 L1/L2/L3 三层。

**新建文件**：

```
@d:\13250\桌面\NovelForgeX\backend\app\services\agents\managing_editor.py
  - 类：ManagingEditor
  - 方法：
    - bootstrap_book()           # 立项后生成大纲/世界观/真相文件
    - produce_chapter(n)         # 单章生产（编排任务图）
    - review_chapter(n)          # 审稿
    - run_periodic_audits()      # 每 5/10 章的周期审计
    - generate_report()          # 出书报

@d:\13250\桌面\NovelForgeX\backend\app\services\inspiration\editor_in_chief.py
  - 类：EditorInChief（墨语总编人格）
  - 方法：
    - start_project()            # 立项
    - daily_supervisor()         # 每日扫描所有书
    - handle_escalation()        # 处理责编升级
    - generate_weekly_report()
    - decide_on_drift_alert()

@d:\13250\桌面\NovelForgeX\backend\app\services\agents\writer_agent.py
  - 类：WriterAgent（chapter_writer 的薄包装）
  - 方法：execute(task_payload) -> writes events
```

**改造文件**：

- `book_daemon.py`：内部委托给 ManagingEditor
- `editor_mode.py`（第 1 周）：被 ManagingEditor 复用

**验收**：

```bash
# 在第 3 章触发"用户审"
POST /managed/books/{bid}/user-review { decision: "approve", feedback: "..." }

# 看墨语的反应
GET /managed/books/{bid}/events?type=user_preference_inferred
→ 应该有一条新的偏好规则被沉淀

# 总编出周报
GET /managed/projects/{pid}/weekly-report
→ 返回 3 本书的对比表 + 关注事项
```

---

### 第 5 周 · 长程审核能力（关键）

**目标**：实现伏笔回收 / 人物弧线 / 主题漂移三大长程审计。

**新建文件**：

```
@d:\13250\桌面\NovelForgeX\backend\app\services\audit\foreshadow_auditor.py
  - 类：ForeshadowAuditor
  - 方法：
    - run_5_chapter_check(book_id, current_chapter)
    - force_recovery(book_id, foreshadow_id)
    - on_chapter_passed(book_id, chapter, draft)  # 自动提取新埋伏笔

@d:\13250\桌面\NovelForgeX\backend\app\services\audit\character_arc_auditor.py
  - 类：CharacterArcAuditor
  - 方法：
    - run_10_chapter_check(book_id, current_chapter)
    - detect_ooc(character, recent_chapters)

@d:\13250\桌面\NovelForgeX\backend\app\services\audit\theme_drift_auditor.py
  - 类：ThemeDriftAuditor
  - 方法：
    - run_20_chapter_check(book_id, current_chapter)
    - sample_chapters(book_id, n_samples)
```

**新建数据模型**：

```
@d:\13250\桌面\NovelForgeX\backend\app\models\character_arc.py
  - 类：CharacterArc
  - 字段：character_id, arc_stages, current_stage, stage_chapter_range

@d:\13250\桌面\NovelForgeX\backend\app\models\theme.py
  - 类：BookTheme
  - 字段：book_id, primary_theme, sub_themes, expected_density
```

**改造文件**：

- `managing_editor.py`：在 `run_periodic_audits()` 中调用三大审计
- `foreshadow` 表：新增 `recovery_deadline` / `priority` 字段

**验收**：

```bash
# 让一本书跑到第 30 章
# 然后查伏笔健康度
GET /managed/books/{bid}/foreshadow-health
→ {
  "active": 8,
  "overdue": 1,
  "recovered_recent_5_ch": 2,
  "upcoming_deadline_5_ch": ["fs_id_1", "fs_id_2"]
}

# 看人物弧线状态
GET /managed/books/{bid}/character-arcs
→ {
  "protagonist": {
    "current_stage": "觉醒",
    "stage_progress": 0.6,
    "ooc_alerts": []
  },
  ...
}
```

---

### 第 6 周 · 学习闭环（diff-draft-final）

**目标**：用户改稿后，墨语真的学到东西。

**新建文件**：

```
@d:\13250\桌面\NovelForgeX\backend\app\services\learning\diff_learner.py
  - 类：DiffLearner
  - 方法：
    - on_chapter_finalized(book_id, chapter, user_final_text)
    - extract_three_way_diff(initial_draft, editor_revised, user_final)
    - classify_changes(diffs)
    - propose_rules(classified)
    - sediment_to_style_rules(rules)

@d:\13250\桌面\NovelForgeX\backend\app\models\style_rule.py
  - 类：StyleRule
```

**改造文件**：

- `managing_editor.py`：审稿时引用 style_rules 库
- `writer_agent.py`：写作时引用 style_rules 库
- `editor_prompts.py`：在 EDITOR_SYSTEM 中注入 style_rules

**验收**：

```bash
# 在某章定稿后
POST /managed/books/{bid}/chapter/52/finalize { user_final_text: "..." }
→ {
  "lessons": [
    {
      "type": "diction",
      "description": "用户偏好将'风轻轻吹过'改为'风像剃刀刮过'，体现锐利意象",
      "examples": [...],
      "confidence": 0.6
    },
    ...
  ],
  "rules_sedimented": ["sr_id_1"]
}

# 看规则库
GET /managed/books/{bid}/style-rules
→ 按使用频次排序的规则列表
```

---

### 第 7-8 周（可选）· 前端 + 体验打磨

- 前端 `InspirationPage` 新增"审稿台" Tab
- 前端 `DashboardPage` 显示多书并发状态
- 前端章节编辑器集成"墨语主编批注"侧栏
- 用户介入点的浮窗体验
- 周报推送（邮件 / 桌面通知）

---

## 10. 成本预算（100 万字 / 单本书）

### 10.1 LLM 调用清单（单章）

| 步骤 | 模型 | Input tokens | Output tokens | 单次成本 |
|---|---|---|---|---|
| Planner（章节计划） | Sonnet | 2,000 | 1,000 | $0.021 |
| Writer（写正文） | Opus | 8,000 | 4,000 | $0.420 |
| StyleAuditor | Haiku | 5,000 | 500 | $0.005 |
| ConsistencyAuditor | Haiku | 6,000 | 500 | $0.006 |
| Editor 审稿 | Sonnet | 10,000 | 1,500 | $0.053 |
| Revision（如需） | Sonnet | 10,000 | 4,000 | $0.090 |
| Observer | Sonnet | 5,000 | 2,000 | $0.045 |
| Reflector | Sonnet | 4,000 | 1,500 | $0.036 |
| **小计（不修订）** | | | | **$0.586** |
| **小计（含 1 次修订）** | | | | **$0.676** |

### 10.2 周期性审计成本

| 频率 | 内容 | 单次成本 |
|---|---|---|
| 每 5 章 | 伏笔回收检查 | $0.02（主要是规则匹配 + 1 次 LLM 总览） |
| 每 10 章 | 人物弧线 | $0.10 |
| 每 10 章 | 责编书报 | $0.05 |
| 每 20 章 | 主题漂移 | $0.30 |
| 每 30 章 | 卷次总结 | $0.50 |

### 10.3 单本书总成本（100 万字 / 300 章）

```
基础生产：
  300 章 × $0.586         = $176     (理想，无修订)
  300 章 × $0.676         = $203     (含 30% 修订率)

周期性审计：
  伏笔：60 次 × $0.02     = $1.2
  人物：30 次 × $0.10     = $3.0
  书报：30 次 × $0.05     = $1.5
  主题：15 次 × $0.30     = $4.5
  卷次：10 次 × $0.50     = $5.0
  ──────────────────────
                          = $15.2

立项 + 设定：             = $5

总编对话 / 周报：         = $5

───────────────────────────────
单本总成本：              ≈ $200-230
```

**3 本并发**：≈ $600-700

> 注：这是 API 价格估算。如果使用 OpenRouter / 国内厂商，成本可降至 1/3 - 1/5。

### 10.4 生产时长估算

```
单章生产平均耗时：
  - Planner: 10s
  - Writer: 60s
  - 审稿 + 修订: 30s
  - Observer/Reflector: 30s
  ────────
  单章总: ~2 分钟

3 本并发：
  - 单本约 5-8 章/小时
  - 3 本约 15-20 章/小时
  - 100 万字 × 3 本 = 900 章
  - 总耗时: 45-60 小时 ≈ 2-3 天密集生产

实际节奏（含审核等待）：
  - 含用户审核间隔
  - 含 LLM API 限速
  - 实际: 7-14 天
```

---

## 11. 风险与回退

### 11.1 主要风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Event 表膨胀 | 高 | 查询变慢 | 按 book_id 分区 + 冷数据归档 |
| LLM 配额超限 | 中 | 生产中断 | LLMQuotaScheduler 限速 + 多 provider 轮询 |
| 责编漏检导致后期崩盘 | 中 | 重做章节 | Fork 机制兜底，可从任意 event 重启 |
| 多书风格污染 | 低 | 串味 | 每本书独立 daemon + 独立 style_baseline |
| 总编上下文撑爆 | 低 | 周报失真 | 严格约束总编只读"目录页" |
| 用户改稿打架 | 低 | 学习失效 | 三方 diff + 显式偏好沉淀 |

### 11.2 回退策略

每一周的改动都保证：

1. **现有 autopilot 完全可用**（不改动 autopilot.py 主干逻辑）
2. **新功能在 `/managed/` 命名空间下**，关掉 daemon 后回到旧流程
3. **数据库新表全部独立**，不动现有任何表的数据
4. **每周代码独立 PR**，可单独 revert

回退命令：

```bash
# 第 N 周回退
git revert <week_N_pr_sha>
alembic downgrade -1
重启服务
```

---

## 12. 验收标准

### 12.1 单元测试覆盖

| 模块 | 目标覆盖率 |
|---|---|
| event_store | ≥ 90% |
| hard_rules | 100% |
| managing_editor | ≥ 70% |
| editor_in_chief | ≥ 60% |
| foreshadow_auditor | ≥ 80% |

### 12.2 端到端测试场景

**Scenario A**：3 本书并发跑到第 10 章
```
前置：用户发起立项 → 选 3 个梗概
执行：等待 3 本书各完成 10 章
验证：
  - 3 本书 chapter_passed event 各 10 条
  - 真相文件各更新 ≥ 10 次
  - 风格漂移 < 阈值
  - 无 hard_rule_violation
  - 用户在第 3 章触发过 user_review
```

**Scenario B**：长跑期伏笔回收
```
前置：一本书已跑到第 50 章
执行：手动创建一个 deadline=55 的伏笔
等待：5 章后
验证：
  - foreshadow_overdue event 出现
  - Planner 在下章 beat plan 中包含"回收伏笔"
  - 实际章节中体现回收
  - foreshadow_recovered event 出现
```

**Scenario C**：用户改稿学习
```
前置：第 30 章已通过审稿
执行：用户在 StudioPage 把"风轻轻吹过"改为"风像剃刀刮过"，保存定稿
等待：finalize 钩子触发
验证：
  - style_rule 表新增 1 条 diction 类规则
  - 第 31 章 Writer prompt 中包含该规则
  - 第 31 章生成的正文偏好锐利意象
```

### 12.3 性能基线

| 指标 | 目标 |
|---|---|
| 单章生产时延 P50 | ≤ 90s |
| 单章生产时延 P95 | ≤ 180s |
| event_store.append 时延 | ≤ 10ms |
| event_store.get_events 时延 | ≤ 50ms |
| 内存占用（3 本并发）| ≤ 2 GB |
| 数据库大小（1 本 300 章）| ≤ 500 MB |

---

## 13. 引用与衍生

- Anthropic Engineering, *Scaling Managed Agents: Decoupling the brain from the hands* ([blog](https://www.anthropic.com/engineering/managed-agents))
- 本项目分析文档：`@d:\13250\桌面\managed-agents-architecture-analysis.md`
- 当前 autopilot 实现：`@d:\13250\桌面\NovelForgeX\backend\app\services\creation\autopilot.py`
- 当前墨语实现：`@d:\13250\桌面\NovelForgeX\backend\app\services\inspiration\engine.py`

---

## 14. 决策日志

| 日期 | 决策 | 理由 |
|---|---|---|
| 2026-05-12 | 不重写 autopilot.py | 保留可回退路径，新功能在新命名空间 |
| 2026-05-12 | Event 表用 SQLite JSON1 | 单用户场景够用，不必上 Postgres |
| 2026-05-12 | 墨语用 Gemini Flash | 调度类任务，小模型够用，节省成本 |
| 2026-05-12 | 责编用 Sonnet 而非 Opus | 审稿对成本敏感，Sonnet 判断力足够 |
| 2026-05-12 | 写作仍用 Opus | 创作质量是核心壁垒 |
| 2026-05-12 | 不引入 Celery/RQ | asyncio + asyncio.Queue 单进程方案够用 |

---

**End of RFC**
