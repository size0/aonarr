"""灵感引擎 — AI 小说助理（含记忆系统）

核心能力:
  1. 编译热门小说数据为上下文 → 注入 system prompt
  2. 流式对话 → 用户自然语言交互
  3. 跨 session 记忆 → 记住用户偏好、创作风格、历史对话要点
  4. 可分析趋势、推荐方向、生成大纲、回答一切小说创作问题

记忆架构 (仿 OpenHanako):
  - 滚动摘要: 每 6 轮 LLM 压缩当前 session 对话
  - 跨 session 记忆: 编译最近 session 摘要为 memory 段
  - 事实提取: 从摘要中提取原子事实 (用户画像/偏好)
  - 注入 prompt: memory 段 + 数据上下文 → system prompt
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Optional, AsyncIterator

from sqlalchemy.orm import Session

from app.llm.client import GenerationConfig
from app.llm.resolver import StageModelResolver
from app.models.learning import HotNovelMeta
from app.models.memory import (
    ChatSession, ChatMessage as ChatMessageRow,
    MemoryFact,
)

logger = logging.getLogger(__name__)

NEW_BOOK_MONTHS = 6
# 每隔多少轮触发一次滚动摘要
TURNS_PER_SUMMARY = 6

ASSISTANT_SYSTEM = """你是「墨语」—— 一位顶级网络小说创作顾问 AI。

## 你的身份
你同时具备以下专业能力：
- 📊 **市场分析师**：精通番茄小说、起点等平台的数据趋势
- ✍️ **资深编辑**：能精准判断什么题材/写法读者买账
- 💡 **创意策划师**：能帮作者从零构思完整的小说企划
- 📖 **大纲架构师**：能生成专业的分卷/分幕/分章大纲
- 🎯 **写作教练**：能给出实操性强的写作建议

{memory}

## 你掌握的实时数据
以下是从番茄小说平台采集的最新热门小说数据：

{context}

## 你的工作方式
1. **主动分析**：不要只干巴巴回答，主动从数据中找到洞察
2. **数据驱动**：推荐方向时用具体数据支撑（阅读量、收藏、评分）
3. **实操导向**：给建议要具体、可执行，不要泛泛而谈
4. **创意激发**：用户没思路时，主动抛出有趣的点子
5. **Markdown 格式**：善用标题、列表、加粗，让回答清晰易读
6. **记忆运用**：如果你记得用户之前的偏好或讨论，主动引用，体现连续性

## 常见任务
- 用户问"什么题材火" → 从数据分析品类/标签热度，给出排名
- 用户问"帮我想个故事" → 结合热门趋势，生成 3-5 个创意方向
- 用户说"生成大纲" → 输出完整的分卷大纲（含标题、章节范围、主线）
- 用户问某本书 → 从数据中找到该书信息并分析
- 用户有模糊想法 → 帮他细化、补全、找到差异化卖点
- 用户问 Agent/事件发动机 → 查看下方"已注册题材 Agent"和"事件发动机"信息

