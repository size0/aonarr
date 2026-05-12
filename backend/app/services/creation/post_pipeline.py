"""章后管线 — 生成摘要 / 提取元数据 / 张力评分

每章写完后自动运行，提取结构化数据写回 DB。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.models.novel import Novel, Chapter
from app.services.prompt_loader import PromptLoader
from app.services.truth.truth_manager import TruthFileManager

logger = logging.getLogger(__name__)

_FALLBACK_PIPELINE_SYSTEM = """你是一位专业且严格的小说编辑分析师。请分析给定的章节正文，提取以下结构化信息。

输出格式要求（严格 JSON）：
{
  "summary": "100字以内的章节摘要",
  "events": [
    {
      "description": "事件描述",
      "type": "冲突|战斗|追逐|危机|背叛|突破|觉醒|揭秘|日常|对话|铺垫|过渡|回忆|升级",
      "importance": "high|medium|low",
      "conflict_level": 0-10,
      "is_hook": false,
      "is_turning_point": false,
      "is_payoff": false
    }
  ],
  "entities": [
    {"name": "角色名", "action": "本章行为", "state_change": "状态变化"}
  ],
  "foreshadows": [
    {"description": "伏笔描述", "status": "planted|tracked|paid_off", "related_chapter": null}
  ],
  "tension_score": 4.5,
  "tension_reason": "张力评分理由",
  "chapter_title_suggestion": "建议章节标题"
}

【events 字段说明】
- type: 事件类型关键词，从以下选择最贴切的：冲突/战斗/追逐/危机/背叛/突破/觉醒/揭秘/日常/对话/铺垫/过渡/回忆/升级
- conflict_level: 该事件的冲突强度 0-10（0=无冲突纯描写，5=中等对抗，10=生死攸关）
- is_hook: 该事件是否制造了悬念/钩子，让读者想看下一章
- is_turning_point: 该事件是否构成剧情转折点（局势逆转、人物命运改变）
- is_payoff: 该事件是否兑现了之前的伏笔/悬念

【tension_score 评分标准 — 请严格打分，大部分章节应在 3-6 分】
- 0-2: 纯日常/过渡/回忆/铺垫，无冲突推进
- 3-4: 有小冲突或信息推进，但不构成转折点
- 5-6: 有明确冲突升级、关系变化或情节转折
- 7-8: 重大高潮、激烈冲突爆发、关键人物命运转折（全书中只有约20%章节应达此级别）
- 9-10: 全书级别的爆发性事件（大决战、核心秘密揭露、主角生死存亡），极其罕见

注意：如果本章主要是对话、铺垫、日常训练、信息交换、角色内心活动，分数不应超过5分。
请不要因为写作"精彩"就给高分，tension_score 衡量的是剧情紧张度和冲突强度，不是文笔好坏。"""


class PostPipeline:
    """章后管线"""

    def __init__(self, db: Session):
        self.db = db
        self._resolver = StageModelResolver(db)
        self._prompt_loader = PromptLoader(db)
        self._truth = TruthFileManager(db)

    async def run(self, novel_id: str, chapter_number: int) -> dict:
        """对指定章节运行完整章后管线

        Returns:
            提取的结构化数据 dict
        """
        chapter = (
            self.db.query(Chapter)
            .filter_by(novel_id=novel_id, number=chapter_number)
            .first()
        )
        if not chapter:
            raise ValueError(f"章节不存在: {novel_id} #{chapter_number}")
        if not chapter.content:
            raise ValueError(f"章节内容为空: {novel_id} #{chapter_number}")

        # 调用 LLM 提取
        llm = self._resolver.get_llm_for_stage("post_chapter_pipeline")

        # 优先从 DB 加载提示词
        system = self._prompt_loader.get_prompt("post_chapter_pipeline")
        if not system:
            system = _FALLBACK_PIPELINE_SYSTEM
        else:
            logger.info("章后管线使用 DB 提示词")

        config = GenerationConfig(
            system=system,
            max_tokens=4096,
            temperature=0.3,
        )

        user_prompt = f"""请分析以下章节正文：

