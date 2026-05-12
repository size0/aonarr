"""分层记忆编译器 — 借鉴 OpenHanako 的三层上下文编译策略

三层记忆编译：
  - 近期（short）: 最近 3 章完整摘要 — 保留全部细节
  - 中期（mid）  : 最近 4~10 章压缩摘要 — 只保留关键事件+人物变化
  - 长期（long） : 全书关键事件索引 — 仅保留转折点和主线进展

SHA-256 指纹缓存：章节内容未变更时直接返回缓存编译结果
Token 预算控制：总输出 ≤ 4000 token（可配置）
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.novel import Chapter, MemoryCache, MemoryIndex, TruthFile

logger = logging.getLogger(__name__)

# 粗估：1 中文字 ≈ 1.5 token
CHARS_PER_TOKEN = 0.67
DEFAULT_TOKEN_BUDGET = 4000

# 三层默认配置
SHORT_TERM_WINDOW = 3   # 最近 3 章完整摘要
MID_TERM_WINDOW = 10    # 最近 4~10 章压缩摘要
LONG_TERM_MAX_EVENTS = 30  # 全书最多 30 条关键事件


@dataclass
class CompiledMemory:
    """编译后的分层记忆"""
    short_term: str = ""   # 近期：最近 3 章完整摘要
    mid_term: str = ""     # 中期：4~10 章压缩摘要
    long_term: str = ""    # 长期：全书关键事件索引
    total_tokens: int = 0
    cache_hits: int = 0    # 命中缓存次数
    cache_misses: int = 0  # 未命中次数

    def to_prompt_text(self) -> str:
        """转为可注入提示词的文本"""
        parts = []
        if self.long_term:
            parts.append(f"【全书关键事件索引】\n{self.long_term}")
        if self.mid_term:
            parts.append(f"【中期记忆（压缩摘要）】\n{self.mid_term}")
        if self.short_term:
            parts.append(f"【近期记忆（详细摘要）】\n{self.short_term}")
        return "\n\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "short_term": self.short_term,
            "mid_term": self.mid_term,
            "long_term": self.long_term,
            "total_tokens": self.total_tokens,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }


def _sha256(text: str) -> str:
    """计算文本 SHA-256 指纹"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) if text else 0


def _get_cache(db: Session, novel_id: str, layer: str, scope_key: str) -> Optional[MemoryCache]:
    return (
        db.query(MemoryCache)
        .filter_by(novel_id=novel_id, layer=layer, scope_key=scope_key)
        .first()
    )


def _set_cache(db: Session, novel_id: str, layer: str, scope_key: str,
               sha: str, compiled: str, tokens: int) -> None:
    existing = _get_cache(db, novel_id, layer, scope_key)
    if existing:
        existing.sha256 = sha
        existing.compiled_text = compiled
        existing.token_count = tokens
    else:
        db.add(MemoryCache(
            novel_id=novel_id, layer=layer, scope_key=scope_key,
            sha256=sha, compiled_text=compiled, token_count=tokens,
        ))
    db.flush()


