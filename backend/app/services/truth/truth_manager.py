"""真相文件管理器 — 7 维度长期记忆系统

借鉴 InkOS 的 Truth Files 体系：
- current_state   : 世界状态 / 角色位置 / 关系网络 / 已知信息
- particle_ledger : 资源账本 / 物品 / 金钱 / 物资衰减
- pending_hooks   : 未闭合伏笔（open / progressing / deferred / resolved）
- chapter_summaries : 各章摘要 / 出场人物 / 关键事件 / 状态变化
- subplot_board   : 支线进度板 / A/B/C 线状态 / 停滞检测
- emotional_arcs  : 按角色追踪情绪变化和成长弧线
- character_matrix: 角色交互矩阵 / 相遇记录 / 信息边界

每个真相文件有两个表示：
- content  : 人类可读的 markdown 投影
- data_json: 机器可读的结构化 JSON
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.models.novel import Novel, Chapter, TruthFile, TRUTH_FILE_KEYS
from app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)


# ── 初始化模板 ──────────────────────────────────────────────────

_INIT_TEMPLATES: dict[str, dict] = {
    "current_state": {
        "content": "# 世界状态\n\n> 尚未生成。写完第一章后自动提取。\n",
        "data": {
            "locations": [],
            "character_positions": {},
            "known_facts": [],
            "active_relationships": [],
            "world_rules": [],
        },
    },
    "particle_ledger": {
        "content": "# 资源账本\n\n> 尚未生成。写完第一章后自动提取。\n",
        "data": {
            "items": [],
            "currency": {},
            "consumables": [],
            "decay_log": [],
        },
    },
    "pending_hooks": {
        "content": "# 伏笔追踪\n\n> 尚未生成。写完第一章后自动提取。\n",
        "data": {
            "hooks": [],
        },
    },
    "chapter_summaries": {
        "content": "# 章节摘要\n\n> 尚未生成。写完第一章后自动提取。\n",
        "data": {
            "summaries": [],
        },
    },
    "subplot_board": {
        "content": "# 支线进度板\n\n> 尚未生成。写完第一章后自动提取。\n",
        "data": {
            "subplots": [],
        },
    },
    "emotional_arcs": {
        "content": "# 情感弧线\n\n> 尚未生成。写完第一章后自动提取。\n",
        "data": {
            "arcs": {},
        },
    },
    "character_matrix": {
        "content": "# 角色交互矩阵\n\n> 尚未生成。写完第一章后自动提取。\n",
        "data": {
            "characters": [],
            "interactions": [],
            "info_boundaries": {},
        },
    },
}


# ── 提取 prompt ─────────────────────────────────────────────────

_EXTRACT_SYSTEM = """你是一位专业的小说结构分析师。请根据给定的章节正文和已有真相文件，**增量更新**以下 7 个维度的结构化数据。

输出要求：严格 JSON，包含以下 7 个顶级 key（每个 key 对应一个真相文件）。
只输出 JSON，不要任何解释文字。

```json
{
  "current_state": {
    "locations": [{"name": "地名", "description": "描述", "characters_present": ["角色名"]}],
    "character_positions": {"角色名": "当前位置"},
    "known_facts": ["已确认的事实"],
    "active_relationships": [{"from": "A", "to": "B", "type": "关系类型", "description": "描述"}],
    "world_rules": ["世界规则/设定"]
  },
  "particle_ledger": {
    "items": [{"name": "物品名", "owner": "拥有者", "quantity": 1, "status": "正常/消耗/丢失", "source_chapter": 1}],
    "currency": {"角色名": {"amount": 0, "unit": "货币单位"}},
    "consumables": [{"name": "名称", "remaining": 0, "decay_rate": "描述"}]
  },
  "pending_hooks": {
    "hooks": [{"id": "hook_N", "description": "伏笔描述", "planted_chapter": 1, "status": "open|progressing|deferred|resolved", "resolved_chapter": null, "importance": "high|medium|low"}]
  },
  "chapter_summaries": {
    "summaries": [{"chapter": 1, "title": "章节标题", "summary": "100字摘要", "characters": ["出场角色"], "key_events": ["事件"], "state_changes": ["状态变化"]}]
  },
  "subplot_board": {
    "subplots": [{"id": "sub_N", "name": "支线名", "description": "描述", "status": "active|stalled|resolved", "last_advanced_chapter": 1, "priority": "A|B|C"}]
  },
  "emotional_arcs": {
    "arcs": {"角色名": [{"chapter": 1, "emotion": "情绪", "intensity": 7, "trigger": "触发事件", "growth_note": "成长描述"}]}
  },
  "character_matrix": {
    "characters": ["角色列表"],
    "interactions": [{"from": "A", "to": "B", "chapter": 1, "type": "对话/冲突/合作/...", "description": "互动描述"}],
    "info_boundaries": {"角色名": ["该角色知道的信息"]}
  }
}
```

