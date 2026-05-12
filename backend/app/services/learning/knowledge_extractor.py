"""知识提取 — 从已完成的拆书分析中提取通用写作知识

从 AnalysisJob(status=done) 的 result_summary 中提取:
- 开头套路、爽点分布、人物模板、对话风格、伏笔技巧、题材公式
调用 get_llm_for_stage("learning_agent") 做结构化提取
写入 KnowledgeEntry 表
"""
from __future__ import annotations

import json
import logging
import re

from app.db.connection import SessionLocal
from app.llm.client import LLMClient, GenerationConfig
from app.llm.resolver import StageModelResolver
from app.models.analysis import AnalysisJob, AnalysisChapterResult
from app.models.learning import KnowledgeEntry

logger = logging.getLogger(__name__)

# ── 提取维度 ────────────────────────────────────────────────────

EXTRACTION_CATEGORIES = [
    {
        "category": "opening_pattern",
        "label": "开篇套路",
        "prompt": """分析这部小说前3章的开篇套路，提取：
1. 钩子类型（悬念/冲突/奇遇/重生/穿越 等）
2. 冲突设置方式
3. 节奏模式（快切入/慢铺垫/双线并行 等）
4. 主角出场方式
5. 世界观揭示手法""",
    },
    {
        "category": "thrill_distribution",
        "label": "爽点分布",
        "prompt": """分析这部小说的爽点分布规律，提取：
1. 高潮/爽点在全文中出现的章节位置（百分比）
2. 爽点类型（打脸/升级/获宝/逆袭/揭秘 等）
3. 爽点之间的间隔节奏
4. 张力递进模式""",
    },
    {
        "category": "character_template",
        "label": "人物模板",
        "prompt": """分析这部小说的角色设计，提取：
1. 主角人设特征（性格/能力/背景/目标）
2. 配角类型分布
3. 反派设计模式
4. 角色成长弧线
5. 角色关系网络特征""",
    },
    {
        "category": "dialogue_style",
        "label": "对话风格",
        "prompt": """分析这部小说的对话风格，提取：
1. 对话占全文的比例
2. 对话口语化程度
3. 对话节奏特征（短促/冗长/交替）
4. 对话中的信息密度
5. 情绪表达方式""",
    },
    {
        "category": "foreshadow_technique",
        "label": "伏笔技巧",
        "prompt": """分析这部小说的伏笔手法，提取：
1. 伏笔埋设方式（对话暗示/物品线索/场景描写/角色异常行为）
2. 伏笔回收的平均章节跨度
3. 多线伏笔交织技巧
4. 伏笔密度""",
    },
    {
        "category": "genre_formula",
        "label": "题材结构",
        "prompt": """分析这部小说的整体结构，提取：
1. 题材归类
2. 叙事结构（三幕式/多幕/单元剧/连续剧）
3. 主线+支线的配比
4. 世界观构建层次
5. 核心卖点""",
    },
    {
        "category": "pacing_rhythm",
        "label": "节奏控制",
        "prompt": """分析这部小说的章节节奏控制技巧，提取：
1. 单章内部节奏曲线（开头-中间-结尾的张力变化）
2. 章尾钩子/悬念设计方式（断章技巧）
3. 快节奏段 vs 慢节奏段的分布比例
4. 过渡段的处理方式（场景切换/时间跳跃/视角切换）
5. 信息投放密度（每章新信息量 vs 旧信息回顾量）""",
    },
    {
        "category": "golden_finger",
        "label": "金手指设计",
        "prompt": """分析这部小说的主角金手指/外挂设计，提取：
1. 金手指类型（系统/传承/血脉/重生记忆/空间/功法 等）
2. 金手指限制与代价设计（防止开挂感过强的平衡手法）
3. 金手指升级节奏（多久给一次新能力/新功能）
4. 金手指与主线剧情的绑定方式
5. 金手指暴露风险与隐藏策略""",
    },
    {
        "category": "reader_psychology",
        "label": "读者心理",
        "prompt": """分析这部小说如何操控读者情绪和阅读欲望，提取：
1. 期待感制造方式（预告/暗示/悬念叠加）
2. 代入感营造技巧（第一人称内心/读者已知角色不知/共情设计）
3. 满足感延迟策略（先压后扬的时间跨度与频率）
4. 情绪节奏波动模式（紧张→释放→更紧张的循环）
5. 追读/催更点的设计（为什么读者会忍不住继续看下一章）""",
    },
    {
        "category": "commercial_formula",
        "label": "商业套路",
        "prompt": """分析这部小说的商业化写法与留存设计，提取：
1. 前三章钩子密度（平均每千字几个钩子/冲突点）
2. 打脸/装逼/逆袭循环的频率和变体
3. 配角工具人设计（捧哏/垫脚石/送温暖/信息提供者）
4. 升级体系节奏（多少章升一次级/获得新能力）
5. 世界观层级扩展节奏（新地图/新势力/新敌人出场间隔）""",
    },
    {
        "category": "description_technique",
        "label": "描写技法",
        "prompt": """分析这部小说的描写手法，提取：
1. 动作场景描写特征（快慢镜头切换/招式描写详略/战斗节奏）
2. 环境描写密度与作用（氛围营造/伏笔植入/情绪渲染）
3. 心理描写方式（内心独白/行为暗示/他人视角反映）
4. 感官描写偏好（视觉/听觉/触觉/嗅觉的使用比例）
5. 叙述视角切换技巧（主角视角 vs 旁观者视角的分配）""",
    },
    {
        "category": "worldbuilding_method",
        "label": "世界观构建",
        "prompt": """分析这部小说的世界观构建方式，提取：
1. 设定引入方式（集中说明/分散渗透/对话带出/冲突揭示）
2. 力量体系层级设计（等级划分/天花板设置/越级挑战合理性）
3. 社会结构与势力分布（门派/国家/家族/组织的层次关系）
4. 规则与禁忌设定（世界的底线规则/打破规则的代价）
5. 世界观扩展节奏（从小世界到大世界的揭示节奏）""",
    },
]

