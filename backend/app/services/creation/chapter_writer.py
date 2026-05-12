"""章节生成服务 — 双阶段写作管线

核心写作链路：
1. 构建上下文 (ContextBuilder)
2. 生成/获取节拍 (OutlineGenerator)
3. Phase 1（创意写作 temp=0.78）：按节拍逐段生成正文
4. Phase 2（状态结算 temp=0.3）：提取事实、更新真相文件
5. 拼接完整章节
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.models.novel import Novel, Chapter
from app.services.creation.context_builder import ContextBuilder
from app.services.creation.vector_store import NovelVectorStore
from app.services.prompt_loader import PromptLoader
from app.services.genre_profile import get_genre_for_novel_genre

logger = logging.getLogger(__name__)

# 硬编码提示词仅作为 DB 无模板时的最低保障兜底
_FALLBACK_SYSTEM = """你是一个长期连载的{genre}作者，正在写《{title}》。

写法只抓一件事：让读者像站在现场旁边，听见人说话，看见事情往前拱。

【生稿要求】
1. 严格按照节拍写，但不要复述节拍内容
2. 第一行直接接动作、台词、声音或一个具体物件
3. 台词要像人在试探、遮掩、顶回去，别像解释设定
4. 情绪落在动作和选择上，不写空泛判断
5. 爽点写清楚筹码变化：谁压谁，谁误判，谁被当场改脸色
6. 直接输出正文，不输出标题、编号、说明和总结
"""

BEAT_PROMPT_TEMPLATE = """第{chapter_number}章 · 节拍{beat_index}/{beat_total} | 目标约{word_target}字

【这一段只写】{beat_summary}
【底色情绪】{emotion_tone}
【在场人物】{characters_involved}
{notes}{golden_chapter_rule}

【刚刚写到这里】
{recent_text}

【人物只看这些】
{characters}

【可碰的伏笔】
{foreshadows}

写法：
- 第一行直接进入现场，不要解释“本节拍要写什么”
- 用动作、台词、物件、停顿推进，少用抽象形容
- 对话别太顺，允许打断、改口、沉默、拿话堵人
- 如果有爽点，写清楚对方误判和现场反应
- 如果是过渡，也要有一个小选择或小麻烦
- 不输出标题、提纲、分析、总结

