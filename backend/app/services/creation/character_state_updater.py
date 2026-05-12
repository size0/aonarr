"""CharacterStateUpdater — 根据 Observer 事实自动回写 Character 模型

在 PostPipeline 中，Observer→Reflector 完成后调用此模块：
1. 从 facts 中提取角色状态变化（emotions/physics/relations）
2. 更新 Character.description 追加当前状态
3. 更新 Character.relationships JSON
4. 处理亲密度关键词映射
5. 处理角色存活状态（死亡/失踪 → 级联更新关系）

使用 NameAuthority 做名称归一化，确保事实中的别名映射到正确角色。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.novel import Character
from app.services.creation.name_authority import NameAuthority, normalize_name

logger = logging.getLogger(__name__)

# ── 亲密度调整关键词映射 ─────────────────────────────────────────
INTIMACY_ADJUSTMENTS: dict[str, int] = {
    # 正向
    "改善": 10, "加深": 15, "信任": 10, "亲近": 15,
    "友好": 10, "认可": 10, "合作": 5, "和解": 20,
    "喜欢": 15, "爱": 20, "尊敬": 10, "感激": 10,
    "好转": 10, "增进": 10, "亲密": 15, "忠诚": 10,
    # 负向
    "恶化": -10, "疏远": -15, "背叛": -30, "敌对": -25,
    "矛盾": -10, "冲突": -15, "怀疑": -10, "不信任": -15,
    "厌恶": -20, "仇恨": -25, "决裂": -30, "猜忌": -10,
    "紧张": -5, "破裂": -25, "反目": -25, "嫉妒": -10,
    # 特殊
    "初识": 0, "相遇": 0, "结盟": 10, "分离": -5,
}

# 死亡/退场关键词
_DEATH_KEYWORDS = {"死亡", "死", "身亡", "殒命", "牺牲", "战死", "被杀"}
_MISSING_KEYWORDS = {"失踪", "消失", "下落不明"}
_RETIRE_KEYWORDS = {"退场", "离去", "退隐", "离开"}


class CharacterStateUpdater:
    """根据 Observer 事实回写 Character 模型"""

    def __init__(self, db: Session):
        self.db = db

    def update_from_facts(
        self,
        novel_id: str,
        chapter_number: int,
        facts: list[dict],
    ) -> dict:
        """从 Observer 提取的 facts 更新角色状态

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            facts: Observer 提取的事实列表

        Returns:
            更新统计 dict
        """
        authority = NameAuthority.from_novel(self.db, novel_id)
        characters = self.db.query(Character).filter_by(novel_id=novel_id).all()
        char_by_name: dict[str, Character] = {}
        for c in characters:
            canonical = normalize_name(c.name)
            char_by_name[canonical] = c

        result = {
            "state_updated": 0,
            "relations_updated": 0,
            "survival_changed": 0,
            "changes": [],
        }

        # 按角色聚合事实
        char_facts: dict[str, list[dict]] = {}
        for fact in facts:
            subj = authority.resolve(fact.get("subject", ""), keep_unknown=False)
            if not subj:
                continue
            char_facts.setdefault(subj, []).append(fact)

        for char_name, facts_list in char_facts.items():
            character = char_by_name.get(char_name)
            if not character:
                continue

            # 1. 检查存活状态
            survival_change = self._check_survival(facts_list)
            if survival_change:
                self._apply_survival(
                    character, survival_change, chapter_number,
                    char_by_name, result
                )
                continue  # 死亡后不再更新其他状态

            # 2. 更新心理/物理状态
            state_changes = self._extract_state_changes(facts_list)
            if state_changes:
                self._apply_state(character, state_changes, chapter_number, result)

            # 3. 更新关系
            relation_facts = [f for f in facts_list if f.get("category") == "relations"]
            if relation_facts:
                self._apply_relations(
                    character, relation_facts, authority, char_by_name,
                    chapter_number, result
                )

        if result["state_updated"] + result["relations_updated"] + result["survival_changed"] > 0:
            self.db.commit()
            logger.info(
                "[CharacterStateUpdater] novel=%s ch=%d → 状态%d 关系%d 存活%d",
                novel_id, chapter_number,
                result["state_updated"], result["relations_updated"], result["survival_changed"],
            )

        return result

    def _check_survival(self, facts: list[dict]) -> Optional[str]:
        """检查是否有死亡/失踪/退场事实"""
        for f in facts:
            cat = f.get("category", "")
            detail = f.get("detail", "") + f.get("predicate", "")
            if cat in ("physics", "characters"):
                for kw in _DEATH_KEYWORDS:
                    if kw in detail:
                        return "deceased"
                for kw in _MISSING_KEYWORDS:
                    if kw in detail:
                        return "missing"
                for kw in _RETIRE_KEYWORDS:
                    if kw in detail:
                        return "retired"
        return None

    def _apply_survival(
        self,
        character: Character,
        status: str,
        chapter_number: int,
        char_by_name: dict[str, Character],
        result: dict,
    ) -> None:
        """应用存活状态变化，级联更新关系"""
        status_map = {"deceased": "死亡", "missing": "失踪", "retired": "退场"}
        desc_suffix = f"\n[第{chapter_number}章] 角色{status_map.get(status, status)}"
        character.description = (character.description or "") + desc_suffix
        result["survival_changed"] += 1
        result["changes"].append(f"{character.name}: {status_map.get(status, status)}")

        # 更新该角色的关系状态为 past
        try:
            rels = json.loads(character.relationships) if character.relationships else []
            for rel in rels:
                if isinstance(rel, dict):
                    rel["status"] = "past"
                    rel["note"] = f"因{status_map.get(status, status)}终止"
            character.relationships = json.dumps(rels, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

    def _extract_state_changes(self, facts: list[dict]) -> list[str]:
        """从 emotions/physics 事实中提取状态变化描述"""
        changes = []
        for f in facts:
            cat = f.get("category", "")
            if cat in ("emotions", "physics"):
                detail = f.get("detail", "") or f.get("predicate", "")
                if detail:
                    changes.append(detail)
        return changes

    def _apply_state(
        self,
        character: Character,
        changes: list[str],
        chapter_number: int,
        result: dict,
    ) -> None:
        """追加角色状态到 description"""
        change_text = "；".join(changes[:5])
        suffix = f"\n[第{chapter_number}章状态] {change_text}"

        # 控制 description 长度：保留最近的状态追加（最多保留5条）
        desc = character.description or ""
        existing_states = [l for l in desc.split("\n") if l.startswith("[第") and "章状态]" in l]
        if len(existing_states) >= 5:
            # 移除最旧的状态行
            oldest = existing_states[0]
            desc = desc.replace(oldest + "\n", "", 1).replace(oldest, "", 1)

        character.description = desc + suffix
        result["state_updated"] += 1
        result["changes"].append(f"{character.name}: {change_text[:50]}")

    def _apply_relations(
        self,
        character: Character,
        relation_facts: list[dict],
        authority: NameAuthority,
        char_by_name: dict[str, Character],
        chapter_number: int,
        result: dict,
    ) -> None:
        """从关系事实更新 Character.relationships JSON"""
        try:
            rels = json.loads(character.relationships) if character.relationships else []
        except (json.JSONDecodeError, TypeError):
            rels = []

        # 现有关系索引
        rel_index: dict[str, dict] = {}
        for r in rels:
            if isinstance(r, dict):
                target = r.get("target", "")
                rel_index[target] = r

        updated = False
        for fact in relation_facts:
            obj = fact.get("object", "")
            target_name = authority.resolve(obj, keep_unknown=True)
            if not target_name or target_name == normalize_name(character.name):
                continue

            detail = fact.get("detail", "") or fact.get("predicate", "")

            # 计算亲密度调整
            intimacy_delta = 0
            for keyword, delta in INTIMACY_ADJUSTMENTS.items():
                if keyword in detail:
                    intimacy_delta = delta
                    break

            if target_name in rel_index:
                # 更新已有关系
                existing = rel_index[target_name]
                existing["description"] = detail
                existing["last_chapter"] = chapter_number
                old_intimacy = existing.get("intimacy", 50)
                new_intimacy = max(0, min(100, old_intimacy + intimacy_delta))
                existing["intimacy"] = new_intimacy
                updated = True
            else:
                # 创建新关系
                new_rel = {
                    "target": target_name,
                    "description": detail,
                    "intimacy": max(0, min(100, 50 + intimacy_delta)),
                    "first_chapter": chapter_number,
                    "last_chapter": chapter_number,
                    "status": "active",
                }
                rels.append(new_rel)
                updated = True

        if updated:
            character.relationships = json.dumps(rels, ensure_ascii=False)
            result["relations_updated"] += 1
            result["changes"].append(f"{character.name}: 关系更新 ({len(relation_facts)}条事实)")