## 项目能力
你可以看到本项目已注册的所有题材 Agent 和事件发动机配置（在数据区末尾）。
用户问你"新建了什么 Agent""职场 Agent 怎么样"等问题时，直接引用这些信息回答。"""


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def build_assistant_context(db: Session) -> str:
    """编译所有热门小说数据 + Agent 信息为 AI 可读的上下文文本"""
    all_novels = db.query(HotNovelMeta).all()
    if not all_novels:
        return "（暂无采集数据，请先在学习中心触发热门小说采集）"

    cutoff = datetime.now(timezone.utc) - timedelta(days=NEW_BOOK_MONTHS * 30)
    genre_counter: Counter = Counter()
    tag_counter: Counter = Counter()
    new_books = []

    for n in all_novels:
        if n.genre:
            genre_counter[n.genre] += 1
        try:
            tags = json.loads(n.tags) if n.tags else []
        except Exception:
            tags = []
        for t in tags:
            if t:
                tag_counter[t] += 1
        created = _parse_iso(getattr(n, "created_at_source", ""))
        if created and created >= cutoff:
            new_books.append(n)

    new_books.sort(key=lambda x: getattr(x, "read_count", 0) or 0, reverse=True)
    top_read = sorted(all_novels, key=lambda x: getattr(x, "read_count", 0) or 0, reverse=True)[:20]
    top_rated = sorted(
        [n for n in all_novels if n.rating and n.rating > 0],
        key=lambda x: x.rating or 0, reverse=True,
    )[:20]

    lines = [f"### 总览\n- 采集总书数: {len(all_novels)}"]
    lines.append(f"- 近{NEW_BOOK_MONTHS}个月新书: {len(new_books)}")

    # 品类
    lines.append("\n### 品类分布 (Top 15)")
    for g, c in genre_counter.most_common(15):
        lines.append(f"- {g}: {c}本")

    # 热门标签
    lines.append("\n### 热门标签 (Top 20)")
    tags_text = ", ".join(f"{t}({c})" for t, c in tag_counter.most_common(20))
    lines.append(tags_text)

    # 飙升新书
    lines.append("\n### 飙升新书 (按阅读量)")
    for n in new_books[:20]:
        rc = getattr(n, "read_count", 0) or 0
        bs = getattr(n, "bookshelf_count", 0) or 0
        lines.append(
            f"- 《{n.title}》{n.genre} | {n.author} | "
            f"阅读{rc:,} 收藏{bs:,} 评分{n.rating or '?'} {n.chapter_count}章 | "
            f"{(n.synopsis or '')[:80]}"
        )

    # 阅读TOP
    lines.append("\n### 阅读量 TOP 20")
    for n in top_read:
        rc = getattr(n, "read_count", 0) or 0
        lines.append(f"- 《{n.title}》{n.genre} | {n.author} | 阅读{rc:,}")

    # 高分
    if top_rated:
        lines.append("\n### 高分作品 TOP 10")
        for n in top_rated[:10]:
            lines.append(f"- 《{n.title}》评分{n.rating} | {n.genre} | {n.author}")

    # 全部书名索引（方便查询）
    lines.append("\n### 全部已采集书目")
    for n in all_novels:
        lines.append(f"- {n.title} ({n.genre}, {n.author})")

    return "\n".join(lines)


# ── 记忆系统 ─────────────────────────────────────────────────────

def _build_memory_text(db: Session) -> str:
    """编译跨 session 记忆 → 注入 system prompt 的文本段

    1. 读取最近 5 个 session 的摘要 → 合并为 recent
    2. 读取所有 MemoryFact → 合并为 facts
    3. 组装成 memory 文本
    """
    # 近期 session 摘要
    recent_sessions = (
        db.query(ChatSession)
        .filter(ChatSession.summary != "")
        .order_by(ChatSession.updated_at.desc())
        .limit(5)
        .all()
    )
    recent_parts = []
    for s in reversed(recent_sessions):  # 时间正序
        recent_parts.append(f"- {s.title}: {s.summary}")

    # 持久事实
    facts = (
        db.query(MemoryFact)
        .order_by(MemoryFact.created_at.desc())
        .limit(30)
        .all()
    )
    fact_lines = [f"- {f.fact}" for f in facts]

    if not recent_parts and not fact_lines:
        return ""

    lines = ["## 你对用户的记忆"]
    if fact_lines:
        lines.append("\n### 用户画像（长期事实）")
        lines.extend(fact_lines)
    if recent_parts:
        lines.append("\n### 近期对话回顾")
        lines.extend(recent_parts)

    return "\n".join(lines)


async def _maybe_rolling_summary(
    db: Session, session_id: str, client
) -> None:
    """如果当前 session 消息数达到阈值，执行滚动摘要

    仿 OpenHanako: 每 TURNS_PER_SUMMARY 轮压缩一次
    """
    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        return

    # 只在消息数为 TURNS_PER_SUMMARY 的倍数时触发
    if session.message_count < TURNS_PER_SUMMARY:
        return
    if session.message_count % TURNS_PER_SUMMARY != 0:
        return

    # 检查指纹：避免重复编译
    fp = hashlib.md5(f"{session_id}:{session.message_count}".encode()).hexdigest()
    if session.summary_fingerprint == fp:
        return

    # 读最近消息
    msgs = (
        db.query(ChatMessageRow)
        .filter_by(session_id=session_id)
        .order_by(ChatMessageRow.turn_index.desc())
        .limit(TURNS_PER_SUMMARY * 2)  # 最近 N 轮（一轮 = user+assistant）
        .all()
    )
    if not msgs:
        return

    conversation = "\n".join(
        f"{'用户' if m.role == 'user' else '助手'}: {m.content[:500]}"
        for m in reversed(msgs)
    )

    prev_summary = session.summary or ""
    prompt_input = f"## 上次摘要\n{prev_summary}\n\n## 新对话\n{conversation}" if prev_summary else conversation

    try:
        config = GenerationConfig(
            system="你是一个对话摘要压缩器。将以下对话压缩为简洁的摘要，重点记录：\n"
                   "1. 用户的身份、偏好、创作方向\n"
                   "2. 讨论过的核心话题和结论\n"
                   "3. 用户表达的喜好/厌恶\n"
                   "不要记录执行细节、工具操作、文件名。最多 200 字。直接输出摘要，不要标题。",
            temperature=0.3,
            max_tokens=500,
        )
        result = await client.generate(prompt_input, config)
        session.summary = result.content.strip()
        session.summary_fingerprint = fp
        db.commit()
        logger.info("Session [%s] 滚动摘要已更新 (%d字)", session.title, len(session.summary))

        # 触发事实提取（后台，不阻塞）
        await _extract_facts_from_summary(db, session_id, session.summary, client)

    except Exception as e:
        logger.warning("滚动摘要失败: %s", e)


async def _extract_facts_from_summary(
    db: Session, session_id: str, summary: str, client
) -> None:
    """从摘要中提取原子事实 → 写入 MemoryFact（仿 OpenHanako deep-memory）"""
    if not summary or len(summary) < 20:
        return

    try:
        config = GenerationConfig(
            system="""你是一个记忆拆分器。从以下对话摘要中提取关于用户的原子事实。

