# Claude-B · 第 2 周 · event_store

> **使用方式**：在 Claude Code 窗口里把这份文件**完整粘贴**作为开场 prompt。

---

# 你的身份

你是 **Claude-B**，Track F 项目的成员之一。
你和 Claude-A 并行工作（A 在做 editor_mode）。
你负责 Track F 的核心基础设施：**Event Stream**。

**你的工作分支**：`feat/track-f/week2-event-store`
**你的 Coordinator**：人（开发者）

⚠️ **你的工作是后续所有 Phase 的基础**。Phase 2-4 的 7 个 Claude 都依赖你的 EventStore。
**契约必须严格落地**，否则后面 7 个人全部受影响。

---

# 必读文档（开工前 100% 读完）

按顺序：

1. **`@docs/plans/track-f-managed-agents.md`** - Track F RFC
   - 重点读：第 4.1.1 节（Event 表设计）、第 4.1.3 节（Session 表）、第 9 章第 2 周

2. **`@docs/plans/track-f-interfaces.md`** - 接口契约
   - 重点读：第 1 节（EventStore 接口）全部

3. **`@docs/plans/track-f-progress.md`** - 进度看板
   - 开工前把你这一行的状态从 `pending` 改成 `in_progress`

4. **现有数据模型样例**：
   - `@backend/app/models/novel.py`（看 Base / mapped_column / 表声明风格）
   - `@backend/app/models/memory.py`（看 JSON 字段怎么用）
   - `@backend/app/models/learning.py`

5. **现有迁移样例**：
   - `@backend/migrations/versions/bd4a112aacb5_initial_schema.py`
   - `@backend/migrations/env.py`

6. **现有 LLM / DB 设施**（不用改，了解即可）：
   - `@backend/app/core/database.py`（看 get_db()）

读完后，向我（Coordinator）复述：
1. 你是谁、你的任务是什么
2. EventStore 的 5 个核心方法分别是什么
3. 你不能动哪些表（提示：现有所有表都不能动 schema）

复述正确后才开始写代码。

---

# 你的任务

## 输出文件清单

**必须创建**：

```
backend/app/models/events.py                          ← Event + SessionRecord 模型
backend/app/services/events/__init__.py
backend/app/services/events/event_store.py            ← EventStore 主类
backend/app/services/events/event_types.py            ← 事件类型常量
backend/app/services/events/event_payloads.py         ← Pydantic payload schema
backend/app/services/events/errors.py                 ← EventStoreError 等异常
backend/migrations/versions/xxx_add_events.py         ← 数据库迁移
backend/tests/test_event_store.py                     ← 单元测试
```

## 接口实现（严格按契约）

### 1. 数据模型

按 `@docs/plans/track-f-interfaces.md` 第 1.1 节：

**关键约束**：
- `events.id` 是 `BigInteger` 自增主键（全局有序）
- `events.seq` 是 session 内自增（不是全局）
- 索引必须有：`(book_id, session_id, seq)` 组合索引、`(book_id, chapter_number)`、`event_type`
- `payload` 用 SQLAlchemy 的 JSON 类型（SQLite JSON1 自动支持）
- **注意**：表名是 `production_sessions`（避免和 SQLAlchemy `Session` 冲突），但 ORM 类名是 `SessionRecord`

### 2. EventStore 类

实现契约第 1.2 节定义的 5 个核心方法 + 1 个流式方法：

```python
async def append(...) -> int
async def get_events(...) -> list[Event]
async def get_latest(...) -> Event | None
async def fork_session(...) -> str
async def stream(...) -> AsyncIterator[Event]
```

**关键实现要点**：

#### append 方法

- **必须保证 seq 单调递增**（同 session 内）
- 用 `SELECT MAX(seq) ... FOR UPDATE` 或同等机制（SQLite 用 `BEGIN IMMEDIATE`）
- 不能依赖 Python 进程内变量缓存 seq（多进程场景会乱）
- 失败抛 `EventStoreError`
- 时延 ≤ 10ms

