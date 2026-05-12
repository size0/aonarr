# Track F · 接口契约

> 本文档定义 Track F 多 Claude 协作时各模块间的接口约定。
> **任何一个 Claude 实例都必须严格遵守这些接口**，违反契约的 PR 不予合并。
>
> 版本：v1.0 · 2026-05-12
> 状态：**冻结**（任何修改需要先在 progress.md 发起讨论并由 Coordinator 批准）

---

## 0. 通用规则

### 0.1 命名规范

- Python 包：`snake_case`
- 类：`PascalCase`
- 函数 / 方法：`snake_case`
- 常量：`UPPER_SNAKE_CASE`
- 事件类型：`snake_case`（如 `chapter_started`）
- 数据库表：`snake_case` 复数（如 `events`）

### 0.2 类型注解

- 所有公开方法 **必须** 有完整类型注解
- 使用 Python 3.10+ 语法（`list[X]` / `X | None`）
- 复杂返回值用 `pydantic.BaseModel` 或 `dataclass`

### 0.3 异步规则

- 所有 I/O 方法 **必须** 是 `async def`
- 数据库使用 `Session`（SQLAlchemy 2.0 风格）
- LLM 调用使用现有 `app.llm.client`

### 0.4 错误处理

- 业务异常继承自 `app.core.errors.NovelForgeError`
- 不要在 service 层捕获异常吞掉
- API 层负责把异常转成 HTTP 响应

---

## 1. EventStore 接口（Claude-B 实现）

### 1.1 数据模型

```python
# @backend/app/models/events.py

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class Event(Base):
    """append-only 事件流"""
    __tablename__ = "events"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    parent_session_id: Mapped[str | None] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(BigInteger)              # session 内有序
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    chapter_number: Mapped[int | None] = mapped_column(Integer, index=True)
    parent_event_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SessionRecord(Base):
    """生产 session 管理（注意类名避免和 SQLAlchemy Session 冲突）"""
    __tablename__ = "production_sessions"
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    book_id: Mapped[str] = mapped_column(String(64), index=True)
    parent_session_id: Mapped[str | None] = mapped_column(String(64))
    forked_at_event: Mapped[int | None] = mapped_column(BigInteger)
    branch_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))           # active/merged/abandoned
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime)
```

### 1.2 EventStore 类（Claude-B 必须实现）

```python
# @backend/app/services/events/event_store.py

from typing import AsyncIterator
from sqlalchemy.orm import Session
from app.models.events import Event, SessionRecord


class EventStore:
    """事件流读写器。线程安全：单 Session 内串行，多 Session 并发由 SQLite WAL 处理"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def append(
        self,
        book_id: str,
        session_id: str,
        event_type: str,
        actor: str,
        payload: dict,
        chapter_number: int | None = None,
        parent_event_id: int | None = None,
    ) -> int:
        """追加事件。返回新事件的 id。
        
        实现要求：
        - 自动计算 seq（同一 session 内自增）
        - 对同一 session 串行 append（用 with self.db.begin())
        - 失败时抛 EventStoreError
        - 时延 ≤ 10ms
        """
        ...
    
    async def get_events(
        self,
        book_id: str,
        session_id: str,
        from_seq: int = 0,
        limit: int = 100,
        types: list[str] | None = None,
        chapter_number: int | None = None,
    ) -> list[Event]:
        """切片读事件。
        
        实现要求：
        - 按 seq 升序返回
        - types 为空则返回所有类型
        - 时延 ≤ 50ms
        """
        ...
    
    async def get_latest(
        self,
        book_id: str,
        session_id: str,
        event_type: str,
    ) -> Event | None:
        """获取某 session 中某类型的最新一条事件"""
        ...
    
    async def fork_session(
        self,
        book_id: str,
        from_event_id: int,
        branch_name: str,
    ) -> str:
        """从某个事件 fork 出新 session。
        
        返回新 session_id。
        实现要求：
        - 新 session 的 parent_session_id = 原 session
        - 新 session 的 forked_at_event = from_event_id
        - 写入一条 session_forked 事件到原 session
        """
        ...
    
    async def stream(
        self,
        book_id: str,
        session_id: str,
        from_seq: int = 0,
        types: list[str] | None = None,
    ) -> AsyncIterator[Event]:
        """SSE 风格流式读取（轮询 + 增量），用于前端实时展示"""
        ...
```

