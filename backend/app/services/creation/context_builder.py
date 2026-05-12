"""上下文构建器 — 从 DB 收集创作所需的全部上下文

为提示词模板提供结构化 context dict，支持 token 预算控制。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.novel import Novel, Chapter, Character, WorldItem, OutlineNode
from app.models.learning import KnowledgeEntry
from app.services.creation.vector_store import NovelVectorStore
from app.services.creation.memory_compiler import MemoryCompiler, MemoryRetriever

logger = logging.getLogger(__name__)

# 粗估：1 中文字 ≈ 1.5 token
CHARS_PER_TOKEN = 0.67


@dataclass
class CreationContext:
    """创作上下文 — 传入提示词模板的结构化数据"""
    novel_id: str = ""
    title: str = ""
    genre: str = ""
    tags: list[str] = field(default_factory=list)
    synopsis: str = ""
    premise: str = ""
    world_setting: str = ""
    # 大纲（JSON 字符串或结构化文本）
    outline: str = ""
    # 当前章节信息
    current_chapter_number: int = 0
    current_chapter_title: str = ""
    current_chapter_beats: str = ""  # 本章节拍列表
    # 前文摘要（滑动窗口）
    previous_summaries: list[dict] = field(default_factory=list)
    # 最近章节的完整文本（用于衔接）
    recent_chapter_text: str = ""
    # 上一章结尾情境（用于章间连贯）
    previous_ending: str = ""
    # 人物列表
    characters: list[dict] = field(default_factory=list)
    # 伏笔列表
    active_foreshadows: list[dict] = field(default_factory=list)
    # 世界设定条目
    world_items: list[dict] = field(default_factory=list)
    # 向量语义检索结果
    semantic_context: list[dict] = field(default_factory=list)
    # 分层编译记忆（近/中/远期）
    compiled_memory: str = ""
    # 时序记忆检索结果
    memory_retrieval: list[dict] = field(default_factory=list)
    # 知识库写作方法论
    writing_knowledge: list[dict] = field(default_factory=list)
    # 故事日志（章间连贯核心）
    story_log: str = ""
    # 元数据
    total_word_count: int = 0
    chapter_count: int = 0

    def to_template_vars(self) -> dict:
        """转为提示词模板可用的变量字典"""
        return {
            "title": self.title,
            "genre": self.genre,
            "tags": "、".join(self.tags) if self.tags else "无",
            "synopsis": self.synopsis or "暂无",
            "premise": self.premise or "暂无",
            "world_setting": self.world_setting or "暂无",
            "outline": self.outline or "暂无大纲",
            "chapter_number": self.current_chapter_number,
            "chapter_title": self.current_chapter_title or f"第{self.current_chapter_number}章",
            "chapter_beats": self.current_chapter_beats or "无节拍",
            "previous_summaries": self._format_summaries(),
            "recent_text": self.recent_chapter_text or "（无前文）",
            "previous_ending": self.previous_ending or "（这是第一章）",
            "characters": self._format_characters(),
            "foreshadows": self._format_foreshadows(),
            "world_items": self._format_world_items(),
            "semantic_context": self._format_semantic_context(),
            "compiled_memory": self.compiled_memory or "（无编译记忆）",
            "memory_retrieval": self._format_memory_retrieval(),
            "writing_knowledge": self._format_writing_knowledge(),
            "story_log": self.story_log or "（这是第一章，无前文日志）",
            "total_word_count": self.total_word_count,
            "chapter_count": self.chapter_count,
        }

    def _format_summaries(self) -> str:
        if not self.previous_summaries:
            return "（无前文摘要）"
        lines = []
        for s in self.previous_summaries:
            lines.append(f"第{s.get('number', '?')}章 {s.get('title', '')}：{s.get('summary', '无摘要')}")
        return "\n".join(lines)

    def _format_characters(self) -> str:
        if not self.characters:
            return "（暂无人物）"
        lines = []
        for c in self.characters:
            traits = "、".join(c.get("traits", []))
            lines.append(f"- {c['name']}（{c.get('role', '配角')}）：{c.get('description', '')}  性格：{traits}")
        return "\n".join(lines)

    def _format_foreshadows(self) -> str:
        if not self.active_foreshadows:
            return "（无活跃伏笔）"
        lines = []
        for f in self.active_foreshadows:
            lines.append(f"- [{f.get('status', 'planted')}] {f.get('description', '')}")
        return "\n".join(lines)

    def _format_world_items(self) -> str:
        if not self.world_items:
            return "（无世界设定条目）"
        lines = []
        for w in self.world_items:
            lines.append(f"- [{w.get('category', '')}] {w['name']}：{w.get('description', '')}")
        return "\n".join(lines)

    def _format_semantic_context(self) -> str:
        if not self.semantic_context:
            return ""
        lines = []
        for item in self.semantic_context:
            ch = item.get("chapter_number", "?")
            lines.append(f"[第{ch}章相关段落] {item.get('text', '')}")
        return "\n".join(lines)

    def _format_memory_retrieval(self) -> str:
        if not self.memory_retrieval:
            return ""
        lines = []
        for item in self.memory_retrieval:
            ch = item.get("chapter", "?")
            t = item.get("type", "")
            lines.append(f"[第{ch}章/{t}] {item.get('content', '')}")
        return "\n".join(lines)

    def _format_writing_knowledge(self) -> str:
        if not self.writing_knowledge:
            return ""
        lines = []
        for k in self.writing_knowledge:
            title = k.get("title", "")
            pattern = k.get("pattern", "")
            insights = k.get("insights", [])
            lines.append(f"【{title}】{pattern}")
            for ins in insights[:3]:
                lines.append(f"  · {ins}")
        return "\n".join(lines)


class ContextBuilder:
    """从 DB 构建创作上下文"""

    def __init__(self, db: Session):
        self.db = db

    def build(
        self,
        novel_id: str,
        chapter_number: int,
        *,
        summary_window: int = 10,
        recent_text_chapters: int = 1,
        max_token_budget: int = 6000,
        memory_token_budget: int = 4000,
        enable_memory_compiler: bool = True,
    ) -> CreationContext:
        """构建指定章节的创作上下文

        Args:
            novel_id: 小说 ID
            chapter_number: 当前要写的章节号
            summary_window: 前文摘要滑动窗口大小
            recent_text_chapters: 取最近几章完整文本
            max_token_budget: token 预算上限（控制上下文总长度）
        """
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        if not novel:
            raise ValueError(f"小说不存在: {novel_id}")

        ctx = CreationContext(
            novel_id=novel_id,
            title=novel.title,
            genre=novel.genre,
            tags=_parse_json_list(novel.tags),
            synopsis=novel.synopsis,
            premise=novel.premise,
            world_setting=novel.world_setting,
            current_chapter_number=chapter_number,
            total_word_count=novel.current_word_count,
            chapter_count=novel.chapter_count,
        )

        # 人物
        characters = self.db.query(Character).filter_by(novel_id=novel_id).all()
        ctx.characters = [
            {
                "name": c.name,
                "role": c.role,
                "description": c.description,
                "traits": _parse_json_list(c.traits),
            }
            for c in characters
        ]

        # 世界设定
        world_items = self.db.query(WorldItem).filter_by(novel_id=novel_id).all()
        ctx.world_items = [
            {"name": w.name, "category": w.category, "description": w.description}
            for w in world_items
        ]

        # 前文章节
        prev_chapters = (
            self.db.query(Chapter)
            .filter(Chapter.novel_id == novel_id, Chapter.number < chapter_number)
            .order_by(Chapter.number.desc())
            .limit(summary_window)
            .all()
        )
        prev_chapters.reverse()  # 按章节号升序

        # 前文摘要
        ctx.previous_summaries = [
            {"number": ch.number, "title": ch.title, "summary": ch.summary}
            for ch in prev_chapters
        ]

        # 最近章节完整文本（用于衔接语气）
        if prev_chapters and recent_text_chapters > 0:
            recent = prev_chapters[-recent_text_chapters:]
            texts = [ch.content for ch in recent if ch.content]
            ctx.recent_chapter_text = "\n\n".join(texts)

        # 上一章结尾情境（章间连贯的关键）
        if prev_chapters:
            last_ch = prev_chapters[-1]
            ending_parts = []
            if last_ch.summary:
                ending_parts.append(f"上一章（{last_ch.title}）：{last_ch.summary}")
            if last_ch.content:
                ending_parts.append(f"结尾原文：{last_ch.content[-300:]}")
            ctx.previous_ending = "\n".join(ending_parts)

        # 活跃伏笔（从各章节聚合）
        all_foreshadows = []
        for ch in prev_chapters:
            fsh = _parse_json_list(ch.foreshadows)
            for f in fsh:
                if isinstance(f, dict) and f.get("status") in ("planted", "tracked"):
                    all_foreshadows.append(f)
        ctx.active_foreshadows = all_foreshadows[-20:]  # 最多 20 条

        # ── 从 outline_nodes 加载大纲 ──
        outline_nodes = (
            self.db.query(OutlineNode)
            .filter_by(novel_id=novel_id)
            .all()
        )
        if outline_nodes:
            ctx.outline = self._build_outline_text(outline_nodes, chapter_number)
            # 从大纲获取当前章标题（按标题中的章节号匹配）
            ch_nodes = [n for n in outline_nodes if n.level == 'chapter']
            for node in ch_nodes:
                m = re.match(r'^第(\d+)章[：:]', node.title)
                if m and int(m.group(1)) == chapter_number:
                    ctx.current_chapter_title = node.title
                    break

        # 当前章节信息（如果已存在 draft，覆盖大纲标题）
        current = (
            self.db.query(Chapter)
            .filter_by(novel_id=novel_id, number=chapter_number)
            .first()
        )
        if current and current.title:
            ctx.current_chapter_title = current.title

        # 向量语义检索 — 用前文摘要或简介作为 query
        try:
            vs = NovelVectorStore(novel_id)
            query_text = ctx.synopsis or ctx.premise or ctx.recent_chapter_text[:500] or ctx.title
            if query_text:
                ctx.semantic_context = vs.query_similar(
                    query_text,
                    n_results=3,
                    exclude_chapter=chapter_number,
                )
        except Exception as e:
            logger.warning("向量检索跳过: %s", e)

        # ── 分层记忆编译 ──
        if enable_memory_compiler:
            try:
                compiler = MemoryCompiler(self.db)
                compiled = compiler.compile(novel_id, chapter_number, token_budget=memory_token_budget)
                ctx.compiled_memory = compiled.to_prompt_text()
            except Exception as e:
                logger.warning("记忆编译跳过: %s", e)

            # 时序记忆检索 — 用前文摘要/简介提取关键词做检索
            try:
                retriever = MemoryRetriever(self.db)
                query_text = ctx.synopsis or ctx.premise or ctx.recent_chapter_text[:200]
                if query_text:
                    # 提取前几个关键词
                    keywords = re.findall(r'[\u4e00-\u9fff]{2,4}', query_text)[:5]
                    if keywords:
                        ctx.memory_retrieval = retriever.retrieve_multi_keyword(
                            novel_id, keywords, max_results=10, token_budget=1500,
                        )
            except Exception as e:
                logger.warning("记忆检索跳过: %s", e)

        # ── 故事日志注入（按卷分层读取）──
        try:
            from app.services.creation.story_log import read_recent_log
            log_text = read_recent_log(
                novel_id, last_n=5, db=self.db, chapter_number=chapter_number
            )
            if log_text:
                ctx.story_log = log_text
                logger.info("故事日志注入: %d 字", len(log_text))
        except Exception as e:
            logger.warning("故事日志读取跳过: %s", e)

        # ── 知识库写作方法论注入 ──
        try:
            ctx.writing_knowledge = self._retrieve_writing_knowledge(
                novel_id, ctx.genre, ctx.tags, chapter_number
            )
        except Exception as e:
            logger.warning("知识库检索跳过: %s", e)

        # token 预算裁剪
        ctx = self._trim_to_budget(ctx, max_token_budget)

        return ctx

    def _build_outline_text(self, nodes: list, chapter_number: int) -> str:
        """将 outline_nodes 构建为紧凑的大纲上下文文本

        聚焦当前章前后，给出结构化的写作方向。
        """
        volumes = [n for n in nodes if n.level == 'volume']
        chapters = [n for n in nodes if n.level == 'chapter']

        # 按标题中的章节号排序
        def _get_ch_num(node):
            m = re.match(r'^第(\d+)章', node.title)
            return int(m.group(1)) if m else 9999
        chapters.sort(key=_get_ch_num)

        lines = []

        # 找当前章所在卷
        current_ch_node = None
        for ch in chapters:
            if _get_ch_num(ch) == chapter_number:
                current_ch_node = ch
                break

        if current_ch_node:
            # 找父卷
            for vol in volumes:
                if vol.id == current_ch_node.parent_id:
                    lines.append(f"【当前卷】{vol.title}：{vol.summary[:200]}")
                    break

        # 输出当前章 ± 2 章的大纲
        nearby = [ch for ch in chapters if abs(_get_ch_num(ch) - chapter_number) <= 2]
        for ch in nearby:
            num = _get_ch_num(ch)
            marker = "→" if num == chapter_number else " "
            lines.append(f"{marker} {ch.title}：{ch.summary[:100]}")

        return "\n".join(lines)

    def _retrieve_writing_knowledge(
        self, novel_id: str, genre: str, tags: list[str], chapter_number: int
    ) -> list[dict]:
        """从知识库检索与当前小说题材相关的写作方法论"""
        results = []

        # 根据题材决定检索的 category
        genre_cat_map = {
            "玄幻": ["fantasy_genre", "writing_technique", "combat_reference"],
            "修真": ["cultivation_genre", "writing_technique", "taoism_reference"],
            "仙侠": ["cultivation_genre", "eastern_worldbuilding", "taoism_reference"],
            "都市": ["urban_genre", "writing_technique", "psychology"],
            "穿越": ["isekai_genre", "writing_technique"],
            "网游": ["game_genre", "writing_technique"],
            "西方奇幻": ["western_worldbuilding", "writing_technique"],
            "武侠": ["eastern_worldbuilding", "combat_reference", "writing_technique"],
        }
        target_cats = genre_cat_map.get(genre, ["writing_technique"])
        # 始终加入通用类
        target_cats.extend(["writing_basics", "writing_advanced", "pacing_technique"])
        target_cats = list(set(target_cats))

        # 根据章节阶段动态调整检索重点
        if chapter_number <= 3:
            # 开篇阶段：重点检索开篇、节奏、爽点方法论
            extra_cats = ["webnovel_basics", "webnovel_workflow"]
            target_cats.extend(extra_cats)

        q = (
            self.db.query(KnowledgeEntry)
            .filter(
                KnowledgeEntry.category.in_(target_cats),
                KnowledgeEntry.quality_score >= 0.6,
            )
            .order_by(KnowledgeEntry.quality_score.desc())
            .limit(8)
        )
        entries = q.all()

        for entry in entries:
            try:
                content = json.loads(entry.content) if entry.content else {}
            except (json.JSONDecodeError, TypeError):
                content = {}
            results.append({
                "title": entry.title,
                "category": entry.category,
                "pattern": content.get("pattern", content.get("definition", "")),
                "insights": content.get("insights", content.get("core_elements", []))[:3],
                "usage": content.get("usage", ""),
            })

        if results:
            logger.info("知识库注入 %d 条方法论", len(results))
        return results

    def _trim_to_budget(self, ctx: CreationContext, budget: int) -> CreationContext:
        """裁剪上下文使其不超过 token 预算"""
        estimated = self._estimate_tokens(ctx)
        if estimated <= budget:
            return ctx

        # 优先裁剪最近章节完整文本
        if ctx.recent_chapter_text:
            max_chars = int(budget * CHARS_PER_TOKEN * 0.3)
            ctx.recent_chapter_text = ctx.recent_chapter_text[-max_chars:]

        # 再裁剪前文摘要（保留最近的）
        while self._estimate_tokens(ctx) > budget and len(ctx.previous_summaries) > 3:
            ctx.previous_summaries.pop(0)

        # 裁剪伏笔
        while self._estimate_tokens(ctx) > budget and len(ctx.active_foreshadows) > 5:
            ctx.active_foreshadows.pop(0)

        return ctx

    def _estimate_tokens(self, ctx: CreationContext) -> int:
        """粗估上下文 token 数"""
        text = json.dumps(ctx.to_template_vars(), ensure_ascii=False)
        return int(len(text) / CHARS_PER_TOKEN)


def _parse_json_list(raw: str) -> list:
    """安全解析 JSON 列表字符串"""
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