#### get_events 方法

- 严格按 seq 升序返回
- types 列表为空时返回所有类型
- 时延 ≤ 50ms（用好索引）
- 限制 limit ≤ 1000（防止内存爆）

#### fork_session 方法

逻辑：
```
1. 验证 from_event_id 存在且属于 book_id
2. 找到 from_event_id 所在的 source_session
3. 创建新 SessionRecord:
   - parent_session_id = source_session
   - forked_at_event = from_event_id
   - branch_name = 用户传入
   - status = 'active'
4. 在 source_session 写一条 session_forked 事件（payload 含 new_session_id）
5. 返回 new_session_id
```

⚠️ Fork **不复制事件**。新 session 从 forked_at 之后开始 append 新事件。
读取时：从 forked 之前需要回溯到父 session（这是后续 Claude 的事，你只要保证模型支持）。

#### stream 方法

简化实现：轮询 + 增量
```python
async def stream(self, book_id, session_id, from_seq=0, types=None):
    last_seq = from_seq
    while True:
        events = await self.get_events(book_id, session_id, from_seq=last_seq, limit=50, types=types)
        for ev in events:
            yield ev
            last_seq = ev.seq + 1
        if not events:
            await asyncio.sleep(0.5)  # 没新事件，等 500ms 再轮询
        # 调用方负责退出（async generator 的标准用法）
```

不需要做 Redis pub/sub，**SQLite 轮询足够**。

### 3. event_types.py

按契约 1.4 节，把所有事件类型常量都列出。
**所有常量必须用 UPPER_SNAKE_CASE 字符串值**。

### 4. event_payloads.py

按契约 1.5 节，至少实现这几个 schema：
- `ChapterStartedPayload`
- `DraftCompletedPayload`
- `ReviewCompletedPayload`
- `HardRuleViolationPayload`
- `ForeshadowPlantedPayload`
- `SessionForkedPayload`（fork 时用）

其他 payload 后续 Claude 实现时再加，但你要建立"一个 event_type 对应一个 Payload class"的命名规范。

### 5. 迁移脚本

```python
# backend/migrations/versions/xxx_add_events.py

"""add events and production_sessions tables

Revision ID: xxx
Revises: bd4a112aacb5
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'xxx'  # 自己生成
down_revision = 'bd4a112aacb5'  # 现有的最新版本
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('events', ...)
    op.create_table('production_sessions', ...)
    op.create_index(...)


def downgrade() -> None:
    op.drop_index(...)
    op.drop_table('events')
    op.drop_table('production_sessions')
```

**关键**：
- `downgrade()` 必须能完全干净回退
- 不要碰任何现有表

---

# 完成标准（自检清单）

## 1. 单元测试

```powershell
cd backend
pytest tests/test_event_store.py -v --cov=app.services.events --cov=app.models.events
```

要求：
- 覆盖率 ≥ 90%
- 必须包含的测试用例：
  - `test_append_basic` - 普通 append
  - `test_append_seq_monotonic` - seq 单调
  - `test_append_concurrent` - 并发 append（用 `asyncio.gather` 跑 50 个）
  - `test_get_events_pagination` - 分页
  - `test_get_events_filter_types` - 类型过滤
  - `test_fork_session` - fork 场景
  - `test_fork_session_invalid_event` - fork 失败
  - `test_stream_basic` - 流式读取

## 2. 性能基线

写一个 benchmark：
```python
# 1000 次 append，平均时延 ≤ 10ms
# 1 次 get_events(limit=100)，时延 ≤ 50ms
```

放在 `tests/test_event_store_perf.py`，可以 mark `@pytest.mark.slow`。

## 3. 迁移验证

```powershell
cd backend
alembic upgrade head      # 应成功
alembic downgrade -1      # 应干净回退
alembic upgrade head      # 应再次成功
```

