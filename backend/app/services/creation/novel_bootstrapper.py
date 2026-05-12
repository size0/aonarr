"""新建小说初始化引导 — 自动生成世界观 / 核心人物 / 宏观大纲

流式 SSE 事件：
- {"stage":"world","status":"start"}
- {"stage":"world","status":"done","data":{...}}
- {"stage":"characters","status":"start"}
- {"stage":"characters","status":"done","data":[...]}
- {"stage":"outline","status":"start"}
- {"stage":"outline","status":"done","data":{...}}
- {"stage":"complete","novel_id":"..."}
- {"stage":"error","message":"..."}
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import AsyncIterator

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.models.novel import Novel, Character, WorldItem, OutlineNode
from app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict | list:
    """从 LLM 输出中提取 JSON，兼容 thinking 模型的混合输出"""
    import re
    # 尝试找 ```json ... ``` 块
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    raw = m.group(1).strip() if m else text.strip()
    # 尝试找第一个 { 或 [
    for i, c in enumerate(raw):
        if c in '{[':
            raw = raw[i:]
            break
    else:
        raise ValueError(f"LLM 输出中无 JSON 内容 (len={len(text)}, first 100: {text[:100]})")
    # 从末尾截断到最后一个 } 或 ]（去掉尾部垃圾）
    for i in range(len(raw) - 1, -1, -1):
        if raw[i] in '}]':
            raw = raw[:i + 1]
            break
    return json.loads(raw)


class NovelBootstrapper:
    """新建小说后的初始化引导器"""

    def __init__(self, db: Session):
        self.db = db
        self._resolver = StageModelResolver(db)
        self._prompt_loader = PromptLoader(db)

    async def bootstrap_stream(self, novel_id: str) -> AsyncIterator[str]:
        """流式初始化小说：世界观 → 人物 → 大纲"""
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        if not novel:
            yield _evt("error", message="小说不存在")
            return

        context = {
            "title": novel.title,
            "genre": novel.genre,
            "tags": novel.tags,
            "synopsis": novel.synopsis or "暂无",
            "premise": novel.premise or "暂无",
            "target_chapters": novel.target_chapter_count or 200,
            "words_per_chapter": novel.words_per_chapter or 2000,
        }

        # ── Stage 1: 世界观 ──
        world_data = None
        try:
            yield _evt("world", status="start")
            logger.info("[bootstrap] 开始生成世界观: %s", novel.title)
            world_data = await self._gen_world(context)
            saved_count = self._save_world(novel_id, world_data)
            novel.world_setting = json.dumps(world_data, ensure_ascii=False)[:4000]
            self.db.commit()
            logger.info("[bootstrap] 世界观生成完成，保存 %d 条", saved_count)
            yield _evt("world", status="done", data=world_data, saved_count=saved_count)
        except Exception as e:
            self.db.rollback()
            logger.exception("[bootstrap] 世界观生成失败")
            yield _evt("world", status="error", message=f"世界观生成失败: {str(e)[:200]}")

        await asyncio.sleep(5)  # 避免上游 API 限流

        # ── Stage 2: 核心人物 ──
        characters = None
        try:
            yield _evt("characters", status="start")
            logger.info("[bootstrap] 开始生成人物")
            characters = await self._gen_characters(context, novel.world_setting or "")
            saved_count = self._save_characters(novel_id, characters)
            self.db.commit()
            logger.info("[bootstrap] 人物生成完成，保存 %d 个", saved_count)
            yield _evt("characters", status="done", data=characters, saved_count=saved_count)
        except Exception as e:
            self.db.rollback()
            logger.exception("[bootstrap] 人物生成失败")
            yield _evt("characters", status="error", message=f"人物生成失败: {str(e)[:200]}")

        await asyncio.sleep(5)  # 避免上游 API 限流

        # ── Stage 3: 宏观大纲 ──
        outline = None
        try:
            yield _evt("outline", status="start")
            logger.info("[bootstrap] 开始生成大纲")
            outline = await self._gen_outline(context, novel.world_setting or "")
            saved_count = self._save_outline(novel_id, outline)
            self.db.commit()
            logger.info("[bootstrap] 大纲生成完成，保存 %d 个节点", saved_count)
            yield _evt("outline", status="done", data=outline, saved_count=saved_count)
        except Exception as e:
            self.db.rollback()
            logger.exception("[bootstrap] 大纲生成失败")
            yield _evt("outline", status="error", message=f"大纲生成失败: {str(e)[:200]}")

        # ── 完成 ──
        try:
            novel.status = "writing"
            self.db.commit()
        except Exception:
            self.db.rollback()
        yield _evt("complete", novel_id=novel_id)

    # ── 单阶段重新生成（公开方法） ────────────────────────────────

    async def regenerate_stage(self, novel_id: str, stage: str) -> dict:
        """重新生成单个阶段：world / characters / outline"""
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        if not novel:
            raise ValueError("小说不存在")

        context = {
            "title": novel.title,
            "genre": novel.genre,
            "tags": novel.tags,
            "synopsis": novel.synopsis or "暂无",
            "premise": novel.premise or "暂无",
            "target_chapters": novel.target_chapter_count or 200,
            "words_per_chapter": novel.words_per_chapter or 2000,
        }

        if stage == "world":
            # 清除旧世界观
            self.db.query(WorldItem).filter_by(novel_id=novel_id).delete()
            self.db.flush()
            data = await self._gen_world(context)
            saved = self._save_world(novel_id, data)
            novel.world_setting = json.dumps(data, ensure_ascii=False)[:4000]
            self.db.commit()
            return {"stage": "world", "data": data, "saved_count": saved}

        elif stage == "characters":
            self.db.query(Character).filter_by(novel_id=novel_id).delete()
            self.db.flush()
            data = await self._gen_characters(context, novel.world_setting or "")
            saved = self._save_characters(novel_id, data)
            self.db.commit()
            return {"stage": "characters", "data": data, "saved_count": saved}

        elif stage == "outline":
            self.db.query(OutlineNode).filter_by(novel_id=novel_id).delete()
            self.db.flush()
            data = await self._gen_outline(context, novel.world_setting or "")
            saved = self._save_outline(novel_id, data)
            self.db.commit()
            return {"stage": "outline", "data": data, "saved_count": saved}

        else:
            raise ValueError(f"未知阶段: {stage}")

    # ── 世界观生成 ──────────────────────────────────────────────

    async def _gen_world(self, ctx: dict) -> dict:
        llm = self._resolver.get_llm_for_stage("outline_planning")
        system = self._prompt_loader.get_prompt("outline_planning", name="世界观生成")
        if not system:
            system = _WORLD_SYSTEM
        config = GenerationConfig(system=system, max_tokens=4096, temperature=0.8)

        user_prompt = f"""请为以下小说生成世界观设定：