SYSTEM_PROMPT = """你是一位网文创作分析专家。基于提供的小说分析数据，提取可复用的创作知识。
请严格按 JSON 格式输出：
{
  "title": "简短标题 (10-30字)",
  "insights": ["洞察1", "洞察2", ...],
  "pattern": "核心模式/套路的简明描述",
  "quality_score": 0.0-1.0,
  "tags": ["标签1", "标签2"]
}"""


# ── 主入口 ──────────────────────────────────────────────────────

async def extract_knowledge_from_recent(
    limit: int = 5,
    categories: list[str] | None = None,
) -> list[dict]:
    """从已完成的拆书任务 或 热门小说章节 中提取知识"""
    from app.api.learning import push_activity

    db = SessionLocal()
    try:
        # 获取 LLM
        try:
            resolver = StageModelResolver(db)
            llm = resolver.get_llm_for_stage("learning_agent")
        except Exception as e:
            logger.error("获取 learning_agent LLM 失败: %s", e)
            push_activity(f"❌ 知识提取失败: LLM 未配置 ({e})", "error")
            return []

        target_categories = categories or [c["category"] for c in EXTRACTION_CATEGORIES]
        results: list[dict] = []

        # 路径A: 拆书引擎已分析的任务
        jobs = (
            db.query(AnalysisJob)
            .filter(AnalysisJob.status == "done")
            .order_by(AnalysisJob.finished_at.desc())
            .limit(limit)
            .all()
        )

        for job in jobs:
            try:
                extracted = await _extract_from_job(db, job, llm, target_categories)
                results.extend(extracted)
            except Exception as e:
                logger.error("从任务 %s 提取知识失败: %s", job.id, e)

        # 路径B: 热门小说章节（主要数据来源）
        hot_results = await _extract_from_hot_novels(db, llm, target_categories, limit)
        results.extend(hot_results)

        if not results:
            push_activity("ℹ️ 暂无新知识可提取（已有书籍已处理或无已完成章节）")
        else:
            push_activity(f"✅ 知识提取完成: 新增 {len(results)} 条知识")

        return results

    finally:
        db.close()


async def _extract_from_job(
    db,
    job: AnalysisJob,
    llm: LLMClient,
    categories: list[str],
) -> list[dict]:
    """从单个分析任务提取知识"""
    # 加载分析结果
    summary = json.loads(job.result_summary) if job.result_summary else {}
    if not summary:
        return []

    # 加载章节结果
    chapters = (
        db.query(AnalysisChapterResult)
        .filter_by(job_id=job.id)
        .order_by(AnalysisChapterResult.chapter_number)
        .all()
    )

    # 构建上下文
    context = _build_context(job, summary, chapters)
    results: list[dict] = []

    for cat_def in EXTRACTION_CATEGORIES:
        if cat_def["category"] not in categories:
            continue

        # 检查是否已有该任务+分类的知识
        existing = (
            db.query(KnowledgeEntry)
            .filter_by(source_novel_id=job.id, category=cat_def["category"])
            .first()
        )
        if existing:
            continue

        try:
            entry = await _extract_single(db, llm, job, context, cat_def)
            if entry:
                results.append(entry)
        except Exception as e:
            logger.error("提取 %s/%s 失败: %s", job.novel_title, cat_def["label"], e)

    return results