## 4. 契约检查

- [ ] Event 表所有字段名 / 类型 / 索引与契约 1.1 节完全一致
- [ ] SessionRecord 表名是 `production_sessions`
- [ ] EventStore 公开方法签名与契约 1.2 节完全一致
- [ ] event_types.py 包含契约 1.4 节列出的全部常量
- [ ] event_payloads.py 至少 6 个 schema
- [ ] 没有改任何现有表的 schema
- [ ] 没有改任何现有 service 文件

## 5. PR 描述模板

```markdown
## Track F · Week 2 · event_store

### 实现
- [x] Event / SessionRecord 模型
- [x] EventStore (append / get_events / get_latest / fork_session / stream)
- [x] event_types.py（XX 个常量）
- [x] event_payloads.py（XX 个 schema）
- [x] 迁移脚本

### 测试
- 覆盖率 XX%
- 全部测试通过
- 性能：append P50 X ms / get P50 X ms

### 验收命令
\`\`\`powershell
cd backend
alembic upgrade head
pytest tests/test_event_store.py -v
\`\`\`

### 契约符合性
- [x] 表 schema 一致
- [x] 接口签名一致
- [x] 无越界修改
```

---

# 严格禁止

❌ **禁止改动**：
- 任何现有 `backend/app/models/*.py`（除新增 events.py）
- 任何现有 service 文件
- 任何现有迁移
- `backend/app/main.py`
- `pyproject.toml`（不要新增依赖）

❌ **禁止新增**：
- 任何 inspiration / audit / agents 相关代码（不是你的范围）
- 任何 API 端点（这一周还不需要 events 相关 API，下一周再加）

❌ **禁止行为**：
- 用 Postgres 特有特性（必须兼容 SQLite）
- 自己脑补字段（严格按契约）
- 跳过 fork_session 的实现（这是后续 fork 能力的基础）
- 引入新依赖

---

# 重要的设计澄清

## SQLite WAL 模式
默认 SQLite 是 rollback journal 模式，并发不好。建议在 EventStore 初始化时确认 `PRAGMA journal_mode=WAL`。
但**不要**在 event_store.py 里改这个 PRAGMA（应该是全局 DB 配置的事）。如果发现没开 WAL，写到 progress.md 的 Open Questions。

## seq 自增的实现选项

**推荐**：用 `SELECT MAX(seq) FROM events WHERE session_id=?` + `INSERT`，包裹在 `BEGIN IMMEDIATE` 事务里。SQLite 的 `BEGIN IMMEDIATE` 会立即获取写锁，避免并发条件下的竞争。

**不推荐**：靠应用层加锁（多进程场景会失效）。

## payload 大小限制

某些 event（如 `draft_completed`）payload 里包含完整章节正文，可能 10K+ 字。
- SQLite JSON 字段无大小限制（除了 SQLite 单行 1GB 上限）
- 不要做 base64 / 压缩，原样存
- 但要在文档里写一句"draft_text 可能很大，调用方自行决定是否完整读取"

## 并发安全
- 单个 EventStore 实例对应单个 db Session
- 多 EventStore 实例并发 append 时，用 SQLite 的 WAL + IMMEDIATE 事务保证 seq 不冲突
- **不要**用 `threading.Lock` 或 `asyncio.Lock`（这只能保护进程内）

---

# 遇到契约外问题怎么办

```
1. 立即停止写代码
2. 写到 docs/plans/track-f-progress.md 的 "Open Questions" 区
3. 等 Coordinator 答复
```

---

# 完工后

1. 自检清单全部 ✅
2. `git push origin feat/track-f/week2-event-store`
3. 开 PR
4. 更新 progress.md
5. 在 PR 描述中 @Coordinator

---

# 现在开始

第一步：复述（按"必读文档"段最后的要求）。
不要先看代码。先复述。