【小说】{self._get_novel_title(novel_id)}
【章节号】第 {chapter_number} 章
【字数】{len(chapter.content)} 字

---正文开始---
{chapter.content[:8000]}
---正文结束---"""

        result = await llm.generate(user_prompt, config)
        extracted = _extract_json(result.content)

        # 写回 DB
        self._update_chapter(chapter, extracted)

        logger.info(
            "章后管线完成: %s #%d, tension=%.1f, events=%d, entities=%d",
            novel_id, chapter_number,
            extracted.get("tension_score", 0),
            len(extracted.get("events", [])),
            len(extracted.get("entities", [])),
        )

        # ── Observer + Reflector: 提取事实 → 更新真相文件 ──
        observer_facts: list[dict] = []
        try:
            from app.services.creation.observer import Observer
            from app.services.creation.reflector import Reflector

            observer = Observer(self.db)
            observer_facts = await observer.extract_facts(
                novel_id, chapter_number, chapter.content
            )
            if observer_facts:
                reflector = Reflector(self.db)
                delta_count = await reflector.apply_delta(
                    novel_id, chapter_number, observer_facts
                )
                extracted["truth_files_updated"] = delta_count
                extracted["facts_extracted"] = len(observer_facts)
                logger.info(
                    "真相文件更新: %s #%d, facts=%d, files=%d",
                    novel_id, chapter_number, len(observer_facts), delta_count,
                )
        except Exception as e:
            logger.warning("Observer/Reflector 阶段失败（不阻断管线）: %s", e)
            extracted["truth_files_error"] = str(e)[:200]

        # ── 保底关系补充：从 entities 中提取互动关系合并到 observer_facts ──
        relation_count = sum(1 for f in observer_facts if f.get("category") == "relations")
        if relation_count == 0:
            entities = extracted.get("entities", [])
            if isinstance(entities, list) and len(entities) >= 2:
                entity_names = [e.get("name", "") for e in entities if isinstance(e, dict) and e.get("name")]
                for i, ent in enumerate(entities):
                    if not isinstance(ent, dict):
                        continue
                    action = ent.get("action", "")
                    state_change = ent.get("state_change", "")
                    name = ent.get("name", "")
                    if not name:
                        continue
                    for other_name in entity_names:
                        if other_name != name and other_name in (action + state_change):
                            observer_facts.append({
                                "category": "relations",
                                "subject": name,
                                "predicate": action[:30] if action else "互动",
                                "object": other_name,
                                "detail": state_change[:30] if state_change else action[:30],
                                "confidence": 0.75,
                            })
                logger.info(
                    "关系保底补充: %s #%d, 从entities提取%d条关系",
                    novel_id, chapter_number,
                    sum(1 for f in observer_facts if f.get("category") == "relations"),
                )

        # ── 角色状态回写：复用 Observer 事实更新 Character 模型 ──
        if observer_facts:
            try:
                from app.services.creation.character_state_updater import CharacterStateUpdater
                updater = CharacterStateUpdater(self.db)
                update_result = updater.update_from_facts(novel_id, chapter_number, observer_facts)
                extracted["character_state_updates"] = update_result
                logger.info(
                    "角色状态回写: %s #%d, updated=%d, rels=%d",
                    novel_id, chapter_number,
                    update_result.get("state_updated", 0),
                    update_result.get("relations_updated", 0),
                )
            except Exception as e:
                logger.warning("角色状态回写阶段失败（不阻断管线）: %s", e)
                extracted["character_state_error"] = str(e)[:200]

        # ── 世界地图自动增长：从 Observer facts 创建/更新 WorldItem ──
        if observer_facts:
            try:
                from app.services.world.world_enricher import enrich_world_from_facts
                world_result = enrich_world_from_facts(
                    self.db, novel_id, chapter_number, observer_facts
                )
                extracted["world_enriched"] = world_result
                if world_result["created"] or world_result["updated"]:
                    logger.info(
                        "世界地图增长: %s #%d, created=%d, updated=%d",
                        novel_id, chapter_number,
                        world_result["created"], world_result["updated"],
                    )
            except Exception as e:
                logger.warning("世界地图增长阶段失败（不阻断管线）: %s", e)
                extracted["world_enrich_error"] = str(e)[:200]

        # ── 知识图谱三元组：从 Observer facts 提取结构化知识 ──
        if observer_facts:
            try:
                from app.services.world.knowledge_graph import KnowledgeGraphService
                kg = KnowledgeGraphService(self.db)
                # 将 observer_facts（list[dict]）转为 {category: [items]} 格式
                facts_by_cat: dict[str, list] = {}
                for f in observer_facts:
                    cat = f.get("category", "other")
                    facts_by_cat.setdefault(cat, []).append(f)
                triple_count = kg.extract_from_observer_facts(
                    novel_id, chapter_number, facts_by_cat
                )
                self.db.commit()
                extracted["knowledge_triples"] = triple_count
                if triple_count:
                    logger.info(
                        "知识图谱: %s #%d, triples=%d",
                        novel_id, chapter_number, triple_count,
                    )
            except Exception as e:
                logger.warning("知识图谱阶段失败（不阻断管线）: %s", e)
                extracted["knowledge_graph_error"] = str(e)[:200]

        # ── 记忆索引：将章节结构化数据写入 MemoryIndex ──
        try:
            from app.services.creation.memory_compiler import MemoryRetriever
            retriever = MemoryRetriever(self.db)
            idx_count = retriever.index_chapter(novel_id, chapter_number, chapter)
            self.db.commit()
            extracted["memory_indexed"] = idx_count
            logger.info("记忆索引: %s #%d, entries=%d", novel_id, chapter_number, idx_count)
        except Exception as e:
            logger.warning("记忆索引阶段失败（不阻断管线）: %s", e)
            extracted["memory_index_error"] = str(e)[:200]

        # ── 故事日志：追加本章结构化总结 ──
        try:
            from app.services.creation.story_log import generate_and_append_log
            log_text = await generate_and_append_log(
                self.db, self._resolver, novel_id, chapter_number
            )
            extracted["story_log_appended"] = len(log_text)
            logger.info("故事日志: %s #%d, %d字", novel_id, chapter_number, len(log_text))
        except Exception as e:
            logger.warning("故事日志阶段失败（不阻断管线）: %s", e)
            extracted["story_log_error"] = str(e)[:200]

        return extracted

    def _update_chapter(self, chapter: Chapter, data: dict) -> None:
        """将提取数据写回章节记录"""
        if "summary" in data:
            chapter.summary = data["summary"]
        if "events" in data:
            chapter.events = json.dumps(data["events"], ensure_ascii=False)
        if "entities" in data:
            chapter.entities = json.dumps(data["entities"], ensure_ascii=False)
        if "foreshadows" in data:
            chapter.foreshadows = json.dumps(data["foreshadows"], ensure_ascii=False)
        if "tension_score" in data:
            try:
                raw_score = float(data["tension_score"])
                # 后置校准：用文本信号修正 LLM 倾向性虚高
                calibrated = self._calibrate_tension(
                    raw_score, chapter.content or "",
                    data.get("events", []),
                )
                chapter.tension_score = calibrated
            except (ValueError, TypeError):
                pass
        if "chapter_title_suggestion" in data:
            suggested = data["chapter_title_suggestion"].strip()
            if suggested and (not chapter.title or chapter.title.startswith("第") and chapter.title.endswith("章")):
                chapter.title = suggested

        # 只有当提取到最低限度的结构化数据时才标记 reviewed
        has_minimum = bool(data.get("summary") or data.get("events") or data.get("tension_score"))
        chapter.status = "reviewed" if has_minimum else "pipeline_failed"
        chapter.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        if not has_minimum:
            logger.warning("管线提取数据不足，章节标记为 pipeline_failed: %s #%d", chapter.novel_id, chapter.number)

    @staticmethod
    def _calibrate_tension(raw: float, content: str, events: list) -> float:
        """用结构化事件信号 + 文本信号双向校准 tension_score

        优先使用事件的结构化字段 (type/conflict_level/is_hook/is_turning_point/is_payoff)，
        兼容旧格式 (description/importance) 通过关键词匹配。
        """
        import re as _re
        score = max(0.0, min(10.0, raw))
        adjust = 0.0

        text_sample = content[:6000]
        total_chars = max(len(content[:6000]), 1)

        # ── 1. 结构化事件信号（主要来源）──
        conflict_types = {"冲突", "战斗", "对抗", "追逐", "逃亡", "生死", "决斗",
                          "暴走", "突变", "灾难", "危机", "死亡", "背叛", "爆发", "揭秘"}
        growth_types = {"突破", "觉醒", "进化", "升级", "能力觉醒", "超自然事件"}
        calm_types = {"日常", "对话", "铺垫", "过渡", "回忆"}

        conflict_count = 0
        growth_count = 0
        calm_count = 0
        max_conflict_level = 0.0
        hook_count = 0
        turning_count = 0
        payoff_count = 0

        if isinstance(events, list):
            for e in events:
                if not isinstance(e, dict):
                    continue
                # 读 type（新格式）或从 description 推断（旧格式兼容）
                etype = e.get("type", "")
                if not etype:
                    desc = e.get("description", "")
                    if any(k in desc for k in conflict_types):
                        etype = "冲突"
                    elif any(k in desc for k in growth_types):
                        etype = "突破"

                if any(k in etype for k in conflict_types):
                    conflict_count += 1
                elif any(k in etype for k in growth_types):
                    growth_count += 1
                elif any(k in etype for k in calm_types):
                    calm_count += 1

                # 结构化冲突强度
                cl = e.get("conflict_level")
                if cl is not None:
                    try:
                        max_conflict_level = max(max_conflict_level, float(cl))
                    except (ValueError, TypeError):
                        pass

                if e.get("is_hook"):
                    hook_count += 1
                if e.get("is_turning_point"):
                    turning_count += 1
                if e.get("is_payoff"):
                    payoff_count += 1

        # 事件类型加减分
        if conflict_count >= 3:
            adjust += 2.5
        elif conflict_count >= 2:
            adjust += 1.8
        elif conflict_count == 1:
            adjust += 1.0
        if growth_count >= 1:
            adjust += 0.8
        if conflict_count == 0 and growth_count == 0:
            if calm_count >= 2:
                adjust -= 0.5
            else:
                adjust -= 0.2

        # conflict_level 加分（如果有结构化数据）
        if max_conflict_level >= 8:
            adjust += 1.5
        elif max_conflict_level >= 5:
            adjust += 0.8

        # 叙事结构加分
        if turning_count >= 1:
            adjust += 1.2
        if payoff_count >= 1:
            adjust += 0.8
        if hook_count >= 2:
            adjust += 0.5

        # ── 2. 文本信号（辅助校正）──
        dialogue_chars = sum(len(m) for m in _re.findall(r'[\u201c\u201d\u300c\u300d].*?[\u201c\u201d\u300c\u300d]', text_sample))
        dialogue_ratio = dialogue_chars / total_chars
        if dialogue_ratio > 0.55:
            adjust -= 0.4
        elif dialogue_ratio > 0.4:
            adjust -= 0.2

        action_words = len(_re.findall(
            r'[杀砍劈斩轰撞爆冲逃追挡血伤死战击破裂崩]|怒吼|咆哮|暴怒|重击|突袭|反击|猛攻',
            text_sample
        ))
        action_density = action_words / total_chars * 1000
        if action_density >= 8:
            adjust += 1.5
        elif action_density >= 4:
            adjust += 0.8

        exclaim_count = text_sample.count("\uff01") + text_sample.count("!") + text_sample.count("\uff1f\uff01")
        if exclaim_count >= 15:
            adjust += 0.3

        score += adjust

        # ── 3. 轻微全局压缩（保留起伏）──
        score = 5.0 + (score - 5.0) * 0.85

        return round(max(1.0, min(10.0, score)), 1)

    def _get_novel_title(self, novel_id: str) -> str:
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        return novel.title if novel else "未知小说"


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        try:
            return json.loads(text[start:end].strip())
        except json.JSONDecodeError:
            pass
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        try:
            return json.loads(text[first:last + 1])
        except json.JSONDecodeError:
            pass
    return {"raw": text}