### 1.3 EventStoreError

```python
# @backend/app/services/events/errors.py

from app.core.errors import NovelForgeError

class EventStoreError(NovelForgeError):
    """EventStore 通用异常"""
    pass

class SessionNotFoundError(EventStoreError):
    pass

class InvalidForkError(EventStoreError):
    pass
```

### 1.4 事件类型注册（Claude-B 必须建立此文件）

```python
# @backend/app/services/events/event_types.py

# 使用字符串常量，不用 Enum（便于动态扩展）

# === 章节生产 ===
CHAPTER_STARTED = "chapter_started"
BEAT_PLAN_COMPLETED = "beat_plan_completed"
WRITER_SPAWNED = "writer_spawned"
WRITER_PROGRESS = "writer_progress"
DRAFT_COMPLETED = "draft_completed"
EARLY_STOP_TRIGGERED = "early_stop_triggered"

# === 审核 ===
REVIEW_STARTED = "review_started"
REVIEW_COMPLETED = "review_completed"
HARD_RULE_VIOLATION = "hard_rule_violation"
REVISION_REQUESTED = "revision_requested"
REVISION_COMPLETED = "revision_completed"
CHAPTER_PASSED = "chapter_passed"
CHAPTER_REJECTED = "chapter_rejected"

# === 连续性 ===
OBSERVER_EXTRACTED = "observer_extracted"
TRUTH_FILE_UPDATED = "truth_file_updated"
FORESHADOW_PLANTED = "foreshadow_planted"
FORESHADOW_RECOVERED = "foreshadow_recovered"
FORESHADOW_OVERDUE = "foreshadow_overdue"
CHARACTER_STATE_UPDATED = "character_state_updated"

# === 跨章节审核 ===
VOLUME_REVIEW_STARTED = "volume_review_started"
VOLUME_REVIEW_COMPLETED = "volume_review_completed"
ARC_CONSISTENCY_CHECK = "arc_consistency_check"
THEME_DRIFT_ALERT = "theme_drift_alert"

# === 用户介入 ===
USER_DECISION_REQUESTED = "user_decision_requested"
USER_DECISION_RECEIVED = "user_decision_received"
USER_EDIT_APPLIED = "user_edit_applied"
USER_PREFERENCE_INFERRED = "user_preference_inferred"

# === Fork ===
SESSION_FORKED = "session_forked"
BRANCH_MERGED = "branch_merged"

# === 生命周期 ===
BOOK_CREATED = "book_created"
BOOK_PHASE_CHANGED = "book_phase_changed"

# Payload schema（pydantic 定义）见同目录下 event_payloads.py
```

### 1.5 Payload Schemas（必须）

```python
# @backend/app/services/events/event_payloads.py

from pydantic import BaseModel
from typing import Literal

class ChapterStartedPayload(BaseModel):
    chapter_number: int
    target_words: int
    triggered_by: str  # "autopilot" | "user" | "rewrite_request"

class DraftCompletedPayload(BaseModel):
    word_count: int
    draft_text: str  # 完整正文（可能很大，但必须存）
    elapsed_ms: int

class ReviewCompletedPayload(BaseModel):
    decision: Literal["pass", "revise", "rewrite", "ask_user"]
    overall_score: float
    dimensions: dict[str, float]
    summary: str
    annotation_count: int

class HardRuleViolationPayload(BaseModel):
    rule_id: str
    severity: Literal["info", "warning", "blocker"]
    evidence: str
    suggested_fix: str | None = None

class ForeshadowPlantedPayload(BaseModel):
    foreshadow_id: str
    description: str
    recovery_deadline: int  # 必须在第几章前回收

# ... 其他事件类型的 payload schema 类似定义 ...
```

---

## 2. MuyuEditor 接口（Claude-A 实现）

### 2.1 ReviewResult 数据结构