【标题】{ctx['title']}
【题材】{ctx['genre']}
【标签】{ctx['tags']}
【简介】{ctx['synopsis']}

请生成完整的世界观设定，输出严格 JSON 格式。"""

        result = await llm.generate(user_prompt, config)
        return _extract_json(result.content)

    def _save_world(self, novel_id: str, data: dict) -> int:
        """将世界观条目写入 world_items 表，返回保存数量"""
        count = 0
        items = data.get("items", data.get("world_items", []))
        if isinstance(data, dict) and not items:
            # 如果是扁平结构，直接包装
            items = [{"category": k, "name": k, "description": str(v)}
                     for k, v in data.items() if k not in ("items", "world_items")]
        for item in items[:20]:  # 限制最多20条
            wi = WorldItem(
                id=str(uuid.uuid4()),
                novel_id=novel_id,
                category=item.get("category", "rule"),
                name=item.get("name", "未命名"),
                description=item.get("description", ""),
                properties=json.dumps(item.get("properties", {}), ensure_ascii=False),
            )
            self.db.add(wi)
            count += 1
        self.db.flush()
        return count

    # ── 人物生成 ──────────────────────────────────────────────

    async def _gen_characters(self, ctx: dict, world_setting: str) -> list[dict]:
        llm = self._resolver.get_llm_for_stage("outline_planning")
        system = self._prompt_loader.get_prompt("outline_planning", name="核心人物生成")
        if not system:
            system = _CHARACTERS_SYSTEM
        config = GenerationConfig(system=system, max_tokens=4096, temperature=0.7)

        user_prompt = f"""请为以下小说生成核心人物设定：

【标题】{ctx['title']}
【题材】{ctx['genre']}
【简介】{ctx['synopsis']}
【世界设定】{world_setting[:1500]}