规则：
1. 只提取用户画像相关事实：身份、偏好、创作方向、喜好、关注主题
2. 不提取工作细节、文件名、工具、命令
3. 每条事实必须是原子的（一条只记一件事）
4. 标签用于检索，选 2-5 个关键词
5. 如果没有新事实，返回空数组 []

输出严格 JSON 数组：
[{"fact": "用户喜欢写都市类型的小说", "tags": ["都市", "创作偏好"]}]""",
            temperature=0.3,
            max_tokens=1000,
        )
        result = await client.generate(f"摘要内容：\n{summary}", config)
        raw = result.content.strip()

        # 解析 JSON
        fence = raw.find("```")
        if fence != -1:
            end = raw.find("```", fence + 3)
            raw = raw[fence:end] if end != -1 else raw[fence:]
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()

        facts = json.loads(raw)
        if not isinstance(facts, list):
            return

        added = 0
        for f in facts:
            if not isinstance(f, dict) or "fact" not in f:
                continue
            fact_text = f["fact"].strip()
            if not fact_text:
                continue
            # 去重：同一 session 不重复提取相同事实
            existing = (
                db.query(MemoryFact)
                .filter_by(source_session_id=session_id, fact=fact_text)
                .first()
            )
            if existing:
                continue
            tags = json.dumps(f.get("tags", []), ensure_ascii=False)
            db.add(MemoryFact(
                fact=fact_text,
                tags=tags,
                source_session_id=session_id,
            ))
            added += 1

        if added:
            db.commit()
            logger.info("提取了 %d 条新事实 (session: %s)", added, session_id[:8])

    except Exception as e:
        logger.warning("事实提取失败: %s", e)


# ── 流式对话 ─────────────────────────────────────────────────────

async def chat_stream(
    db: Session,
    messages: list[dict],
    session_id: str = "",
) -> AsyncIterator[str]:
    """流式对话 — 注入小说数据上下文 + 项目知识 + 跨 session 记忆"""
    context = build_assistant_context(db)
    memory_text = _build_memory_text(db)

    # 注入项目全景知识
    from app.services.inspiration.project_context import build_project_context
    project_ctx = build_project_context(db)
    full_context = context + "\n\n" + project_ctx if project_ctx else context

    system = ASSISTANT_SYSTEM.replace("{context}", full_context).replace("{memory}", memory_text)

    resolver = StageModelResolver(db)
    client = None
    for stage in ("chapter_writing", "outline_planning", "learning_agent"):
        try:
            client = resolver.get_llm_for_stage(stage)
            break
        except Exception:
            continue
    if not client:
        yield "❌ 未配置 LLM 模型，请先在设置页面配置模型。"
        return

    # 拼接多轮消息为 prompt
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            prompt_parts.append(f"用户: {content}")
        elif role == "assistant":
            prompt_parts.append(f"助手: {content}")

    prompt = "\n\n".join(prompt_parts)
    if not prompt.startswith("用户:"):
        prompt = f"用户: {prompt}"

    config = GenerationConfig(system=system, temperature=0.7, max_tokens=4096)

    try:
        async for chunk in client.stream_generate(prompt, config):
            yield chunk
    except Exception as e:
        logger.error("助理对话失败: %s", e)
        yield f"\n\n❌ 生成出错: {e}"

    # 对话结束后触发滚动摘要（后台）
    if session_id and client:
        try:
            await _maybe_rolling_summary(db, session_id, client)
        except Exception as e:
            logger.warning("后台摘要触发失败: %s", e)