async def _extract_single(
    db,
    llm: LLMClient,
    job: AnalysisJob,
    context: str,
    cat_def: dict,
) -> dict | None:
    """提取单个维度的知识"""
    prompt = f"""## 小说信息
书名: {job.novel_title}
章节数: {job.chapter_count}

## 分析数据
{context}

## 提取任务
{cat_def['prompt']}"""

    # 优先从 DB 加载学习 Agent 提示词
    system = SYSTEM_PROMPT
    if db is not None:
        from app.services.prompt_loader import PromptLoader
        db_prompt = PromptLoader(db).get_prompt("learning_agent")
        if db_prompt:
            system = db_prompt

    config = GenerationConfig(
        system=system,
        temperature=0.5,
        max_tokens=2048,
    )

    result = await llm.generate(prompt, config)
    parsed = _parse_response(result.content)

    if not parsed.get("title"):
        parsed["title"] = f"{job.novel_title} - {cat_def['label']}"

    # 保存到 KnowledgeEntry
    entry = KnowledgeEntry(
        category=cat_def["category"],
        title=parsed["title"],
        content=json.dumps(parsed, ensure_ascii=False),
        source_novel_id=job.id,
        tags=json.dumps(parsed.get("tags", [cat_def["category"]]), ensure_ascii=False),
        quality_score=float(parsed.get("quality_score", 0.5)),
    )
    db.add(entry)
    db.commit()

    logger.info("知识提取完成: [%s] %s", cat_def["category"], parsed["title"])
    return {
        "category": cat_def["category"],
        "title": parsed["title"],
        "quality_score": entry.quality_score,
    }


def _build_context(job: AnalysisJob, summary: dict, chapters: list) -> str:
    """构建提取上下文 (控制在合理 token 范围)"""
    parts: list[str] = []

    # 聚合信息
    agg = summary.get("aggregation", {})
    if agg.get("reverse_outline"):
        outline_items = agg["reverse_outline"][:10]
        parts.append("### 逆向大纲 (前10章)")
        for item in outline_items:
            parts.append(f"- 第{item.get('chapter', '?')}章: {item.get('summary', '')}")

    if agg.get("character_profiles"):
        parts.append("\n### 主要角色")
        for char in agg["character_profiles"][:8]:
            parts.append(
                f"- {char.get('name', '?')}: 出现{char.get('appearance_count', 0)}次, "
                f"角色={char.get('primary_role', '')}"
            )

    if agg.get("foreshadow_net"):
        parts.append(f"\n### 伏笔数: {len(agg['foreshadow_net'])}")

    # 文风指纹
    style = summary.get("style_fingerprint", {})
    if style:
        sent = style.get("sentence", {})
        dlg = style.get("dialogue", {})
        parts.append(
            f"\n### 文风指纹\n"
            f"- 平均句长: {sent.get('avg_length', 0)}\n"
            f"- 对话占比: {dlg.get('ratio', 0):.1%}\n"
            f"- 节奏: {style.get('rhythm', {}).get('pattern', '')}"
        )

    # 章节摘要 (前3章完整, 后面取样)
    if chapters:
        parts.append("\n### 章节摘要")
        for ch in chapters[:3]:
            parts.append(f"- 第{ch.chapter_number}章 {ch.chapter_title}: {ch.summary[:150]}")
        if len(chapters) > 6:
            mid_idx = len(chapters) // 2
            parts.append(f"- 第{chapters[mid_idx].chapter_number}章: {chapters[mid_idx].summary[:100]}")
            parts.append(f"- 第{chapters[-1].chapter_number}章: {chapters[-1].summary[:100]}")

    return "\n".join(parts)


def _parse_response(content: str) -> dict:
    """解析 LLM 响应 JSON"""
    content = content.strip()
    block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    text = block.group(1).strip() if block else content
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        text = text[first:last + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"title": content[:50], "insights": [content[:200]], "quality_score": 0.3}


# ── 热门小说知识提取 ──────────────────────────────────────────────