请生成 3-6 个核心人物，输出严格 JSON 数组。"""

        result = await llm.generate(user_prompt, config)
        raw = _extract_json(result.content)
        return raw if isinstance(raw, list) else raw.get("characters", [])

    def _save_characters(self, novel_id: str, characters: list[dict]) -> int:
        count = 0
        for ch in characters[:8]:
            char = Character(
                id=str(uuid.uuid4()),
                novel_id=novel_id,
                name=ch.get("name", "未命名"),
                role=ch.get("role", "supporting"),
                description=ch.get("description", ""),
                traits=json.dumps(ch.get("traits", []), ensure_ascii=False),
            )
            self.db.add(char)
            count += 1
        self.db.flush()
        return count

    # ── 大纲生成 ──────────────────────────────────────────────

    async def _gen_outline(self, ctx: dict, world_setting: str) -> dict:
        llm = self._resolver.get_llm_for_stage("outline_planning")
        system = self._prompt_loader.get_prompt("outline_planning", name="极速宏观规划·破城槌")
        if not system:
            system = _OUTLINE_SYSTEM
        config = GenerationConfig(system=system, max_tokens=8192, temperature=0.8)

        user_prompt = f"""请为以下小说生成宏观大纲：

【标题】{ctx['title']}
【题材】{ctx['genre']}
【简介】{ctx['synopsis']}
【世界设定】{world_setting[:2000]}
【目标章数】约 {ctx['target_chapters']} 章
【每章字数】约 {ctx['words_per_chapter']} 字

请生成卷/幕结构大纲，输出严格 JSON，格式如下：
{{"volumes": [
  {{
    "title": "卷名",
    "summary": "本卷核心冲突与剧情概述",
    "volume_climax": "本卷高潮事件",
    "chapters": [
      {{"title": "章节标题", "summary": "本章剧情概要（50-100字）"}}
    ]
  }}
]}}
注意：每卷必须包含 chapters 数组，每章必须有 title 和 summary。"""

        # 最多重试 2 次（thinking 模型可能首次只返回思考过程）
        for attempt in range(3):
            result = await llm.generate(user_prompt, config)
            logger.info("[_gen_outline] attempt=%d, raw length=%d, first 200: %s",
                         attempt, len(result.content), result.content[:200])
            try:
                parsed = _extract_json(result.content)
                logger.info("[_gen_outline] parsed type=%s, keys=%s",
                             type(parsed).__name__,
                             list(parsed.keys()) if isinstance(parsed, dict) else len(parsed))
                return parsed
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning("[_gen_outline] JSON 提取失败 (attempt %d): %s", attempt, e)
                if attempt < 2:
                    # 加更强的 JSON-only 指令再试
                    user_prompt = f"""你上一次没有输出有效 JSON，请直接输出纯 JSON（不要任何解释文字）。

{user_prompt}

重要：请只输出一个 JSON 对象，格式为 {{"volumes": [...]}}，不要其他任何文字。"""
                    await asyncio.sleep(2)
                else:
                    raise

    def _save_outline(self, novel_id: str, outline: dict) -> int:
        """将大纲写入 outline_nodes 表，返回保存节点数"""
        count = 0

        # ── 深度解包：LLM 可能多包一层 novel_outline / outline 等 ──
        if isinstance(outline, dict):
            for wrapper_key in ("novel_outline", "outline_data", "data"):
                inner = outline.get(wrapper_key)
                if isinstance(inner, dict):
                    outline = inner
                    break
                elif isinstance(inner, list):
                    outline = inner
                    break

        # ── 提取卷列表，兼容多种 key 名 ──
        if isinstance(outline, list):
            volumes = outline
        else:
            volumes = None
            for k in ("volumes", "acts", "卷", "outline", "arcs", "parts"):
                v = outline.get(k)
                if v and isinstance(v, list):
                    volumes = v
                    break
            if not volumes:
                # 最后兜底：遍历所有 value 找第一个 list[dict]
                for v in outline.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        volumes = v
                        break
            if not volumes:
                volumes = []
                logger.warning("[_save_outline] 无法识别大纲结构，keys=%s", list(outline.keys()) if isinstance(outline, dict) else type(outline).__name__)

        order = 0
        for vol in volumes[:20]:
            vol_id = str(uuid.uuid4())
            # 兼容 title / volume_title / 卷名
            vol_title = vol.get("title") or vol.get("volume_title") or vol.get("卷名") or f"第{order+1}卷"
            vol_summary = vol.get("summary") or vol.get("core_conflict") or vol.get("描述") or ""
            vol_node = OutlineNode(
                id=vol_id,
                novel_id=novel_id,
                parent_id=None,
                level="volume",
                title=vol_title,
                summary=vol_summary,
                sort_order=order,
                metadata_json=json.dumps({
                    k: vol.get(k) for k in ("chapter_range", "map_and_tier", "volume_climax", "catharsis_release")
                    if vol.get(k)
                }, ensure_ascii=False),
            )
            self.db.add(vol_node)
            count += 1
            order += 1

            # ── 子节点（幕/章/弧）— 兼容多种 key 名 ──
            children = None
            for k in ("chapters", "acts", "scenes", "plot_arcs", "子章节", "章节", "arcs",
                       "chapter_list", "episode_list", "episodes", "sub_arcs", "beats"):
                c = vol.get(k)
                if c and isinstance(c, list):
                    children = c
                    break
            # 兜底：遍历所有 value 找第一个 list[dict]（排除已知非章节字段）
            if not children:
                skip_keys = {"tags", "themes", "keywords", "characters", "foreshadows",
                             "foreshadows_to_plant", "foreshadows_to_pay_off",
                             "key_characters", "character_arcs"}
                for k, v in vol.items():
                    if k in skip_keys:
                        continue
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        children = v
                        logger.info("[_save_outline] 卷 '%s' 使用兜底 key='%s' 作为章节列表 (%d items)",
                                    vol_title, k, len(v))
                        break
            if not children:
                children = []

            for j, ch in enumerate(children[:50]):
                ch_title = ch.get("title") or ch.get("arc") or ch.get("标题") or f"第{j+1}章"
                ch_summary = ch.get("summary") or ch.get("detail") or ch.get("描述") or ""
                ch_node = OutlineNode(
                    id=str(uuid.uuid4()),
                    novel_id=novel_id,
                    parent_id=vol_id,
                    level="chapter",
                    title=ch_title,
                    summary=ch_summary,
                    sort_order=j,
                )
                self.db.add(ch_node)
                count += 1
        self.db.flush()
        return count


# ── Fallback System Prompts ────────────────────────────────────

_WORLD_SYSTEM = """你是一位资深网文世界观架构师。请根据用户提供的小说设定，生成完整的世界观。

