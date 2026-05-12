# NovelForgeX 竞品分析 and 借鉴计划

> 2026-05-07 分析 7 个开源项目，提炼可落地的升级计划

---

## 一、竞品分析

### 1. xkhanhan/novel (Webnovel Writer)
架构: Claude Code 插件，文件系统 + SQLite，4个Agent

可借鉴:
- Reviewer AI味5子维度检测（词汇层/句式层/叙事层/情感层/对话层）
- Anti-AI 7条高维规则（删段末感悟/删万能副词/情绪用生理反应/对话潜台词/节奏疏密/章末禁安全着陆/展示不解释）
- Context-Agent 5段结构化任务书格式
- Deconstruction-Agent 拆书系统（快速/深度模式 + 情节点提取 + 质量门控 + 抽象转化规则）
- 37个题材模板（比我们11个多）

### 2. worldwonderer/oh-story-claudecode
架构: Claude Code Skill包，长篇+短篇全流程

可借鉴:
- 扫榜系统：结构化分析榜单数据（不只是爬取）
- 拆文全流程：黄金三章分析 + 爽点循环提取 + 节奏地图
- 去AI味完整管线：写作提示 -> 生成 -> 检测 -> 多轮打磨（不只是单步后处理）
- 是 xkhanhan/novel 的灵感来源

### 3. xindoo/ai-novel-lab
架构: Kilo Code + DeepSeek，100章43万字实战验证

可借鉴:
- 爽文核心逻辑：黄金三章情绪流 + 绝对主角中心 + 一致性爽感
- 写前强制记忆检索（search_story_memory 查人物/道具/伏笔）
- 宏观一致性（全局设定+大纲锁定）vs 微观一致性（逐章细节校验）分离
- 实战5大坑：3-5章后AI主动停止、连写多章质量下降、字数失控、上下文断裂、真实人名泄露

### 4. jiaw-Zh/long-novel-writer (herozhong0125/Long-Novel-Writer)
架构: 长篇小说创作工具

可借鉴:
- 长篇连贯性管理的具体实现（GitHub不可达，信息有限）

### 5. veiller/AINovel
GitHub不可达，信息不足

### 6. zz9744813-lab/novel-hub
GitHub不可达，信息不足

### 7. RyenLee/inovel
GitHub不可达，信息不足

---

## 二、NovelForgeX 现状对比

| 能力维度 | NovelForgeX 现状 | 差距 |
|---------|-----------------|------|
| AI味检测 | quality_radar 的 ai_detect 维度（疲劳词+禁用句式） | 缺 5 子维度深度检测 |
| 去AI味 | anti_detect.py 单步后处理 + LLM改写 | 缺写前注入+生成约束+多轮打磨管线 |
| 拆书学习 | hot_crawler 爬取+存储 | 完全没有拆书分析能力 |
| 写前检索 | Observer + MemoryRetriever + ContextBuilder | 非强制，无校验门控 |
| 爽感工程 | 无 | 缺爽点循环/黄金三章/情绪流设计 |
| 题材覆盖 | 11个 ThemeAgent | 竞品有37个 |
| 任务书格式 | ContextBuilder + template_vars | 缺结构化5段任务书 |
| 宏微观一致性 | FACT_LOCK + story_log | 未分层，无强制校验 |

---

## 三、借鉴落地计划

### Phase A: AI味对抗升级（优先级最高，直接影响产出质量）

#### A1. quality_radar 的 ai_detect 拆分为 5 子维度
文件: `backend/app/services/audit/quality_radar.py`

把当前的单一 ai_detect 维度拆分为:
- vocab_ai: 词汇层（AI高频词密度、万能副词结构、神态模板）
- syntax_ai: 句式层（四段闭环、同构句连续、段末总结句、重复信息）
- narrative_ai: 叙事层（匀速节奏、戏剧性反讽提示、安全着陆、展示后解释）
- emotion_ai: 情感层（标签化情绪、即时切换、模板化反应）
- dialogue_ai: 对话层（信息宣讲、全员书面语、对白后解释）

每个子维度独立评分 0-100，各有 severity 阈值。总 ai_detect 为加权平均。

#### A2. Anti-AI 写前规则系统化
文件: `backend/app/services/audit/anti_detect.py`

新增 `advanced_prompt_rules()` 函数，输出 7 条高维规则:
1. 删段末感悟句 —— 留余味，不做闭环
2. 删万能副词（缓缓/淡淡/微微）—— 换具体动作
3. 情绪用生理反应+微动作 —— 禁止"他感到X"
4. 对话带潜台词和意图冲突 —— 有抢话/沉默/答非所问
5. 制造节奏疏密对比 —— 有的段落只一句话
6. 章末禁止安全着陆 —— 留未解决的问题
7. 展示后不解释 —— show dont tell

注入 ChapterWriter._build_system_prompt() 的叙事铁律部分。

#### A3. 去AI味多轮管线
文件: `backend/app/services/audit/anti_detect.py`