async def _extract_from_hot_novels(
    db,
    llm: LLMClient,
    target_categories: list[str],
    limit: int = 5,
) -> list[dict]:
    """从热门小说章节中提取创作知识"""
    from app.models.learning import HotNovelMeta, HotNovelChapter
    from app.api.learning import push_activity

    novels = (
        db.query(HotNovelMeta)
        .filter(HotNovelMeta.status == "done")
        .order_by(HotNovelMeta.crawled_at.desc())
        .limit(limit)
        .all()
    )

    if not novels:
        return []

    results: list[dict] = []

    for novel in novels:
        chapters = (
            db.query(HotNovelChapter)
            .filter_by(novel_id=novel.id)
            .order_by(HotNovelChapter.chapter_number)
            .all()
        )
        if len(chapters) < 3:
            continue

        # 检查是否已提取过
        existing_cats = {
            e.category for e in
            db.query(KnowledgeEntry.category)
            .filter_by(source_novel_id=novel.id)
            .all()
        }
        todo_cats = [c for c in target_categories if c not in existing_cats]
        if not todo_cats:
            continue

        push_activity(f"🧠 提取知识: [{novel.title}] ({len(todo_cats)} 维度)")

        context = _build_hot_novel_context(novel, chapters)

        for cat_def in EXTRACTION_CATEGORIES:
            if cat_def["category"] not in todo_cats:
                continue
            try:
                entry = await _extract_single_hot(db, llm, novel, context, cat_def)
                if entry:
                    results.append(entry)
            except Exception as e:
                logger.error("热门小说 %s/%s 知识提取失败: %s", novel.title, cat_def["label"], e)

    return results


def _build_hot_novel_context(novel, chapters) -> str:
    """从热门小说章节构建 LLM 提取上下文"""
    parts: list[str] = []

    parts.append("### 基本信息")
    parts.append(f"- 书名: {novel.title}")
    parts.append(f"- 作者: {novel.author}")
    parts.append(f"- 题材: {novel.genre}")
    parts.append(f"- 字数: {novel.word_count}")
    parts.append(f"- 简介: {(novel.synopsis or '')[:300]}")

    # 前3章完整内容（控制在合理范围）
    parts.append("\n### 前3章正文")
    for ch in chapters[:3]:
        content = (ch.content or "")[:2000]
        parts.append(f"\n#### 第{ch.chapter_number}章 {ch.title}")
        parts.append(content)

    # 后续章节取摘要
    if len(chapters) > 3:
        parts.append("\n### 后续章节概要")
        for ch in chapters[3:]:
            snippet = (ch.content or "")[:200]
            parts.append(f"- 第{ch.chapter_number}章 {ch.title}: {snippet}...")

    # 控制总长度
    full = "\n".join(parts)
    if len(full) > 12000:
        full = full[:12000] + "\n...(已截断)"
    return full


async def _extract_single_hot(
    db,
    llm: LLMClient,
    novel,
    context: str,
    cat_def: dict,
) -> dict | None:
    """从热门小说提取单维度知识"""
    prompt = f"""## 小说信息
书名: {novel.title}
作者: {novel.author}
题材: {novel.genre}

## 正文数据
{context}

## 提取任务
{cat_def['prompt']}"""

    # 优先从 DB 加载学习 Agent 提示词
    system = SYSTEM_PROMPT
    if db is not None:
        from app.services.prompt_loader import PromptLoader
        db_prompt = PromptLoader(db).get_prompt("learning_agent")
        if db_prompt:
            system = db_prompt

    config = GenerationConfig(
        system=system,
        temperature=0.5,
        max_tokens=2048,
    )

    result = await llm.generate(prompt, config)
    parsed = _parse_response(result.content)

    if not parsed.get("title"):
        parsed["title"] = f"{novel.title} - {cat_def['label']}"

    entry = KnowledgeEntry(
        category=cat_def["category"],
        title=parsed["title"],
        content=json.dumps(parsed, ensure_ascii=False),
        source_novel_id=novel.id,
        tags=json.dumps(parsed.get("tags", [cat_def["category"]]), ensure_ascii=False),
        quality_score=float(parsed.get("quality_score", 0.5)),
    )
    db.add(entry)
    db.commit()

    logger.info("热门小说知识提取: [%s] %s", cat_def["category"], parsed["title"])
    return {
        "category": cat_def["category"],
        "title": parsed["title"],
        "quality_score": entry.quality_score,
        "source": f"hot:{novel.title}",
    }