class MemoryCompiler:
    """分层记忆编译器"""

    def __init__(self, db: Session):
        self.db = db

    def compile(
        self,
        novel_id: str,
        chapter_number: int,
        *,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> CompiledMemory:
        """编译指定章节的三层记忆

        Args:
            novel_id: 小说 ID
            chapter_number: 当前要写的章节号
            token_budget: 总 token 预算上限（默认 4000）
        """
        result = CompiledMemory()

        # 获取所有前文章节（按章节号升序）
        prev_chapters = (
            self.db.query(Chapter)
            .filter(Chapter.novel_id == novel_id, Chapter.number < chapter_number)
            .order_by(Chapter.number.asc())
            .all()
        )
        if not prev_chapters:
            return result

        # 按窗口分层
        total = len(prev_chapters)
        short_start = max(0, total - SHORT_TERM_WINDOW)
        mid_start = max(0, total - MID_TERM_WINDOW)

        short_chapters = prev_chapters[short_start:]          # 最近 3 章
        mid_chapters = prev_chapters[mid_start:short_start]   # 第 4~10 章
        long_chapters = prev_chapters[:mid_start]             # 更早的章节

        # 预算分配：近期 50%，中期 30%，长期 20%
        budget_short = int(token_budget * 0.50)
        budget_mid = int(token_budget * 0.30)
        budget_long = int(token_budget * 0.20)

        # ── 近期编译（完整摘要 + 关键细节）──
        result.short_term, hits, misses = self._compile_short(
            novel_id, short_chapters, budget_short
        )
        result.cache_hits += hits
        result.cache_misses += misses

        # ── 中期编译（压缩摘要）──
        result.mid_term, hits, misses = self._compile_mid(
            novel_id, mid_chapters, budget_mid
        )
        result.cache_hits += hits
        result.cache_misses += misses

        # ── 长期编译（关键事件索引）──
        result.long_term, hits, misses = self._compile_long(
            novel_id, long_chapters, budget_long
        )
        result.cache_hits += hits
        result.cache_misses += misses

        result.total_tokens = (
            _estimate_tokens(result.short_term) +
            _estimate_tokens(result.mid_term) +
            _estimate_tokens(result.long_term)
        )

        # 超预算裁剪
        if result.total_tokens > token_budget:
            result = self._trim(result, token_budget)

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()

        logger.info(
            "记忆编译完成: novel=%s ch=%d tokens=%d (hits=%d misses=%d)",
            novel_id, chapter_number, result.total_tokens,
            result.cache_hits, result.cache_misses,
        )
        return result

    # ── 近期：最近 3 章完整摘要 ────────────────────────────────────

    def _compile_short(self, novel_id: str, chapters: list[Chapter],
                       budget: int) -> tuple[str, int, int]:
        if not chapters:
            return "", 0, 0

        hits, misses = 0, 0
        lines = []
        for ch in chapters:
            source = f"{ch.number}|{ch.summary or ''}|{ch.content or ''}"
            sha = _sha256(source)
            scope_key = f"ch_{ch.number}"

            cached = _get_cache(self.db, novel_id, "short", scope_key)
            if cached and cached.sha256 == sha:
                lines.append(cached.compiled_text)
                hits += 1
            else:
                compiled = self._compile_short_chapter(ch)
                tokens = _estimate_tokens(compiled)
                _set_cache(self.db, novel_id, "short", scope_key, sha, compiled, tokens)
                lines.append(compiled)
                misses += 1

        text = "\n".join(lines)
        max_chars = int(budget * CHARS_PER_TOKEN)
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text, hits, misses

    def _compile_short_chapter(self, ch: Chapter) -> str:
        """近期章节编译：保留完整摘要 + 关键事件 + 出场人物"""
        parts = [f"第{ch.number}章「{ch.title or '未命名'}」"]

        if ch.summary:
            parts.append(f"  摘要：{ch.summary}")

        # 从 events/entities JSON 提取关键信息
        events = _safe_json(ch.events)
        if events:
            event_strs = [e if isinstance(e, str) else e.get("description", str(e)) for e in events[:5]]
            parts.append(f"  事件：{'；'.join(event_strs)}")

        entities = _safe_json(ch.entities)
        if entities:
            entity_names = []
            for e in entities[:8]:
                if isinstance(e, str):
                    entity_names.append(e)
                elif isinstance(e, dict):
                    entity_names.append(e.get("name", str(e)))
            parts.append(f"  人物：{'、'.join(entity_names)}")

        foreshadows = _safe_json(ch.foreshadows)
        active_fs = [f for f in foreshadows if isinstance(f, dict) and f.get("status") in ("planted", "tracked")]
        if active_fs:
            fs_strs = [f.get("description", str(f)) for f in active_fs[:3]]
            parts.append(f"  伏笔：{'；'.join(fs_strs)}")

        return "\n".join(parts)

    # ── 中期：第 4~10 章压缩摘要 ──────────────────────────────────

    def _compile_mid(self, novel_id: str, chapters: list[Chapter],
                     budget: int) -> tuple[str, int, int]:
        if not chapters:
            return "", 0, 0

        # 中期以整段为单位缓存
        source_concat = "|".join(f"{c.number}:{c.summary or ''}" for c in chapters)
        sha = _sha256(source_concat)
        scope_key = f"ch_{chapters[0].number}_{chapters[-1].number}"

        cached = _get_cache(self.db, novel_id, "mid", scope_key)
        if cached and cached.sha256 == sha:
            return cached.compiled_text, 1, 0

        lines = []
        for ch in chapters:
            summary = ch.summary or ""
            compressed = self._compress_summary(ch.number, ch.title, summary)
            lines.append(compressed)

        text = "\n".join(lines)
        max_chars = int(budget * CHARS_PER_TOKEN)
        if len(text) > max_chars:
            text = text[-max_chars:]

        tokens = _estimate_tokens(text)
        _set_cache(self.db, novel_id, "mid", scope_key, sha, text, tokens)
        return text, 0, 1

    def _compress_summary(self, number: int, title: str, summary: str) -> str:
        """压缩摘要：只保留关键事件和人物变化"""
        if not summary:
            return f"第{number}章「{title or '未命名'}」：（无摘要）"

        # 截取前 80 字 + 提取关键动词句
        short = summary[:80]
        if len(summary) > 80:
            short += "…"
        return f"第{number}章「{title or '未命名'}」：{short}"

    # ── 长期：全书关键事件索引 ────────────────────────────────────

    def _compile_long(self, novel_id: str, chapters: list[Chapter],
                      budget: int) -> tuple[str, int, int]:
        if not chapters:
            return "", 0, 0

        # 长期以全局为单位缓存
        source_concat = "|".join(f"{c.number}:{c.events or ''}:{c.tension_score}" for c in chapters)
        sha = _sha256(source_concat)
        scope_key = "global"

        cached = _get_cache(self.db, novel_id, "long", scope_key)
        if cached and cached.sha256 == sha:
            return cached.compiled_text, 1, 0

        # 提取高张力章节和关键事件
        key_events = []
        for ch in chapters:
            events = _safe_json(ch.events)
            if not events and not ch.summary:
                continue

            # 高张力章节（>= 7.0）或有关键事件的章节
            is_key = ch.tension_score >= 7.0
            has_events = bool(events)

            if is_key or has_events:
                desc = ch.summary[:50] if ch.summary else ""
                if events:
                    evt_str = events[0] if isinstance(events[0], str) else events[0].get("description", "")
                    desc = desc or evt_str[:50]
                key_events.append({
                    "chapter": ch.number,
                    "title": ch.title,
                    "event": desc,
                    "tension": ch.tension_score,
                })

        # 按重要性截取
        key_events = key_events[-LONG_TERM_MAX_EVENTS:]

        lines = []
        for ke in key_events:
            tension_tag = f"[张力{ke['tension']:.0f}]" if ke["tension"] >= 7 else ""
            lines.append(f"第{ke['chapter']}章 {tension_tag}{ke['event']}")

        # 补充真相文件中的全局事件
        truth_events = self._get_truth_events(novel_id)
        if truth_events:
            lines.append("--- 全局真相 ---")
            lines.extend(truth_events[:10])

        text = "\n".join(lines)
        max_chars = int(budget * CHARS_PER_TOKEN)
        if len(text) > max_chars:
            text = text[-max_chars:]

        tokens = _estimate_tokens(text)
        _set_cache(self.db, novel_id, "long", scope_key, sha, text, tokens)
        return text, 0, 1

    def _get_truth_events(self, novel_id: str) -> list[str]:
        """从真相文件中提取全局关键事件"""
        truth = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id, file_key="chapter_summaries")
            .first()
        )
        if not truth or not truth.content:
            return []

        # 提取 markdown 列表项作为关键事件
        lines = []
        for line in truth.content.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                lines.append(line[2:].strip())
        return lines[-15:]

    # ── 超预算裁剪 ──────────────────────────────────────────────

    def _trim(self, mem: CompiledMemory, budget: int) -> CompiledMemory:
        """优先保留近期，裁剪长期和中期"""
        target_chars = int(budget * CHARS_PER_TOKEN)

        while _estimate_tokens(mem.long_term + mem.mid_term + mem.short_term) > budget:
            # 先裁剪长期
            if mem.long_term:
                mem.long_term = mem.long_term[:int(len(mem.long_term) * 0.7)]
                if len(mem.long_term) < 20:
                    mem.long_term = ""
                continue
            # 再裁剪中期
            if mem.mid_term:
                mem.mid_term = mem.mid_term[:int(len(mem.mid_term) * 0.7)]
                if len(mem.mid_term) < 20:
                    mem.mid_term = ""
                continue
            # 最后裁剪近期
            if mem.short_term:
                mem.short_term = mem.short_term[-int(target_chars * 0.8):]
            break

        mem.total_tokens = (
            _estimate_tokens(mem.short_term) +
            _estimate_tokens(mem.mid_term) +
            _estimate_tokens(mem.long_term)
        )
        return mem