新增 `multi_pass_deai(text, max_rounds=3)`:
- Round 1: 正则后处理（疲劳词/禁用句式/同构句）
- Round 2: 5子维度检测，定位问题句段
- Round 3: LLM 定向改写（只改问题句，保持上下文）
- 每轮后重新评分，达标即停

### Phase B: 拆书学习系统（填补最大空白）

#### B1. 拆书服务 book_deconstructor.py
文件: `backend/app/services/learning/book_deconstructor.py`

核心功能:
- 快速模式: 黄金三章拆解（前3章钩子/爽点/节奏/承接）
- 深度模式: 逐章情节点提取 -> 聚合为剧情条 -> 角色分级 -> 爽点循环识别
- 抽象转化: 提取可迁移模式（条件框架/情绪链条），不复制原作事实
- 输出: structured JSON (init_reference_research)

#### B2. 拆书 API
文件: `backend/app/api/learning.py`

- POST /novels/{novel_id}/learning/deconstruct — 提交拆书任务
- GET /novels/{novel_id}/learning/deconstruct/{task_id} — 获取拆书结果
- POST /novels/{novel_id}/learning/apply-patterns — 将可迁移模式应用到当前项目

#### B3. 爬取数据与拆书打通
修改 hot_crawler.py，爬取后自动触发快速拆书（黄金三章分析），
结果存入 HotNovel 的 analysis_json 字段。

### Phase C: 爽感工程（提升商业竞争力）

#### C1. 爽点循环引擎
文件: `backend/app/services/creation/coolness_engine.py`

实现四层爽点循环:
- 蓄力层: 压迫/铺垫/制造期待
- 释放层: 反转/打脸/升级/底牌亮出
- 反应层: 围观震惊/敌人恐惧/利益落袋
- 衔接层: 新问题/新危机/钩子

与现有的节拍系统（beat）集成:
- _get_default_beats() 增加 coolness_type 字段
- 大纲规划时自动标注每章的爽感定位（蓄力/爆发/收割）

#### C2. 黄金三章强化
修改大纲规划 prompt（outline_planning 阶段）:
- 第1章: 前500字钩子 + 主角第一印象 + 世界观铺设 + 章尾钩子
- 第2章: 冲突升级 + 信息密度提高 + 爽点间隔控制
- 第3章: 核心矛盾锁定 + 金手指首次展示 + 留人钩子

#### C3. 情绪流标注
PostPipeline 新增情绪弧线提取:
- 每章标注情绪走向: 压抑->爆发->余波
- tension_ecg 图表增加情绪层叠加显示

### Phase D: 写前校验门控（防止一致性崩坏）

#### D1. 强制记忆检索
修改 ChapterWriter.generate_chapter_stream():
- 写前自动查询: 本章涉及角色的当前状态/境界/关系
- 查询: 活跃伏笔的到期状态
- 查询: 上章结尾钩子（必须回应）
- 结果注入 FACT_LOCK 块

#### D2. 宏/微观一致性分离
宏观层（不变）:
- 全局设定、世界观、力量体系、核心大纲
- 存储: Novel.bible_json + WorldItem

微观层（逐章校验）:
- 角色境界/装备/关系变化
- 时间线连续性
- 伏笔回应状态
- 新增: pre_write_check() 函数，写前自动校验微观一致性

#### D3. 结构化任务书
修改 ContextBuilder.build() 输出格式:
1. 开篇委托: 书名/章号/标题/一句话目标
2. 本章故事: 前文摘要 + 本章目标/阻力 + 情节节点 + 跨章约束
3. 本章人物: 每人状态/驱动力/本章作用/说话倾向
4. 写法指导: 风格/节奏策略 + anti-AI提醒 + 审查趋势
5. 收在哪里: 结尾感觉 + 未完感

### Phase E: 题材扩展（锦上添花）

#### E1. ThemeAgent 扩展到 25+
从竞品的37个题材中选取高频的补充:
- 末日/废土、灵异/恐怖、体育、职场、军事、农村、医疗、娱乐圈、直播、盗墓、美食、校园、二次元、系统流

---

## 四、执行优先级

| 阶段 | 任务 | 预估工时 | 价值 |
|------|------|---------|------|
| A1 | AI味5子维度检测 | 3h | 直接提升检测精度 |
| A2 | Anti-AI写前7条规则 | 1h | 立即降低AI检出率 |
| A3 | 去AI味多轮管线 | 3h | 从57%降到30%以下 |
| B1 | 拆书服务核心 | 5h | 填补最大空白 |
| B2 | 拆书API | 1h | |
| B3 | 爬取与拆书打通 | 2h | |
| C1 | 爽点循环引擎 | 4h | 提升商业质量 |
| C2 | 黄金三章强化 | 2h | |
| C3 | 情绪流标注 | 2h | |
| D1 | 强制记忆检索 | 2h | 防一致性崩坏 |
| D2 | 宏微观一致性 | 3h | |
| D3 | 结构化任务书 | 3h | |
| E1 | 题材扩展 | 4h | 锦上添花 |

**建议执行顺序**: A2 -> A1 -> A3 -> D1 -> B1 -> C1 -> D3 -> B2+B3 -> C2+C3 -> D2 -> E1