增量规则：
- 对已有数据做 **追加或更新**，不要删除之前章节的信息
- pending_hooks 中已 resolved 的伏笔保留但标记 resolved
- chapter_summaries 追加新章，保留旧章摘要
- emotional_arcs 追加新章节的情感节点
- character_matrix 追加新交互，更新信息边界"""


class TruthFileManager:
    """真相文件 CRUD + LLM 提取"""

    def __init__(self, db: Session):
        self.db = db
        self._resolver = StageModelResolver(db)
        self._prompt_loader = PromptLoader(db)

    # ── 初始化 ──────────────────────────────────────────────────

    def ensure_truth_files(self, novel_id: str) -> list[dict]:
        """确保小说拥有全部 7 个真相文件，缺失的自动创建"""
        existing = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id)
            .all()
        )
        existing_keys = {tf.file_key for tf in existing}

        created = []
        for key in TRUTH_FILE_KEYS:
            if key not in existing_keys:
                tpl = _INIT_TEMPLATES[key]
                tf = TruthFile(
                    novel_id=novel_id,
                    file_key=key,
                    content=tpl["content"],
                    data_json=json.dumps(tpl["data"], ensure_ascii=False),
                )
                self.db.add(tf)
                created.append(key)

        if created:
            self.db.commit()
            logger.info("为小说 %s 创建真相文件: %s", novel_id, created)

        return self.list_truth_files(novel_id)

    # ── CRUD ────────────────────────────────────────────────────

    def list_truth_files(self, novel_id: str) -> list[dict]:
        """列出小说的所有真相文件"""
        rows = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id)
            .order_by(TruthFile.file_key)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    def get_truth_file(self, novel_id: str, file_key: str) -> Optional[dict]:
        """获取单个真相文件"""
        row = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id, file_key=file_key)
            .first()
        )
        return self._to_dict(row) if row else None

    def update_truth_file(
        self,
        novel_id: str,
        file_key: str,
        *,
        content: Optional[str] = None,
        data_json: Optional[dict] = None,
        last_chapter: Optional[int] = None,
    ) -> dict:
        """手动更新真相文件（人工编辑）"""
        row = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id, file_key=file_key)
            .first()
        )
        if not row:
            raise ValueError(f"真相文件不存在: {file_key}")

        if content is not None:
            row.content = content
        if data_json is not None:
            row.data_json = json.dumps(data_json, ensure_ascii=False)
        if last_chapter is not None:
            row.last_chapter = last_chapter
        row.version += 1
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return self._to_dict(row)

    # ── LLM 提取（章后管线调用）──────────────────────────────────

    async def extract_and_update(
        self, novel_id: str, chapter_number: int
    ) -> dict:
        """从指定章节正文提取事实，增量更新全部真相文件

        Returns:
            更新后的所有真相文件 dict
        """
        # 确保真相文件存在
        self.ensure_truth_files(novel_id)

        # 获取章节正文
        chapter = (
            self.db.query(Chapter)
            .filter_by(novel_id=novel_id, number=chapter_number)
            .first()
        )
        if not chapter or not chapter.content:
            raise ValueError(f"章节内容为空: {novel_id} #{chapter_number}")

        # 获取小说信息
        novel = self.db.query(Novel).filter_by(id=novel_id).first()
        novel_title = novel.title if novel else "未知小说"

        # 获取已有真相文件作为上下文
        existing = {}
        for key in TRUTH_FILE_KEYS:
            tf = self.get_truth_file(novel_id, key)
            if tf:
                existing[key] = tf.get("data_json", {})

        # 调用 LLM
        llm = self._resolver.get_llm_for_stage("post_chapter_pipeline")

        system = self._prompt_loader.get_prompt("truth_file_extract")
        if not system:
            system = _EXTRACT_SYSTEM

        config = GenerationConfig(
            system=system,
            max_tokens=8192,
            temperature=0.3,
        )

        user_prompt = self._build_extract_prompt(
            novel_title, chapter_number, chapter.content, existing
        )

        result = await llm.generate(user_prompt, config)
        extracted = self._parse_json(result.content)

        if not extracted:
            logger.warning("真相文件提取失败: 无法解析 LLM 输出")
            return {"error": "提取失败", "raw": result.content[:500]}

        # 增量更新各真相文件
        updated_keys = []
        for key in TRUTH_FILE_KEYS:
            if key in extracted and extracted[key]:
                self._apply_delta(novel_id, key, extracted[key], chapter_number)
                updated_keys.append(key)

        logger.info(
            "真相文件提取完成: %s #%d, 更新了 %s",
            novel_id, chapter_number, updated_keys,
        )
        return {
            "updated_keys": updated_keys,
            "chapter": chapter_number,
            "files": self.list_truth_files(novel_id),
        }

    # ── 供 ContextBuilder 使用的快捷方法 ───────────────────────

    def get_context_snapshot(self, novel_id: str) -> dict:
        """返回所有真相文件的 data_json，用于写作上下文构建"""
        result = {}
        rows = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id)
            .all()
        )
        for r in rows:
            try:
                result[r.file_key] = json.loads(r.data_json) if r.data_json else {}
            except json.JSONDecodeError:
                result[r.file_key] = {}
        return result

    def get_markdown_snapshot(self, novel_id: str) -> str:
        """返回所有真相文件的 markdown 内容拼接，用于 prompt 注入"""
        rows = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id)
            .order_by(TruthFile.file_key)
            .all()
        )
        parts = []
        key_names = {
            "current_state": "世界状态",
            "particle_ledger": "资源账本",
            "pending_hooks": "伏笔追踪",
            "chapter_summaries": "章节摘要",
            "subplot_board": "支线进度板",
            "emotional_arcs": "情感弧线",
            "character_matrix": "角色交互矩阵",
        }
        for r in rows:
            label = key_names.get(r.file_key, r.file_key)
            parts.append(f"## {label}\n\n{r.content}")
        return "\n\n---\n\n".join(parts) if parts else ""

    # ── 内部工具 ────────────────────────────────────────────────

    def _build_extract_prompt(
        self,
        novel_title: str,
        chapter_number: int,
        content: str,
        existing: dict,
    ) -> str:
        """构建提取用的 user prompt"""
        # 截断正文防止上下文爆炸
        max_content = 8000
        truncated = content[:max_content]
        if len(content) > max_content:
            truncated += f"\n\n... (正文共 {len(content)} 字，已截断)"

        # 已有真相文件摘要（只传关键数据，控制 token）
        existing_summary = json.dumps(existing, ensure_ascii=False, indent=None)
        if len(existing_summary) > 4000:
            existing_summary = existing_summary[:4000] + "...(已截断)"

        return f"""请分析以下章节，增量更新真相文件。