```python
# @backend/app/services/inspiration/editor_mode.py

from pydantic import BaseModel
from typing import Literal


class Annotation(BaseModel):
    location: dict           # {"paragraph": int, "char_range": [int, int]}
    category: Literal["consistency", "style", "pacing", "foreshadow", "hard_rule", "dialogue", "ai_taste", "structure"]
    severity: Literal["info", "warning", "blocker"]
    issue: str
    suggestion: str | None = None
    evidence: list[dict] = []      # 引用证据（其他章节 / 真相文件）
    auto_fixable: bool = False


class NextAction(BaseModel):
    action: Literal["pass", "trigger_revision", "trigger_rewrite", "ask_user", "escalate"]
    target: str | None = None      # 比如 "revision_loop" / "writer_agent"
    payload: dict = {}             # 具体参数


class ReviewResult(BaseModel):
    decision: Literal["pass", "revise", "rewrite", "ask_user"]
    overall_score: float           # 0-100
    dimensions: dict[str, float]   # 10 维质量评分
    summary: str                   # 编辑总评（≤ 200 字）
    annotations: list[Annotation]
    next_action: NextAction
    elapsed_ms: int
    tokens_used: int
```

### 2.2 MuyuEditor 类

```python
class MuyuEditor:
    """墨语主编 - 编辑模式"""
    
    def __init__(self, db: Session, event_store: EventStore | None = None):
        """event_store 可选，第 1 周可暂时为 None（打桩）"""
        self.db = db
        self.event_store = event_store
    
    async def review_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        session_id: str | None = None,
    ) -> ReviewResult:
        """对某章进行全维度审稿。
        
        实现要求：
        1. 必须并发跑：quality_radar / consistency_checker / style_drift_detector
        2. 必须先跑 hard_rules（任一 blocker 直接 decision=rewrite，跳过 LLM）
        3. LLM 综合判断时必须用 EDITOR_SYSTEM prompt
        4. 输出严格符合 ReviewResult schema
        5. 如果 event_store 不为 None，必须 append 以下事件：
            - review_started
            - hard_rule_violation（如有）
            - review_completed
        6. 全过程时延 ≤ 30 秒
        """
        ...
    
    async def review_chapter_streaming(
        self,
        novel_id: str,
        chapter_number: int,
        session_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """流式审稿（用于前端实时展示）。
        
        yield 内容：
        - {"type": "stage", "name": "running_quality_radar"}
        - {"type": "stage", "name": "running_consistency"}
        - {"type": "annotation", "data": {...}}
        - {"type": "result", "data": {ReviewResult}}
        """
        ...
```

### 2.3 EDITOR_SYSTEM Prompt（Claude-A 自由发挥但必须包含以下结构）

```python
EDITOR_SYSTEM = """你是「墨语」—— 这本书的责任编辑。

## 你的身份与职责
[详见 RFC 第 5.1 节]

## 你的工具输出
你将收到以下来自其他 worker 的输出：
{tool_outputs}

## 章节草稿
{draft_text}

## 全局上下文
- 真相文件相关条目：{truth_file_excerpts}
- 最近 10 章摘要：{recent_summaries}
- 已激活伏笔：{active_foreshadows}
- 风格基线指纹：{style_fingerprint}
- 用户偏好规则：{user_style_rules}

## 你的输出格式
严格按以下 JSON 输出（不要多余字段）：
{review_result_schema}
"""
```

---

## 3. HardRules 接口（Claude-A 实现）

```python
# @backend/app/services/audit/hard_rules.py

from typing import Callable
from dataclasses import dataclass


@dataclass
class HardRuleContext:
    """传给 hard rule 检查函数的上下文"""
    novel_id: str
    chapter_number: int
    draft_text: str
    truth_file: dict           # 已编译的真相文件
    active_foreshadows: list[dict]
    expected_word_range: tuple[int, int]


@dataclass
class HardRuleViolation:
    rule_id: str
    severity: Literal["info", "warning", "blocker"]
    evidence: str
    suggested_fix: str | None


@dataclass
class HardRule:
    id: str
    description: str
    category: str
    severity: Literal["info", "warning", "blocker"]
    check: Callable[[HardRuleContext], HardRuleViolation | None]


# 内置规则集（必须实现至少这 6 条）
HARD_RULES: list[HardRule] = [
    # 1. protagonist_name_immutable
    # 2. chapter_word_range
    # 3. timeline_monotonic（暂可简化）
    # 4. dead_character_stays_dead
    # 5. foreshadow_recovery_deadline
    # 6. no_outline_skip
]


def run_hard_rules(ctx: HardRuleContext) -> list[HardRuleViolation]:
    """跑全部规则，返回违反的清单（空列表 = 全过）"""
    ...
```