直接输出正文。"""


# 黄金三章规则注入
def _get_golden_chapter_rule(chapter_number: int, beat_index: int, beat_total: int) -> str:
    """根据章节号和节拍位置，返回黄金三章的硬性写作要求"""
    if chapter_number > 3:
        return ""
    rules = []
    if chapter_number == 1:
        if beat_index == 1:
            rules.append("🔥 全书第一段！从冲突/动作/声音开始。禁止慢热、交代背景、描写环境。第一句话就要让读者停不下来。")
        if beat_index <= 2:
            rules.append("🔥 黄金第一章：前两个节拍必须展示主角的金手指（核心能力），让读者知道爽点在哪。")
        if beat_index == beat_total:
            rules.append("🪝 本章结尾钩子！必须留一个读者翻到下一章的理由——悬念、危机、意外发现、更大的世界暗示。")
    elif chapter_number == 2:
        if beat_index <= 2:
            rules.append("🔥 黄金第二章：金手指必须得到实际验证——给读者第一个爽点，让他们看到这个能力有多厉害。")
        rules.append("⚡ 主角必须主动做事：试探能力、做出选择、应对危机。不能只观察和思考。")
    elif chapter_number == 3:
        rules.append("💥 黄金第三章：爽点爆发！必须有一个让读者拍大腿的瞬间——打脸、逆袭、震惊全场、或获得重大收获。")
        if beat_index == beat_total:
            rules.append("🪝 三章定生死！章末钩子拉到最强——暗示更大的棋局、更强的对手、更深的秘密。让读者无论如何要看第四章。")
    return "\n".join(rules) if rules else ""


def _track_expressions(text: str, used: set) -> None:
    """从生成文本中提取高频 2-4 字词组，加入已使用集合"""
    # 统计 2-4 字滑动窗口
    for width in (2, 3, 4):
        for i in range(len(text) - width + 1):
            phrase = text[i:i + width]
            if re.match(r'^[\u4e00-\u9fff]+$', phrase):
                used.add(phrase)
    # 额外提取明显重复的高频词
    words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
    freq = Counter(words)
    for word, count in freq.items():
        if count >= 3:
            used.add(word)


def _build_anti_repeat_hint(used: set, recent_text: str) -> str:
    """根据已使用表达构建反重复提示"""
    if not used:
        return ""
    # 找前文中出现超过 3 次的词
    words = re.findall(r'[\u4e00-\u9fff]{2,6}', recent_text)
    freq = Counter(words)
    overused = [w for w, c in freq.most_common(10) if c >= 3 and len(w) >= 2]
    if not overused:
        return ""
    return f"\n⚠️ 前文已过度使用以下表达，本段绝对禁止再用：{'、'.join(overused[:8])}\n"


def _post_process_chapter(text: str) -> str:
    """章节后处理：修复高频重复词、清理敷衍对话、改善句式"""

    # ── 1. 清理单字敷衍对话：保留前 2 次，后续删除整行 ──
    # 匹配 "嗯" "哦" "啊" 各种引号形式（独占一行或接短动作描写）
    filler_pattern = re.compile(
        r'^[  \t]*[\u201c"][\u55ef\u54e6\u554a][。\u3002]?[\u201d"][  \t]*$',
        re.MULTILINE,
    )
    filler_count = 0
    def _filler_replacer(m):
        nonlocal filler_count
        filler_count += 1
        if filler_count <= 2:
            return m.group(0)
        return ""  # 删除多余的
    text = filler_pattern.sub(_filler_replacer, text)

    # ── 2. 疲劳词替换：超频出现的描述词用同义词轮换 ──
    fatigue_map = {
        "耳根": ["耳尖", "耳后", "脖颈侧面", "太阳穴"],
        "没动": ["顿住", "定在原地", "僵了一下"],
        "没说话": ["沉默", "没接话", "咽回了嗓子里"],
        "没回头": ["背对着", "肩膀绷着没转", "脚步没停"],
    }
    for word, alternatives in fatigue_map.items():
        positions = [m.start() for m in re.finditer(re.escape(word), text)]
        if len(positions) <= 3:
            continue
        # 保留前 3 次，后续用替换词轮换
        alt_idx = 0
        offset = 0
        for pos in positions[3:]:
            real_pos = pos + offset
            alt = alternatives[alt_idx % len(alternatives)]
            text = text[:real_pos] + alt + text[real_pos + len(word):]
            offset += len(alt) - len(word)
            alt_idx += 1

    # ── 3. 清理连续空行和过度碎片化 ──
    # 连续超过 2 个空行压缩为 1 个
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 合并连续超短非对话行（<=5字且无引号，连续超过4行时合并）
    lines = text.split('\n')
    result_lines = []
    short_streak = 0
    for line in lines:
        stripped = line.strip()
        is_dialogue = '\u201c' in stripped or '"' in stripped
        if 0 < len(stripped) <= 5 and not is_dialogue:
            short_streak += 1
            if short_streak > 4:
                if result_lines:
                    result_lines[-1] = result_lines[-1] + stripped
                    continue
        else:
            short_streak = 0
        result_lines.append(line)

    return '\n'.join(result_lines)


class ChapterWriter:
    """章节生成器"""

    def __init__(self, db: Session):
        self.db = db
        self._resolver = StageModelResolver(db)
        self._context_builder = ContextBuilder(db)
        self._prompt_loader = PromptLoader(db)

    async def generate_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        beats: Optional[list[dict]] = None,
    ) -> str:
        """非流式：生成完整章节，返回全文"""
        full_text = []
        async for chunk in self.generate_chapter_stream(novel_id, chapter_number, beats=beats):
            data = json.loads(chunk) if chunk.startswith("{") else {"text": chunk}
            if "text" in data:
                full_text.append(data["text"])
        return "".join(full_text)

    async def generate_chapter_stream(
        self,
        novel_id: str,
        chapter_number: int,
        beats: Optional[list[dict]] = None,
        *,
        mode: str = "creative",
        enable_settlement: bool = True,
        composed_context: Optional[dict] = None,
    ) -> AsyncIterator[str]:
        """流式生成章节 — yield SSE-compatible JSON 事件

        Args:
            mode: 'creative'(temp=0.78) / 'settlement'(temp=0.3)
            enable_settlement: 创意阶段结束后自动进入结算阶段
            composed_context: Composer 产出的完整上下文 dict，包含 fact_lock/planning_section/voice_block 等

        事件类型:
        - {"type":"chapter_start","chapter_number":N,"beat_total":M}
        - {"type":"beat_start","beat_index":I,"beat_summary":"..."}
        - {"type":"chapter_chunk","text":"...","beat_index":I}
        - {"type":"beat_done","beat_index":I,"word_count":N}
        - {"type":"settlement_start"}
        - {"type":"settlement_done","facts_extracted":N}
        - {"type":"chapter_saved","chapter_number":N,"total_words":N}
        - {"type":"error","message":"..."}
        """
        try:
            # 1. 构建上下文
            ctx = self._context_builder.build(novel_id, chapter_number)
            template_vars = ctx.to_template_vars()

            # 2. 获取或使用提供的节拍
            if not beats:
                beats = self._get_default_beats(chapter_number)

            beat_total = len(beats)
            yield json.dumps({
                "type": "chapter_start",
                "chapter_number": chapter_number,
                "beat_total": beat_total,
                "timestamp": _now_iso(),
            }, ensure_ascii=False)

            # 3. 获取 LLM 客户端 + 从 DB 加载提示词
            creative_temp = 0.78 if mode == "creative" else 0.3
            llm = self._resolver.get_llm_for_stage("chapter_writing")
            system_prompt = self._build_system_prompt(ctx, template_vars, composed_context)
            # max_tokens 将在每个 beat 循环中动态设置
            base_config = GenerationConfig(
                system=system_prompt,
                max_tokens=1024,
                temperature=creative_temp,
            )

            # 4. 按节拍逐段生成
            full_content = []
            used_expressions = set()  # 跨节拍防重复追踪
            for i, beat in enumerate(beats):
                beat_index = i + 1
                beat_summary = beat.get("summary", f"第{beat_index}段")

                yield json.dumps({
                    "type": "beat_start",
                    "beat_index": beat_index,
                    "beat_summary": beat_summary,
                    "timestamp": _now_iso(),
                }, ensure_ascii=False)

                # 构建节拍提示词
                wt = beat.get("word_target", 400)
                golden_rule = _get_golden_chapter_rule(chapter_number, beat_index, beat_total)
                # 组合 notes：原始 notes + 跨节拍防重复提示
                notes_parts = []
                if beat.get("notes"):
                    notes_parts.append(f"特殊要求：{beat['notes']}")
                anti_repeat = _build_anti_repeat_hint(
                    used_expressions,
                    "\n".join(full_content) if full_content else "",
                )
                if anti_repeat:
                    notes_parts.append(anti_repeat)
                combined_notes = "\n".join(notes_parts)

                user_prompt = BEAT_PROMPT_TEMPLATE.format(
                    chapter_number=chapter_number,
                    beat_index=beat_index,
                    beat_total=beat_total,
                    beat_type=beat.get("type", "rising"),
                    beat_summary=beat_summary,
                    word_target=wt,
                    word_target_max=int(wt * 1.3),
                    emotion_tone=beat.get("emotion_tone", "自然"),
                    characters_involved="、".join(beat.get("characters_involved", [])) or "自定",
                    notes=combined_notes,
                    golden_chapter_rule=golden_rule,
                    synopsis=ctx.synopsis or "暂无",
                    recent_text=template_vars["recent_text"][-500:],  # 只保留最近500字
                    characters=template_vars["characters"][:300],  # 压缩人物信息
                    foreshadows=template_vars["foreshadows"][:200],
                    semantic_context=template_vars.get("semantic_context", "无"),
                )

                # 流式生成本节拍（动态 max_tokens 硬卡字数）
                beat_max_tokens = min(int(wt * 2.2), 1600)  # 中文1字≈1.5token，留余量
                config = GenerationConfig(
                    system=base_config.system,
                    max_tokens=beat_max_tokens,
                    temperature=base_config.temperature,
                )
                beat_text = []
                async for chunk in llm.stream_generate(user_prompt, config):
                    beat_text.append(chunk)
                    yield json.dumps({
                        "type": "chapter_chunk",
                        "text": chunk,
                        "beat_index": beat_index,
                    }, ensure_ascii=False)

                beat_content = "".join(beat_text)
                full_content.append(beat_content)

                # 提取高频表达供下一节拍规避
                _track_expressions(beat_content, used_expressions)

                # 更新 recent_text 供下一个 beat 衔接
                template_vars["recent_text"] = beat_content[-800:]

                yield json.dumps({
                    "type": "beat_done",
                    "beat_index": beat_index,
                    "word_count": len(beat_content),
                    "timestamp": _now_iso(),
                }, ensure_ascii=False)

            # 5. 后处理：修复生成文本中的高频重复问题
            final_content = "\n\n".join(full_content)
            final_content = _post_process_chapter(final_content)
            total_words = len(final_content)
            # 优先使用大纲中的章节标题
            chapter_title = ctx.current_chapter_title or ""
            # 从大纲标题中提取纯标题部分（去掉"第N章："前缀）
            import re as _re2
            title_match = _re2.match(r'^第\d+章[：:]\s*(.+)$', chapter_title)
            if title_match:
                chapter_title = title_match.group(1)
            elif not chapter_title:
                chapter_title = await self._generate_title(final_content)
            self._save_chapter(novel_id, chapter_number, final_content, llm.model, title=chapter_title)

            # 6. Phase 2: 状态结算（从正文提取事实 → 更新真相文件）
            if enable_settlement and mode == "creative":
                yield json.dumps({
                    "type": "settlement_start",
                    "timestamp": _now_iso(),
                }, ensure_ascii=False)

                try:
                    facts_count = await self._run_settlement(
                        novel_id, chapter_number, final_content
                    )
                    yield json.dumps({
                        "type": "settlement_done",
                        "facts_extracted": facts_count,
                        "timestamp": _now_iso(),
                    }, ensure_ascii=False)
                except Exception as e:
                    logger.warning("结算阶段失败（不影响章节保存）: %s", e)
                    yield json.dumps({
                        "type": "settlement_error",
                        "message": str(e)[:200],
                        "timestamp": _now_iso(),
                    }, ensure_ascii=False)

            yield json.dumps({
                "type": "chapter_saved",
                "chapter_number": chapter_number,
                "total_words": total_words,
                "model_used": llm.model,
                "timestamp": _now_iso(),
            }, ensure_ascii=False)

        except Exception as e:
            logger.exception("章节生成失败: novel=%s chapter=%d", novel_id, chapter_number)
            yield json.dumps({
                "type": "error",
                "message": str(e),
                "timestamp": _now_iso(),
            }, ensure_ascii=False)

    async def _generate_title(self, content: str) -> str:
        """从章节内容提取标题（2-8字短语）"""
        import re as _re
        try:
            llm = self._resolver.get_llm_for_stage("chapter_writing")
            prompt = (
                '请为以下小说章节内容拟一个简短标题（2-8个字，不要"第N章"前缀，'
                '只输出标题本身，不要引号或其他说明）：\n\n'
                + content[:800]
            )
            config = GenerationConfig(system="你是标题生成器。", max_tokens=30, temperature=0.3)
            result = await llm.generate(prompt, config)
            title = result.content if hasattr(result, 'content') else str(result)
            title = _re.sub(r'^[""「【\s]+|[""」】\s]+$', '', title.strip())
            title = title.split('\n')[0].strip()
            if len(title) > 15 or len(title) < 1:
                return ""
            return title
        except Exception as e:
            logger.warning("标题生成失败: %s", e)
            return ""

    def _save_chapter(self, novel_id: str, number: int, content: str, model: str, title: str = "") -> None:
        """保存或更新章节到 DB"""
        title = title or f"第{number}章"
        chapter = self.db.query(Chapter).filter_by(novel_id=novel_id, number=number).first()
        if chapter:
            chapter.content = content
            chapter.word_count = len(content)
            chapter.status = "pipeline_pending"
            chapter.model_used = model
            chapter.title = title
            chapter.updated_at = datetime.now(timezone.utc)
        else:
            chapter = Chapter(
                novel_id=novel_id,
                number=number,
                title=title,
                content=content,
                word_count=len(content),
                status="pipeline_pending",
                model_used=model,
            )
            self.db.add(chapter)

        # flush 使新增 chapter 在后续 count/sum 查询中可见（autoflush=False）
        self.db.flush()

        # 更新小说统计
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        if novel:
            novel.chapter_count = (
                self.db.query(Chapter).filter_by(novel_id=novel_id).count()
            )
            total_words = sum(
                ch.word_count for ch in self.db.query(Chapter).filter_by(novel_id=novel_id).all()
            )
            novel.current_word_count = total_words
            novel.updated_at = datetime.now(timezone.utc)

        self.db.commit()

        # 写入向量库供后续语义检索
        try:
            vs = NovelVectorStore(novel_id)
            vs.upsert_chapter(number, content)
        except Exception as e:
            logger.warning("向量库写入跳过: %s", e)

    async def _run_settlement(
        self, novel_id: str, chapter_number: int, content: str
    ) -> int:
        """Phase 2 结算：提取事实 → 更新真相文件

        使用低温 LLM (temp=0.3) 提取 9 类事实，
        然后通过 Reflector 写入真相文件。
        """
        from app.services.creation.observer import Observer
        from app.services.creation.reflector import Reflector

        observer = Observer(self.db)
        facts = await observer.extract_facts(novel_id, chapter_number, content)

        reflector = Reflector(self.db)
        delta_count = await reflector.apply_delta(novel_id, chapter_number, facts)

        logger.info(
            "结算完成: novel=%s ch=%d, 提取事实=%d, delta=%d",
            novel_id, chapter_number, len(facts), delta_count,
        )
        return len(facts)

    def _build_system_prompt(self, ctx, template_vars: dict, composed_context: Optional[dict] = None) -> str:
        """从 DB 加载专业级提示词，填充变量后返回 system prompt

        优先使用 DB 中 'chapter_writing' 阶段最新的活跃模板。
        模板内的 {variable} 占位符会被 template_vars 替换。
        如果提供了 composed_context（来自 Composer），会用其中的字段覆盖默认空值。
        DB 无模板时使用 _FALLBACK_SYSTEM 兜底。
        """
        # 优先取 '网文正文生成·主控 v1' 或 '主工作流章节生成 v6'
        preferred_names = [
            "网文正文生成·主控 v1（商业铁律+反AI禁表）",
            "主工作流章节生成 v6（记忆引擎增强）",
            "自动驾驶·节拍流式写作 v3",
        ]
        raw_template = None
        for name in preferred_names:
            raw_template = self._prompt_loader.get_prompt("chapter_writing", name=name)
            if raw_template:
                logger.info("使用 DB 提示词模板: %s", name)
                break

        if not raw_template:
            # fallback: 取该阶段最新的任意活跃模板
            raw_template = self._prompt_loader.get_prompt("chapter_writing")
            if raw_template:
                logger.info("使用 DB 提示词模板: (最新活跃)")

        if not raw_template:
            logger.warning("DB 无 chapter_writing 模板，使用硬编码兜底")
            return _FALLBACK_SYSTEM.format(
                genre=ctx.genre or "玄幻",
                title=ctx.title,
            )

        # 使用 PromptRenderer 统一解析 [SYSTEM]/[USER]
        from app.services.prompt_renderer import render as render_prompt

        # 构建扩展变量表：合并 context_builder 的变量 + 额外写作专用变量
        vars_dict = dict(template_vars)

        # 从 composed_context 中提取 Composer 产出的核心字段（优先级高于默认空值）
        cc = composed_context or {}
        vars_dict.update({
            "novel_title": ctx.title,
            "genre": ctx.genre or "玄幻",
            "chapter_number": ctx.current_chapter_number,
            "planning_section": cc.get("planning_section", ""),
            "voice_block": cc.get("voice_block", ""),
            "learning_block": cc.get("learning_block", ""),
            "context": cc.get("context") or self._format_context_block(ctx),
            "fact_lock": cc.get("fact_lock") or self._build_fact_lock(ctx),
            "pov_strategy": cc.get("pov_strategy", ""),
            "pov_character": cc.get("pov_character", ""),
            "location": cc.get("location", ""),
            "tone": cc.get("tone", ""),
            "length_rule": cc.get("length_rule", "⑦ 字数服从当前节拍目标。写足现场、写清筹码变化，但不为了凑字重复情绪和环境。"),
            "outline": cc.get("outline", ""),
            "beat_section": cc.get("beat_section", ""),
            "beat_extra": cc.get("beat_extra", ""),
            "prior_draft": "",
            "prev_summary": template_vars.get("previous_summary", ""),
            "characters_section": cc.get("characters_section") or template_vars.get("characters", ""),
            "world_settings_section": cc.get("world_settings_section") or template_vars.get("world_items", ""),
            "constraints": cc.get("constraints", ""),
            "selected_truth": cc.get("selected_truth", ""),
        })

        # 注入题材规则（疲劳词、节奏、语言铁律等）
        genre_section = self._build_genre_section(ctx.genre)
        if genre_section:
            vars_dict["genre_rules"] = genre_section

        # 注入反AI检测规则
        from app.services.audit.anti_detect import prompt_rules
        anti_detect_section = prompt_rules(ctx.genre)
        vars_dict["anti_detect_rules"] = anti_detect_section

        # 注入知识库写作方法论
        knowledge_section = template_vars.get("writing_knowledge", "")
        if knowledge_section:
            vars_dict["writing_knowledge"] = f"━━━ 写作方法论参考 ━━━\n{knowledge_section}"
        else:
            vars_dict["writing_knowledge"] = ""

        # 渲染模板（统一处理 [SYSTEM]/[USER]）
        rendered = render_prompt(raw_template, vars_dict)
        # 保存 user 模板供节拍生成使用（如果有）
        if rendered.user:
            self._rendered_user_template = rendered.user
        result = rendered.system

        # 如果模板中没有 {genre_rules} 占位符，追加到末尾
        if genre_section and "{genre_rules}" not in raw_template:
            result += "\n\n" + genre_section

        # 如果模板中没有 {anti_detect_rules} 占位符，追加到末尾
        if "{anti_detect_rules}" not in raw_template:
            result += "\n\n" + anti_detect_section

        # 如果模板中没有 {writing_knowledge} 占位符，追加到末尾
        if knowledge_section and "{writing_knowledge}" not in raw_template:
            result += "\n\n━━━ 写作方法论参考 ━━━\n" + knowledge_section

        # ── 通用叙事原则（讲故事的方法，不是格式规则）──
        core_rules = (
            "\n\n━━━ 生稿校准 ━━━\n"
            "【入场】从一个正在发生的东西切入：动作、声音、物件、半句台词。\n"
            "【赌注】三句话内让读者知道角色怕丢什么、想拿什么、被谁卡住。\n"
            "【设定】只通过使用、代价、误判露出来，不用讲课口吻解释概念。\n"
            "【对话】每句台词都带目的：试探、压价、甩锅、遮掩、逼问、改口。\n"
            "【画面】对话之间给小动作和物件反应，让人站在现场。\n"
            "【节奏】关键处拆成连续微动作；过渡处一句带走。\n"
            "【语言】少用漂亮形容和宏大判断，多用短促、具体、有毛边的句子。"
        )
        result += core_rules

        return result

    def _format_context_block(self, ctx) -> str:
        """构建紧凑的上下文块供 system prompt 使用"""
        parts = []
        if ctx.synopsis:
            parts.append(f"【故事简介】{ctx.synopsis}")
        if ctx.characters:
            char_lines = []
            for c in ctx.characters[:5]:
                traits = "、".join(c.get("traits", []))
                char_lines.append(f"  · {c['name']}（{c.get('role', '配角')}）：{c.get('description', '')} [{traits}]")
            parts.append("【登场人物】\n" + "\n".join(char_lines))
        if ctx.active_foreshadows:
            fsh_lines = [f"  · [{f.get('status')}] {f.get('description', '')}" for f in ctx.active_foreshadows[:8]]
            parts.append("【活跃伏笔】\n" + "\n".join(fsh_lines))
        if ctx.previous_summaries:
            sum_lines = [f"  第{s.get('number')}章：{s.get('summary', '')}" for s in ctx.previous_summaries[-3:]]
            parts.append("【前文摘要】\n" + "\n".join(sum_lines))
        return "\n\n".join(parts) if parts else ""

    def _build_fact_lock(self, ctx) -> str:
        """构建 FACT_LOCK 块 — 写作时不可违反的硬事实"""
        facts = []
        facts.append(f"书名=《{ctx.title}》")
        if ctx.genre:
            facts.append(f"题材={ctx.genre}")
        facts.append(f"当前章节=第{ctx.current_chapter_number}章")
        facts.append(f"已写={ctx.total_word_count}字/{ctx.chapter_count}章")
        for c in ctx.characters[:3]:
            facts.append(f"人物：{c['name']}（{c.get('role', '')}）")
        return "━━━ FACT_LOCK ━━━\n" + "\n".join(facts)

    def _build_genre_section(self, genre: str) -> str:
        """根据小说题材生成可注入 prompt 的规则段落"""
        if not genre:
            return ""
        profile = get_genre_for_novel_genre(genre)
        if not profile:
            return ""
        return profile.to_prompt_section()

    def _get_default_beats(self, chapter_number: int) -> list[dict]:
        """当没有预生成节拍时，使用默认 6 节拍结构"""
        return [
            {"index": 1, "type": "opening", "summary": "场景导入，承接前文", "word_target": 400, "emotion_tone": "平稳"},
            {"index": 2, "type": "rising", "summary": "事件推进，制造冲突", "word_target": 500, "emotion_tone": "紧张"},
            {"index": 3, "type": "rising", "summary": "冲突升级，角色互动", "word_target": 500, "emotion_tone": "紧张"},
            {"index": 4, "type": "climax", "summary": "本章高潮，关键转折", "word_target": 500, "emotion_tone": "热血"},
            {"index": 5, "type": "falling", "summary": "高潮余波，角色反应", "word_target": 400, "emotion_tone": "复杂"},
            {"index": 6, "type": "hook", "summary": "章末钩子，制造悬念", "word_target": 300, "emotion_tone": "悬疑"},
        ]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