输出格式要求（严格 JSON）：
{
  "items": [
    {
      "category": "power_system",
      "name": "力量体系名称",
      "description": "详细描述",
      "properties": {"levels": ["境界1", "境界2"]}
    },
    {
      "category": "location",
      "name": "地名",
      "description": "地理描述"
    },
    {
      "category": "faction",
      "name": "势力名",
      "description": "势力描述"
    },
    {
      "category": "rule",
      "name": "世界规则",
      "description": "规则描述"
    },
    {
      "category": "history",
      "name": "历史事件",
      "description": "事件描述"
    }
  ]
}

要求：
1. 力量体系必须有清晰的等级划分（至少5级）
2. 至少3个重要地点
3. 至少3个主要势力
4. 2-3条世界核心规则
5. 1-2个关键历史事件
6. 所有设定要为故事冲突和升级提供空间"""

_CHARACTERS_SYSTEM = """你是一位资深网文人物设计师。请根据小说设定生成核心人物。

输出格式要求（严格 JSON 数组）：
[
  {
    "name": "角色名",
    "role": "protagonist",
    "description": "外貌+性格+背景简述（100字以内）",
    "traits": ["特质1", "特质2", "特质3"],
    "motivation": "核心动机",
    "secret": "隐藏的秘密/伏笔",
    "relationships": [{"target": "另一角色名", "relation": "关系描述"}]
  }
]

role 取值：protagonist / antagonist / supporting / mentor / love_interest

要求：
1. 主角1人，必须有明确的金手指和成长路线
2. 主要反派1-2人，与主角有深层矛盾
3. 核心配角2-3人（师长/伙伴/红颜）
4. 每个角色至少3个性格特质
5. 角色间要有足够的戏剧张力"""

_OUTLINE_SYSTEM = """你是一位资深网文大纲策划师。请生成结构化的宏观大纲。

输出格式（严格 JSON）：
{
  "volumes": [
    {
      "title": "卷名",
      "summary": "本卷概要（50字）",
      "chapter_range": [1, 50],
      "core_conflict": "核心冲突",
      "power_level": "主角此卷实力范围",
      "chapters": [
        {"title": "章节标题", "summary": "章节概要（30字）"}
      ]
    }
  ],
  "main_plot_threads": ["主线1", "主线2"],
  "foreshadow_plan": ["伏笔1", "伏笔2"]
}

要求：
1. 3-5卷结构，每卷有明确的核心冲突
2. 前3卷每卷列10个章节概要，后续卷每卷列5个关键章节
3. 每卷有升级/换地图/换敌人
4. 至少3条贯穿全书的主线
5. 至少3个需要长线回收的伏笔"""


def _evt(stage: str, **kwargs) -> str:
    return json.dumps({"stage": stage, **kwargs}, ensure_ascii=False)
