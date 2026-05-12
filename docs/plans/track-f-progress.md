# Track F · 进度看板

> 多 Claude 协作时，每个 Claude 开工前必读、完工时必更新本文件。
> Coordinator（人）通过本文件追踪 9 路并行进度。

---

## 状态图例

- 🔵 `pending` - 未开始
- 🟡 `in_progress` - 进行中
- 🟢 `done` - 已合并
- 🔴 `blocked` - 被依赖项阻塞
- ⚠️ `failed` - 需要重做

---

## Phase 1 · 地基（2 路并行）

| Claude | 任务 | 分支 | 状态 | PR | 完成时间 | 备注 |
|---|---|---|---|---|---|---|
| **A** | editor_mode + hard_rules + 审稿 API | `feat/track-f/week1-editor-mode` | 🟢 merged | `bd08c28` | 2026-05-12 | Cascade 接手完成。63/63 测试通过 |
| **B** | event_store + Event/Session 表 + 迁移 | `feat/track-f/week2-event-store` | 🟢 merged | `6ba3d83` | 2026-05-12 | Cascade 接手完成。22/22 测试 + alembic 三连过 |

**Phase 1 验收标准（全部 ✅）**：
- ✅ A 和 B 两个 PR 都已 review + merge 到 `main` (commit `bec4415`)
- ✅ `POST /api/v1/managed/books/{bid}/chapter/{n}/review` 跑通（支持可选 `session_id` 自动写事件）
- ✅ `GET /api/v1/managed/books/{bid}/events?session_id=…&limit=…&types=…` 跑通
- ✅ `POST /api/v1/managed/books/{bid}/sessions` 创建 session
- ✅ 91/91 联合测试全过（hard_rules 35 + managed_editor 28 + event_store 22 + e2e 6）

---

## Phase 2 · 运行时（依赖 Phase 1）

| Claude | 任务 | 分支 | 状态 | PR | 完成时间 | 备注 |
|---|---|---|---|---|---|---|
| **C** | book_daemon + daemon_pool + llm_quota | `feat/track-f/week3-daemon` | � merged | TBD | 2026-05-12 | Cascade 接手实现。36/36 测试 + alembic 三连过 |

**Phase 2 验收标准（全部 ✅）**：
- ✅ `BookState` 模型 + alembic 迁移 `b2c3d4e5f6a7`
- ✅ `LLMQuotaScheduler` 支持容量 / per-book / 优先级 / 时间窗口
- ✅ `BookProductionDaemon` 完整生命周期 + 事件钩子 + 心跳
- ✅ `DaemonPool` 多书并发 + spawn/pause/resume/stop/list/shutdown
- ✅ HTTP API: `POST /managed/books/{bid}/daemon/{start,pause,resume,stop}`, `GET /managed/books/{bid}/state`, `GET /managed/daemons`
- ✅ 36/36 测试全过（llm_quota 10 + book_daemon/pool 15 + http e2e 11）
- ✅ 全仓回归 202/202 通过（含 75 个老测试）

---

## Phase 3 · 角色层（依赖 Phase 2）

| Claude | 任务 | 分支 | 状态 | PR | 完成时间 | 备注 |
|---|---|---|---|---|---|---|
| **D** | managing_editor 责编 agent | `feat/track-f/week4-editor` | 🔵 pending | – | – | – |
| **E** | editor_in_chief 总编人格 | `feat/track-f/week4-eic` | 🔵 pending | – | – | – |

---

## Phase 4 · 长程审核 + 学习（4 路并行，依赖 Phase 3）

| Claude | 任务 | 分支 | 状态 | PR | 完成时间 | 备注 |
|---|---|---|---|---|---|---|
| **F** | foreshadow_auditor 伏笔审计 | `feat/track-f/week5-foreshadow` | 🔵 pending | – | – | – |
| **G** | character_arc_auditor 人物弧线 | `feat/track-f/week5-character-arc` | 🔵 pending | – | – | – |
| **H** | theme_drift_auditor 主题漂移 | `feat/track-f/week5-theme-drift` | 🔵 pending | – | – | – |
| **I** | diff_learner 学习闭环 | `feat/track-f/week6-diff-learner` | 🔵 pending | – | – | – |

---

## Open Questions（待 Coordinator 决定）

> 各 Claude 实施过程中遇到的契约外问题集中放这里。Coordinator 答复后由对应 Claude 落地。

_（暂无）_

---

## Cross-Cutting Issues（跨模块 issue）

> 不属于单个 Claude，需要协调的事项。

_（暂无）_

---

## 已合并 PR 清单

_（合并后从对应 Phase 表移到这里）_

---

## 关键时间节点

| 时间 | 里程碑 |
|---|---|
| 2026-05-12 | Track F 启动 |
| TBD | Phase 1 完成 |
| TBD | Phase 2 完成 |
| TBD | Phase 3 完成 |
| TBD | Phase 4 完成 |
| TBD | E2E 验收 |

---

## Claude 实例使用记录

| 实例 | 模型 | 启动时间 | 累计 token | 累计成本 |
|---|---|---|---|---|
| Claude-A | Opus 4.7 | – | – | – |
| Claude-B | Opus 4.7 | – | – | – |
| ... | | | | |

---

## 更新规则（每个 Claude 必读）

1. **开工前**：把自己负责的行从 `pending` 改成 `in_progress`，填启动时间
2. **遇到契约外问题**：写到 Open Questions 区，**停止写代码**，等 Coordinator 答复
3. **完工时**：
   - 状态改成 `done`
   - 填 PR 链接和合并时间
   - 把 PR 条目挪到"已合并 PR 清单"
4. **被阻塞时**：状态改成 `blocked`，备注写"等待 X"
5. **绝对禁止**：跨越自己的任务边界改其他 Claude 的代码
