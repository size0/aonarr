# Track C: 拆书引擎 (独立 Python 模块)

独立可并行的拆书分析轨道：可作为独立 Python 包开发和测试，后期集成到主后端。

## 前置条件
- 需要 Track A 的 `get_llm_for_stage()` 接口约定（开发时可 mock）
- 可独立用 CLI 测试，不依赖 FastAPI

## 交付物
1. `backend/app/services/analysis/` 完整拆书引擎
2. 支持格式: .txt / .epub / .docx (pdf 后期)
3. 五步管线:
   - `importer.py` — 文件解析 + 编码检测
   - `chapter_splitter.py` — 智能章节切分 (50+ 正则模式 + LLM 辅助)
   - `entity_scanner.py` — jieba 分词 + LLM 实体分类 → 高频实体词典
   - `chapter_extractor.py` — 逐章深度提取 (人物/地点/物品/关系/事件) → JSON
   - `aggregator.py` — 全局聚合: 逆向大纲 + 人物图谱 + 时间线 + 伏笔网
4. `style_fingerprint.py` — 文风指纹: 句长分布/对话占比/修辞密度/节奏模式
5. `export_settings.py` — 设定集导出 (Markdown/Word)
6. CLI 入口: `python -m analysis --input novel.txt --output ./results/`
7. 单元测试 + 一本样本小说的集成测试

## 阶段配置映射
- `entity_scanner` / `chapter_extractor` → `book_analysis_extract` (实用版: gemini-flash)
- `aggregator` → `book_analysis_deep` (实用版: gemini-pro)
- `style_fingerprint` → `style_detection` (实用版: claude-opus-medium)

## 数据模型 (供 Track A 建表)
```python
class AnalysisJob:
    id: str
    novel_title: str
    source_file: str
    status: Literal["pending", "scanning", "extracting", "aggregating", "done", "failed"]
    progress: float  # 0.0 ~ 1.0
    chapter_count: int
    result_summary: dict  # 聚合后的概要
    created_at: datetime

class AnalysisChapterResult:
    job_id: str
    chapter_number: int
    characters: list[dict]
    events: list[dict]
    relationships: list[dict]
    foreshadows: list[dict]
    summary: str
```

## 步骤
1. `importer.py` — txt/epub/docx 解析器
2. `chapter_splitter.py` — 正则模式库 + LLM 辅助切分
3. `entity_scanner.py` — jieba + LLM 实体分类
4. `chapter_extractor.py` — 逐章 LLM 提取 (异步并发)
5. `aggregator.py` — 全局聚合算法
6. `style_fingerprint.py` — 文风分析
7. CLI 入口 + 测试
8. 集成到 FastAPI 路由 (`/api/v1/analysis/`)

## 预计工时
3-4 天
