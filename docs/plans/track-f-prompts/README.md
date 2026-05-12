# Track F · 多 Claude 派活手册

> 给"人作 Coordinator"模式的使用指南。
> 你（人）作为 Coordinator，按本手册开 Claude Code 实例并派活。

---

## 0. 一次性准备（开工前做一次）

### 0.1 确认环境

```powershell
cd d:\13250\桌面\NovelForgeX
git status                      # 应在 main 分支
git remote -v                   # 应指向 size0/aonarr
git pull origin main            # 拿到最新 RFC 和契约
```

### 0.2 必读文档（你自己也要看一遍）

- `@docs/plans/track-f-managed-agents.md` - RFC（已有）
- `@docs/plans/track-f-interfaces.md` - 接口契约（不可违反）
- `@docs/plans/track-f-progress.md` - 进度看板（实时更新）

### 0.3 安装 Claude Code（如果还没装）

```powershell
npm install -g @anthropic-ai/claude-code
# 或参考 https://docs.anthropic.com/en/docs/claude-code
```

---

## 1. Phase 1 启动（2 个 Claude 并行）

### 1.1 开第一个 Claude Code 窗口（Claude-A）

```powershell
# PowerShell 窗口 1
cd d:\13250\桌面\NovelForgeX
git checkout feat/track-f/week1-editor-mode
claude
```

进入 Claude Code 后，**逐字粘贴** `claude-A-editor-mode.md` 的内容作为开场 prompt。

### 1.2 开第二个 Claude Code 窗口（Claude-B）

```powershell
# 另起 PowerShell 窗口 2
cd d:\13250\桌面\NovelForgeX
git checkout feat/track-f/week2-event-store
claude
```

进入 Claude Code 后，**逐字粘贴** `claude-B-event-store.md` 的内容作为开场 prompt。

> ⚠️ **关键**：两个窗口必须用**不同的工作目录副本**，否则会互相覆盖文件。
> 推荐做法：用 `git worktree` 创建独立工作树（见 1.3）。

### 1.3 推荐做法：使用 git worktree（避免文件冲突）

```powershell
cd d:\13250\桌面\NovelForgeX

# 给 Claude-A 一个独立工作树
git worktree add ..\NovelForgeX-claude-A feat/track-f/week1-editor-mode

# 给 Claude-B 一个独立工作树
git worktree add ..\NovelForgeX-claude-B feat/track-f/week2-event-store

# 然后在不同窗口里：
# 窗口 1: cd ..\NovelForgeX-claude-A; claude
# 窗口 2: cd ..\NovelForgeX-claude-B; claude
```

完工后清理工作树：
```powershell
git worktree remove ..\NovelForgeX-claude-A
git worktree remove ..\NovelForgeX-claude-B
```

---

## 2. 你（Coordinator）的日常工作

### 2.1 监控进度

每 1-2 小时看一眼：
```powershell
# 在主目录
git fetch --all
git log --all --oneline --graph -20
```

或者看进度看板：
```powershell
notepad docs\plans\track-f-progress.md
```

### 2.2 Code Review

某个 Claude 完工后，你需要：

1. 拉取它的分支查看变更
   ```powershell
   git fetch origin feat/track-f/week1-editor-mode
   git checkout feat/track-f/week1-editor-mode
   git diff main
   ```

2. 跑测试
   ```powershell
   cd backend
   pytest tests/test_managed_editor.py -v
   ```

3. 验收（按 prompt 中的"完成标准"逐项检查）

4. 合并
   ```powershell
   git checkout main
   git merge feat/track-f/week1-editor-mode --no-ff -m "Merge: Track F Week 1 editor_mode"
   git push origin main
   ```

### 2.3 处理 Open Questions

如果某个 Claude 在 progress.md 提了问题：

1. 你看清楚问题
2. 在 progress.md 里答复
3. 通知对应 Claude（在它的窗口里说"看 progress.md 我答复了你的问题"）