---

## 4. ManagingEditor 接口（Claude-D 实现）

> **注意**：第 4 周才会用到。Claude-A/B 阶段不需要实现，但要遵守这里定义的接口。

```python
# @backend/app/services/agents/managing_editor.py

class ManagingEditor:
    """单本书的责编 agent"""
    
    def __init__(
        self,
        db: Session,
        event_store: EventStore,
        book_id: str,
    ):
        ...
    
    async def bootstrap_book(self) -> None:
        """立项后生成大纲/世界观/角色卡/真相文件"""
        ...
    
    async def produce_chapter(self, chapter_number: int) -> ReviewResult:
        """单章生产（编排任务图）"""
        ...
    
    async def run_periodic_audits(self, current_chapter: int) -> list[dict]:
        """周期性审计（每 5/10/20 章触发）"""
        ...
    
    async def generate_report(self) -> str:
        """出书报给总编（≤ 500 字摘要）"""
        ...
```

---

## 5. 共享：路由命名空间

所有 Track F 新增 API 必须挂在 `/managed/` 命名空间下：

```python
# @backend/app/routes/managed.py
from fastapi import APIRouter

router = APIRouter(prefix="/managed", tags=["managed-agents"])

# 由 Claude-A 添加
@router.post("/books/{book_id}/chapter/{n}/review")
async def review_chapter(...): ...

# 由 Claude-B 添加
@router.get("/books/{book_id}/events")
async def get_events(...): ...

# 后续 Claude 添加更多端点
```

**注册位置**：`@backend/app/main.py` 中加：
```python
from app.routes.managed import router as managed_router
app.include_router(managed_router, prefix="/api/v1")
```

---

## 6. 共享：测试约定

### 6.1 测试目录结构

```
@backend/tests/
├── test_managed_editor.py       # Claude-A 写
├── test_event_store.py          # Claude-B 写
├── test_hard_rules.py           # Claude-A 写
├── test_managing_editor.py      # Claude-D 写
└── ...
```

### 6.2 测试数据 fixture

每个 Claude 必须使用 `@backend/tests/conftest.py` 中的现有 fixture：
- `db` - 测试数据库 session
- `sample_novel` - 一个完整的测试小说
- `sample_chapter` - 一个测试章节

如需新增 fixture，加在 `conftest.py` 而不是各自测试文件里。

### 6.3 覆盖率门槛

| 模块 | 最低覆盖率 |
|---|---|
| event_store | 90% |
| hard_rules | 100% |
| editor_mode | 80% |
| managing_editor | 70% |

---

## 7. 共享：依赖管理

### 7.1 不允许新增大型依赖

未在 `backend/pyproject.toml` 中的依赖必须在 progress.md 申请。

### 7.2 允许使用的标准库

- `pydantic` (已有)
- `sqlalchemy` (已有)
- `fastapi` (已有)
- `asyncio`
- `typing`
- `dataclasses`

---

## 8. Coordinator 仲裁规则

当多 Claude 出现接口分歧时：

1. **以本契约为准**——严格按本文件描述实现
2. **本文件没写到的**——以 RFC（`@docs/plans/track-f-managed-agents.md`）为准
3. **RFC 也没写到的**——在 `@docs/plans/track-f-progress.md` 的 "Open Questions" 区提问，等待 Coordinator（人）决定
4. **绝对禁止**：自己脑补一个接口然后实现

---

## 9. 版本变更记录

| 日期 | 版本 | 修改内容 | 修改人 |
|---|---|---|---|
| 2026-05-12 | v1.0 | 初版冻结 | Coordinator |