# ── 时序记忆检索服务 ─────────────────────────────────────────────

class MemoryRetriever:
    """时序记忆检索 — 从 MemoryIndex 按相关性检索历史记忆"""

    def __init__(self, db: Session):
        self.db = db

    def index_chapter(self, novel_id: str, chapter_number: int, chapter: Chapter) -> int:
        """为章节建立记忆索引

        从章节的 summary/events/entities/foreshadows 提取结构化记忆条目
        Returns: 新建索引条目数
        """
        # 清除旧索引
        self.db.query(MemoryIndex).filter_by(
            novel_id=novel_id, chapter_number=chapter_number
        ).delete()

        count = 0

        # 摘要 → summary 条目
        if chapter.summary:
            self.db.add(MemoryIndex(
                novel_id=novel_id, chapter_number=chapter_number,
                entry_type="summary", content=chapter.summary,
                keywords=self._extract_keywords(chapter.summary),
                importance=7,
            ))
            count += 1

        # 事件 → event 条目
        events = _safe_json(chapter.events)
        for evt in events:
            desc = evt if isinstance(evt, str) else evt.get("description", str(evt))
            self.db.add(MemoryIndex(
                novel_id=novel_id, chapter_number=chapter_number,
                entry_type="event", content=desc,
                keywords=self._extract_keywords(desc),
                importance=8 if chapter.tension_score >= 7 else 5,
            ))
            count += 1

        # 伏笔 → foreshadow 条目
        foreshadows = _safe_json(chapter.foreshadows)
        for fs in foreshadows:
            if not isinstance(fs, dict):
                continue
            desc = fs.get("description", "")
            status = fs.get("status", "planted")
            self.db.add(MemoryIndex(
                novel_id=novel_id, chapter_number=chapter_number,
                entry_type="foreshadow",
                content=f"[{status}] {desc}",
                keywords=self._extract_keywords(desc),
                importance=9 if status == "planted" else 6,
            ))
            count += 1

        # 实体 → character_change 条目
        entities = _safe_json(chapter.entities)
        if entities:
            names = []
            for e in entities:
                if isinstance(e, str):
                    names.append(e)
                elif isinstance(e, dict):
                    names.append(e.get("name", ""))
            if names:
                self.db.add(MemoryIndex(
                    novel_id=novel_id, chapter_number=chapter_number,
                    entry_type="character_change",
                    content=f"出场人物：{'、'.join(names)}",
                    keywords=",".join(names),
                    importance=4,
                ))
                count += 1

        self.db.flush()
        logger.info("记忆索引: novel=%s ch=%d entries=%d", novel_id, chapter_number, count)
        return count

    def retrieve(
        self,
        novel_id: str,
        *,
        query: str = "",
        entry_types: Optional[list[str]] = None,
        chapter_range: Optional[tuple[int, int]] = None,
        max_results: int = 20,
        min_importance: int = 1,
        token_budget: int = 1500,
    ) -> list[dict]:
        """按相关性检索历史记忆

        Args:
            novel_id: 小说 ID
            query: 关键词查询（空则返回最重要的条目）
            entry_types: 过滤条目类型
            chapter_range: (start, end) 章节范围
            max_results: 最大返回条目数
            min_importance: 最低重要性阈值
            token_budget: 返回结果的 token 预算

        Returns:
            [{"chapter": N, "type": "...", "content": "...", "importance": N}, ...]
        """
        q = self.db.query(MemoryIndex).filter(
            MemoryIndex.novel_id == novel_id,
            MemoryIndex.importance >= min_importance,
        )

        if entry_types:
            q = q.filter(MemoryIndex.entry_type.in_(entry_types))

        if chapter_range:
            q = q.filter(
                MemoryIndex.chapter_number >= chapter_range[0],
                MemoryIndex.chapter_number <= chapter_range[1],
            )

        # 关键词匹配 + 重要性排序
        if query:
            # SQLite LIKE 模糊匹配
            q = q.filter(
                (MemoryIndex.content.contains(query)) |
                (MemoryIndex.keywords.contains(query))
            )

        entries = (
            q.order_by(MemoryIndex.importance.desc(), MemoryIndex.chapter_number.desc())
            .limit(max_results)
            .all()
        )

        # 按 token 预算裁剪
        results = []
        total_tokens = 0
        for entry in entries:
            tokens = _estimate_tokens(entry.content)
            if total_tokens + tokens > token_budget:
                break
            results.append({
                "chapter": entry.chapter_number,
                "type": entry.entry_type,
                "content": entry.content,
                "importance": entry.importance,
                "keywords": entry.keywords,
            })
            total_tokens += tokens

        return results

    def retrieve_multi_keyword(
        self,
        novel_id: str,
        keywords: list[str],
        *,
        max_results: int = 15,
        token_budget: int = 1500,
    ) -> list[dict]:
        """按多个关键词检索，合并去重，按重要性排序"""
        seen_ids = set()
        all_entries = []

        for kw in keywords:
            results = self.retrieve(
                novel_id, query=kw, max_results=max_results // len(keywords) + 2,
                token_budget=token_budget,
            )
            for r in results:
                key = f"{r['chapter']}_{r['type']}_{r['content'][:30]}"
                if key not in seen_ids:
                    seen_ids.add(key)
                    all_entries.append(r)

        # 按重要性排序，裁剪到预算
        all_entries.sort(key=lambda x: (-x["importance"], -x["chapter"]))
        result = []
        total_tokens = 0
        for entry in all_entries[:max_results]:
            tokens = _estimate_tokens(entry["content"])
            if total_tokens + tokens > token_budget:
                break
            result.append(entry)
            total_tokens += tokens
        return result

    def _extract_keywords(self, text: str) -> str:
        """从文本中提取关键词（简易中文分词）"""
        if not text:
            return ""
        # 提取 2~4 字的中文词（简易正则，非完整分词）
        words = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        # 去重保序
        seen = set()
        unique = []
        for w in words:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        return ",".join(unique[:15])


# ── 辅助函数 ────────────────────────────────────────────────────

def _safe_json(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