### 2.4 处理冲突

如果两个 Claude 的 PR 冲突（不同分支改了同一文件）：

1. 先合并先完工的
2. 让后完工的 `git pull origin main` 解冲突
3. 必要时你帮它解（直接 edit 然后告诉它）

---

## 3. Phase 2-4 启动时机

不要急着开 9 个 Claude。**Phase 1 必须先完成**。

### Phase 2（Phase 1 合并后启动）

```powershell
git checkout main
git pull origin main
git checkout -b feat/track-f/week3-daemon
git push -u origin feat/track-f/week3-daemon

# 然后启动 Claude-C
```

### Phase 3（Phase 2 合并后启动）

可以同时启动 Claude-D 和 Claude-E。

### Phase 4（Phase 3 合并后启动）

可以同时启动 Claude-F、G、H、I（4 路并行）。

---

## 4. 一些实用技巧

### 4.1 让 Claude 明白它是谁

每次粘贴 prompt 后，先确认它"自我介绍"：

```
你：开始任务前，请先复述：你是谁？你的任务是什么？你必须遵守哪些契约？
```

如果 Claude 答错了，重新粘贴 prompt。

### 4.2 防止 Claude 越界

如果发现 Claude 改了不该改的文件：

```
你：停。检查 git diff，把不属于你任务范围的改动 revert 掉。
你的范围在 prompt 的"任务输出"段，不要越界。
```

### 4.3 进度卡住时

如果 Claude 卡住或绕圈：

```
你：暂停。把当前状态用 200 字总结给我。
你需要做什么？为什么卡住？
```

### 4.4 测试不通过时

```
你：测试失败的具体原因是什么？是契约不清晰，还是实现有 bug？
不要绕过测试，先弄清楚根因。
```

---

## 5. 资金 / Token 预估

按 Claude Opus 4.7 价格（$15/M input, $75/M output）粗估：

| Claude | 任务规模 | 估算 input | 估算 output | 估算成本 |
|---|---|---|---|---|
| A | editor_mode + hard_rules | 500K | 100K | ~$15 |
| B | event_store + 迁移 | 500K | 80K | ~$14 |
| C | daemon_pool | 400K | 60K | ~$11 |
| D | managing_editor | 600K | 100K | ~$17 |
| E | editor_in_chief | 400K | 80K | ~$12 |
| F | foreshadow | 300K | 60K | ~$9 |
| G | character_arc | 300K | 60K | ~$9 |
| H | theme_drift | 300K | 60K | ~$9 |
| I | diff_learner | 400K | 80K | ~$12 |
| | | **3.7M** | **680K** | **~$108** |

**实际可能 1.5-2 倍**（含 review 来回、测试调试）。**预算 $200-250**。

> 用 OpenRouter / Sonnet / 国内厂商可降至 1/3。

---

## 6. 紧急停止

任何时候发现失控：

```powershell
# 在所有 Claude Code 窗口里输入
你：紧急停止。不要再写任何代码。等我下一步指令。
```

然后回 main 看损失：
```powershell
git checkout main
# 各分支的工作还在，没合并的话不影响 main
```

---

## 7. 文件清单

本目录下的所有 Claude prompt：

| 文件 | 对应 Claude | Phase |
|---|---|---|
| `claude-A-editor-mode.md` | A | 1 |
| `claude-B-event-store.md` | B | 1 |
| `claude-C-daemon.md` | C | 2 (待生成) |
| `claude-D-managing-editor.md` | D | 3 (待生成) |
| `claude-E-editor-in-chief.md` | E | 3 (待生成) |
| `claude-F-foreshadow.md` | F | 4 (待生成) |
| `claude-G-character-arc.md` | G | 4 (待生成) |
| `claude-H-theme-drift.md` | H | 4 (待生成) |
| `claude-I-diff-learner.md` | I | 4 (待生成) |

> Phase 2-4 的 prompt 在 Phase 1 跑通后生成。
