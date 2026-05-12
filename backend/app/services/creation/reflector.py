"""Reflector Agent — 将 Observer 提取的事实写入真相文件

职责：
1. 接收 Observer 输出的 facts 列表
2. 按 category 分类映射到 7 维真相文件
3. 对每个真相文件生成 JSON delta
4. 代码层校验后写入 DB（TruthFile 表）

真相文件映射：
  characters + physics + emotions → current_state
  resources                       → particle_ledger
  foreshadows                     → pending_hooks
  (chapter summary auto)          → chapter_summaries
  relations                       → character_matrix
  emotions (arc tracking)         → emotional_arcs
  information + relations         → subplot_board
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.novel import TruthFile, TRUTH_FILE_KEYS

logger = logging.getLogger(__name__)

# Observer fact category → truth file key(s) 映射
_CATEGORY_TO_FILE: dict[str, list[str]] = {
    "characters":   ["current_state"],
    "locations":    ["current_state"],
    "resources":    ["particle_ledger"],
    "relations":    ["character_matrix", "subplot_board"],
    "emotions":     ["emotional_arcs", "current_state"],
    "information":  ["subplot_board"],
    "foreshadows":  ["pending_hooks"],
    "timeline":     ["current_state"],
    "physics":      ["current_state"],
}


class Reflector:
    """将提取的事实 delta 写入真相文件"""

    def __init__(self, db: Session):
        self.db = db

    async def apply_delta(
        self,
        novel_id: str,
        chapter_number: int,
        facts: list[dict],
    ) -> int:
        """将 facts 按 category 分组，merge 到对应的真相文件

        Returns:
            更新的真相文件条目数
        """
        if not facts:
            return 0

        # 按目标真相文件分组
        file_deltas: dict[str, list[dict]] = {}
        for fact in facts:
            cat = fact.get("category", "")
            target_files = _CATEGORY_TO_FILE.get(cat, ["current_state"])
            for fk in target_files:
                file_deltas.setdefault(fk, []).append(fact)

        # 自动生成本章摘要条目
        summary_entry = self._build_chapter_summary(chapter_number, facts)
        file_deltas.setdefault("chapter_summaries", []).append(summary_entry)

        updated = 0
        for file_key, delta_facts in file_deltas.items():
            if file_key not in TRUTH_FILE_KEYS:
                continue
            self._merge_into_truth_file(novel_id, file_key, chapter_number, delta_facts)
            updated += 1

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        logger.info(
            "[Reflector] novel=%s ch=%d → updated %d truth files (%d facts)",
            novel_id, chapter_number, updated, len(facts),
        )
        return updated

    def _merge_into_truth_file(
        self,
        novel_id: str,
        file_key: str,
        chapter_number: int,
        new_facts: list[dict],
    ) -> None:
        """合并新事实到真相文件（追加模式，按章节分组）"""
        tf = (
            self.db.query(TruthFile)
            .filter_by(novel_id=novel_id, file_key=file_key)
            .first()
        )

        if tf:
            # 已有文件 → 追加
            try:
                existing = json.loads(tf.data_json) if tf.data_json else {}
            except json.JSONDecodeError:
                existing = {}

            # 按章节号分组存储
            chapters_data = existing.get("chapters", {})
            ch_key = str(chapter_number)

            # 替换该章节的数据（重新结算时覆盖）
            chapters_data[ch_key] = new_facts

            existing["chapters"] = chapters_data
            existing["last_updated"] = datetime.now(timezone.utc).isoformat()

            # 更新聚合视图
            existing["aggregate"] = self._build_aggregate(file_key, chapters_data)

            tf.data_json = json.dumps(existing, ensure_ascii=False)
            tf.content = self._render_markdown(file_key, existing)
            tf.version += 1
            tf.last_chapter = max(tf.last_chapter, chapter_number)
            tf.updated_at = datetime.now(timezone.utc)
        else:
            # 新建真相文件
            data = {
                "chapters": {str(chapter_number): new_facts},
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            data["aggregate"] = self._build_aggregate(file_key, data["chapters"])

            tf = TruthFile(
                id=str(uuid.uuid4()),
                novel_id=novel_id,
                file_key=file_key,
                data_json=json.dumps(data, ensure_ascii=False),
                content=self._render_markdown(file_key, data),
                version=1,
                last_chapter=chapter_number,
            )
            self.db.add(tf)

        self.db.flush()

    def _build_aggregate(self, file_key: str, chapters_data: dict) -> dict:
        """构建聚合视图 — 将各章节数据汇总"""
        all_facts = []
        for ch_facts in chapters_data.values():
            if isinstance(ch_facts, list):
                all_facts.extend(ch_facts)

        if file_key == "current_state":
            # 按 subject 汇总最新状态
            state = {}
            for f in all_facts:
                subj = f.get("subject", "")
                if subj:
                    state[subj] = {
                        "last_action": f.get("predicate", ""),
                        "detail": f.get("detail", ""),
                        "category": f.get("category", ""),
                    }
            return state

        elif file_key == "particle_ledger":
            # 按物品汇总
            ledger = {}
            for f in all_facts:
                subj = f.get("subject", "")
                if subj:
                    if subj not in ledger:
                        ledger[subj] = []
                    ledger[subj].append({
                        "change": f.get("predicate", ""),
                        "detail": f.get("detail", ""),
                    })
            return ledger

        elif file_key == "pending_hooks":
            # 按状态分组
            hooks = {"planted": [], "tracked": [], "paid_off": []}
            for f in all_facts:
                status = "planted"
                detail = f.get("detail", "") or f.get("predicate", "")
                # 从 detail 中推断状态
                for s in ("paid_off", "tracked", "planted"):
                    if s in str(f.get("predicate", "")).lower() or s in str(detail).lower():
                        status = s
                        break
                hooks.setdefault(status, []).append({
                    "subject": f.get("subject", ""),
                    "description": detail,
                })
            return hooks

        elif file_key == "character_matrix":
            # 关系对
            pairs = []
            for f in all_facts:
                pairs.append({
                    "from": f.get("subject", ""),
                    "to": f.get("object", ""),
                    "relation": f.get("predicate", ""),
                    "detail": f.get("detail", ""),
                })
            return {"relations": pairs}

        elif file_key == "emotional_arcs":
            # 按角色追踪
            arcs = {}
            for f in all_facts:
                subj = f.get("subject", "")
                if subj:
                    if subj not in arcs:
                        arcs[subj] = []
                    arcs[subj].append({
                        "emotion": f.get("predicate", ""),
                        "detail": f.get("detail", ""),
                    })
            return arcs

        elif file_key == "chapter_summaries":
            return {"count": len(chapters_data)}

        elif file_key == "subplot_board":
            subplots = []
            for f in all_facts:
                subplots.append({
                    "subject": f.get("subject", ""),
                    "event": f.get("predicate", ""),
                    "detail": f.get("detail", ""),
                })
            return {"events": subplots}

        return {}

    def _render_markdown(self, file_key: str, data: dict) -> str:
        """将真相文件渲染为可读 Markdown"""
        agg = data.get("aggregate", {})
        lines = [f"# 真相文件: {file_key}", ""]

        if file_key == "current_state":
            lines.append("## 当前世界状态")
            for subj, info in agg.items():
                lines.append(f"- **{subj}**: {info.get('last_action', '')} — {info.get('detail', '')}")

        elif file_key == "particle_ledger":
            lines.append("## 资源账本")
            for item, changes in agg.items():
                lines.append(f"### {item}")
                for c in changes:
                    lines.append(f"  - {c.get('change', '')} {c.get('detail', '')}")

        elif file_key == "pending_hooks":
            for status in ("planted", "tracked", "paid_off"):
                hooks = agg.get(status, [])
                if hooks:
                    label = {"planted": "未闭合", "tracked": "推进中", "paid_off": "已回收"}[status]
                    lines.append(f"## 伏笔 — {label}")
                    for h in hooks:
                        lines.append(f"- [{h.get('subject', '')}] {h.get('description', '')}")

        elif file_key == "character_matrix":
            lines.append("## 角色关系矩阵")
            for r in agg.get("relations", []):
                lines.append(f"- {r.get('from', '')} → {r.get('to', '')}: {r.get('relation', '')} ({r.get('detail', '')})")

        elif file_key == "emotional_arcs":
            lines.append("## 情感弧线")
            for char, entries in agg.items():
                lines.append(f"### {char}")
                for e in entries:
                    lines.append(f"  - {e.get('emotion', '')} — {e.get('detail', '')}")

        elif file_key == "chapter_summaries":
            lines.append(f"## 章节摘要 (共 {agg.get('count', 0)} 章)")
            chapters = data.get("chapters", {})
            for ch_num in sorted(chapters.keys(), key=lambda x: int(x)):
                entries = chapters[ch_num]
                if entries and isinstance(entries, list):
                    first = entries[0]
                    lines.append(f"- 第{ch_num}章: {first.get('detail', first.get('predicate', ''))}")

        elif file_key == "subplot_board":
            lines.append("## 支线进度板")
            for evt in agg.get("events", []):
                lines.append(f"- [{evt.get('subject', '')}] {evt.get('event', '')} — {evt.get('detail', '')}")

        return "\n".join(lines)

    def _build_chapter_summary(self, chapter_number: int, facts: list[dict]) -> dict:
        """从 facts 自动生成本章摘要条目"""
        # 提取出场角色
        chars = set()
        events = []
        for f in facts:
            if f.get("category") == "characters":
                chars.add(f.get("subject", ""))
            if f.get("category") in ("characters", "foreshadows", "relations"):
                events.append(f.get("detail", f.get("predicate", "")))

        summary = "；".join(events[:5]) if events else "日常推进"
        return {
            "category": "chapter_summary",
            "subject": f"第{chapter_number}章",
            "predicate": summary,
            "detail": f"出场: {'、'.join(chars)}" if chars else "",
            "confidence": 1.0,
        }