【小说】{novel_title}
【章节号】第 {chapter_number} 章
【字数】{len(content)} 字

---已有真相文件---
{existing_summary}

---本章正文---
{truncated}
---正文结束---

请输出完整的 7 个维度 JSON 更新。保留已有数据，追加本章新信息。"""

    def _apply_delta(
        self, novel_id: str, file_key: str, new_data: dict, chapter_number: int
    ) -> None:
        """将 LLM 输出的某个维度数据写入真相文件"""
        row = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id, file_key=file_key)
            .first()
        )
        if not row:
            return

        row.data_json = json.dumps(new_data, ensure_ascii=False, indent=2)
        row.content = self._data_to_markdown(file_key, new_data)
        row.last_chapter = chapter_number
        row.version += 1
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()

    def _data_to_markdown(self, file_key: str, data: dict) -> str:
        """将结构化 JSON 转为人类可读的 markdown"""
        converters = {
            "current_state": self._md_current_state,
            "particle_ledger": self._md_particle_ledger,
            "pending_hooks": self._md_pending_hooks,
            "chapter_summaries": self._md_chapter_summaries,
            "subplot_board": self._md_subplot_board,
            "emotional_arcs": self._md_emotional_arcs,
            "character_matrix": self._md_character_matrix,
        }
        converter = converters.get(file_key)
        if converter:
            try:
                return converter(data)
            except Exception as e:
                logger.warning("markdown 转换失败 (%s): %s", file_key, e)
        return f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"

    @staticmethod
    def _md_current_state(d: dict) -> str:
        lines = ["# 世界状态\n"]
        for loc in d.get("locations", []):
            chars = ", ".join(loc.get("characters_present", []))
            lines.append(f"- **{loc['name']}**: {loc.get('description', '')} {'[' + chars + ']' if chars else ''}")
        if d.get("character_positions"):
            lines.append("\n## 角色位置")
            for char, pos in d["character_positions"].items():
                lines.append(f"- {char} → {pos}")
        if d.get("active_relationships"):
            lines.append("\n## 关系网络")
            for rel in d["active_relationships"]:
                lines.append(f"- {rel['from']} ←{rel.get('type', '?')}→ {rel['to']}: {rel.get('description', '')}")
        if d.get("known_facts"):
            lines.append("\n## 已知事实")
            for fact in d["known_facts"]:
                lines.append(f"- {fact}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _md_particle_ledger(d: dict) -> str:
        lines = ["# 资源账本\n"]
        for item in d.get("items", []):
            status = f" ({item['status']})" if item.get("status") else ""
            lines.append(f"- **{item['name']}** x{item.get('quantity', '?')} — 持有者: {item.get('owner', '?')}{status}")
        if d.get("currency"):
            lines.append("\n## 货币")
            for char, info in d["currency"].items():
                lines.append(f"- {char}: {info.get('amount', 0)} {info.get('unit', '')}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _md_pending_hooks(d: dict) -> str:
        lines = ["# 伏笔追踪\n"]
        status_icon = {"open": "🔵", "progressing": "🟡", "deferred": "⏸️", "resolved": "✅"}
        for hook in d.get("hooks", []):
            icon = status_icon.get(hook.get("status", "open"), "❓")
            lines.append(f"- {icon} **{hook.get('description', '')}** (ch{hook.get('planted_chapter', '?')}, {hook.get('importance', 'medium')})")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _md_chapter_summaries(d: dict) -> str:
        lines = ["# 章节摘要\n"]
        for s in d.get("summaries", []):
            lines.append(f"### 第{s.get('chapter', '?')}章 {s.get('title', '')}")
            lines.append(f"{s.get('summary', '')}")
            if s.get("characters"):
                lines.append(f"- 出场: {', '.join(s['characters'])}")
            if s.get("key_events"):
                for e in s["key_events"]:
                    lines.append(f"- 事件: {e}")
            lines.append("")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _md_subplot_board(d: dict) -> str:
        lines = ["# 支线进度板\n"]
        status_icon = {"active": "🟢", "stalled": "🔴", "resolved": "✅"}
        for sp in d.get("subplots", []):
            icon = status_icon.get(sp.get("status", "active"), "❓")
            lines.append(f"- {icon} [{sp.get('priority', '?')}线] **{sp.get('name', '')}**: {sp.get('description', '')} (最后推进: ch{sp.get('last_advanced_chapter', '?')})")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _md_emotional_arcs(d: dict) -> str:
        lines = ["# 情感弧线\n"]
        for char, points in d.get("arcs", {}).items():
            lines.append(f"## {char}")
            for p in points:
                lines.append(f"- ch{p.get('chapter', '?')}: {p.get('emotion', '')} (强度{p.get('intensity', '?')}) — {p.get('trigger', '')} → {p.get('growth_note', '')}")
            lines.append("")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _md_character_matrix(d: dict) -> str:
        lines = ["# 角色交互矩阵\n"]
        if d.get("characters"):
            lines.append(f"角色列表: {', '.join(d['characters'])}\n")
        lines.append("## 交互记录")
        for inter in d.get("interactions", []):
            lines.append(f"- ch{inter.get('chapter', '?')}: {inter.get('from', '?')} ←{inter.get('type', '?')}→ {inter.get('to', '?')}: {inter.get('description', '')}")
        if d.get("info_boundaries"):
            lines.append("\n## 信息边界")
            for char, info_list in d["info_boundaries"].items():
                lines.append(f"- **{char}** 知道: {', '.join(info_list)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _to_dict(row: TruthFile) -> dict:
        try:
            data = json.loads(row.data_json) if row.data_json else {}
        except json.JSONDecodeError:
            data = {}
        return {
            "id": row.id,
            "novel_id": row.novel_id,
            "file_key": row.file_key,
            "content": row.content,
            "data_json": data,
            "version": row.version,
            "last_chapter": row.last_chapter,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _parse_json(text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON"""
        import re
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试从 ```json ... ``` 中提取
        m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # 尝试找第一个 { ... } 块
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
        return None
