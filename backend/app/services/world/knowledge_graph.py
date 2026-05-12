"""知识图谱三元组服务 — 自动提取 + CRUD + 查询

从 Observer 提取的 facts 中生成三元组，写入 knowledge_triples 表。
支持按实体名查询一度关系、按谓词查询、章节范围查询。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.novel import KnowledgeTriple

logger = logging.getLogger(__name__)


class KnowledgeGraphService:
    """知识图谱三元组服务"""

    def __init__(self, db: Session):
        self.db = db

    # ==================== CRUD ====================

    def create_triple(
        self,
        novel_id: str,
        subject_id: str,
        predicate: str,
        object_id: str,
        subject_type: str = "character",
        object_type: str = "character",
        description: str = "",
        confidence: float = 1.0,
        source_type: str = "manual",
        source_chapter: Optional[int] = None,
    ) -> KnowledgeTriple:
        """创建三元组"""
        triple = KnowledgeTriple(
            novel_id=novel_id,
            subject_id=subject_id,
            subject_type=subject_type,
            predicate=predicate,
            object_id=object_id,
            object_type=object_type,
            description=description,
            confidence=confidence,
            source_type=source_type,
            source_chapter=source_chapter,
            first_appearance=source_chapter,
            related_chapters=str(source_chapter) if source_chapter else "",
        )
        self.db.add(triple)
        self.db.flush()
        return triple

    def upsert_triple(
        self,
        novel_id: str,
        subject_id: str,
        predicate: str,
        object_id: str,
        chapter_number: Optional[int] = None,
        **kwargs,
    ) -> KnowledgeTriple:
        """创建或更新三元组（去重：subject+predicate+object 唯一）"""
        existing = (
            self.db.query(KnowledgeTriple)
            .filter_by(
                novel_id=novel_id,
                subject_id=subject_id,
                predicate=predicate,
                object_id=object_id,
            )
            .first()
        )
        if existing:
            # 更新相关章节
            if chapter_number:
                chapters = set(
                    int(x) for x in (existing.related_chapters or "").split(",")
                    if x.strip().isdigit()
                )
                chapters.add(chapter_number)
                existing.related_chapters = ",".join(str(c) for c in sorted(chapters))
            for key, val in kwargs.items():
                if hasattr(existing, key) and val is not None:
                    setattr(existing, key, val)
            return existing
        else:
            return self.create_triple(
                novel_id=novel_id,
                subject_id=subject_id,
                predicate=predicate,
                object_id=object_id,
                source_chapter=chapter_number,
                **kwargs,
            )

    def get_by_novel(self, novel_id: str, active_only: bool = True) -> List[KnowledgeTriple]:
        """获取小说的所有三元组"""
        q = self.db.query(KnowledgeTriple).filter_by(novel_id=novel_id)
        if active_only:
            q = q.filter_by(is_active=True)
        return q.order_by(KnowledgeTriple.created_at).all()

    def get_by_entity(self, novel_id: str, entity_name: str) -> List[KnowledgeTriple]:
        """获取与实体相关的所有三元组（一度关系）"""
        return (
            self.db.query(KnowledgeTriple)
            .filter(
                KnowledgeTriple.novel_id == novel_id,
                KnowledgeTriple.is_active.is_(True),
                or_(
                    KnowledgeTriple.subject_id == entity_name,
                    KnowledgeTriple.object_id == entity_name,
                ),
            )
            .all()
        )

    def search_by_predicate(
        self, novel_id: str, predicates: List[str], limit: int = 20,
    ) -> List[KnowledgeTriple]:
        """按谓词搜索三元组"""
        return (
            self.db.query(KnowledgeTriple)
            .filter(
                KnowledgeTriple.novel_id == novel_id,
                KnowledgeTriple.is_active.is_(True),
                KnowledgeTriple.predicate.in_(predicates),
            )
            .limit(limit)
            .all()
        )

    def get_recent(
        self, novel_id: str, chapter_number: int, chapter_range: int = 5, limit: int = 20,
    ) -> List[KnowledgeTriple]:
        """获取最近章节相关三元组"""
        min_ch = max(1, chapter_number - chapter_range)
        return (
            self.db.query(KnowledgeTriple)
            .filter(
                KnowledgeTriple.novel_id == novel_id,
                KnowledgeTriple.is_active.is_(True),
                KnowledgeTriple.source_chapter.isnot(None),
                KnowledgeTriple.source_chapter >= min_ch,
                KnowledgeTriple.source_chapter <= chapter_number,
            )
            .order_by(KnowledgeTriple.source_chapter.desc())
            .limit(limit)
            .all()
        )

    def delete_triple(self, triple_id: str) -> bool:
        """软删除三元组"""
        triple = self.db.query(KnowledgeTriple).filter_by(id=triple_id).first()
        if triple:
            triple.is_active = False
            return True
        return False

    def hard_delete(self, triple_id: str) -> bool:
        """硬删除三元组"""
        n = self.db.query(KnowledgeTriple).filter_by(id=triple_id).delete()
        return n > 0

    # ==================== 自动提取 ====================

    def extract_from_observer_facts(
        self,
        novel_id: str,
        chapter_number: int,
        facts: Dict[str, list],
    ) -> int:
        """从 Observer 提取的 facts 中生成三元组

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            facts: Observer 输出的结构化事实 dict
                {
                    "relations": [{"subject": ..., "object": ..., "type": ...}, ...],
                    "characters": [{"name": ..., "trait": ...}, ...],
                    "locations": [{"name": ..., "description": ...}, ...],
                    "resources": [{"name": ..., "owner": ..., "description": ...}, ...],
                    ...
                }

        Returns:
            新增/更新的三元组数量
        """
        count = 0

        # 1. relations → 角色关系三元组
        for rel in facts.get("relations", []):
            if not isinstance(rel, dict):
                continue
            subj = rel.get("subject", "").strip()
            obj = rel.get("object", "").strip()
            rel_type = rel.get("type", "关系").strip()
            if subj and obj and subj != obj:
                self.upsert_triple(
                    novel_id=novel_id,
                    subject_id=subj,
                    predicate=rel_type,
                    object_id=obj,
                    subject_type="character",
                    object_type="character",
                    source_type="auto",
                    confidence=0.9,
                    chapter_number=chapter_number,
                )
                count += 1

        # 2. characters + locations → 角色-地点关系
        char_names = [c.get("name", "") for c in facts.get("characters", []) if isinstance(c, dict)]
        for loc in facts.get("locations", []):
            if not isinstance(loc, dict):
                continue
            loc_name = loc.get("name", "").strip()
            if not loc_name:
                continue
            # 角色出现在此地点
            for name in char_names:
                if name:
                    self.upsert_triple(
                        novel_id=novel_id,
                        subject_id=name,
                        predicate="出现在",
                        object_id=loc_name,
                        subject_type="character",
                        object_type="location",
                        source_type="auto",
                        confidence=0.7,
                        chapter_number=chapter_number,
                    )
                    count += 1

        # 3. resources → 物品-角色关系
        for res in facts.get("resources", []):
            if not isinstance(res, dict):
                continue
            res_name = res.get("name", "").strip()
            owner = res.get("owner", "").strip()
            if res_name and owner:
                self.upsert_triple(
                    novel_id=novel_id,
                    subject_id=owner,
                    predicate="拥有",
                    object_id=res_name,
                    subject_type="character",
                    object_type="item",
                    source_type="auto",
                    description=res.get("description", ""),
                    confidence=0.8,
                    chapter_number=chapter_number,
                )
                count += 1

        # 4. emotions → 角色情感状态
        for emo in facts.get("emotions", []):
            if not isinstance(emo, dict):
                continue
            char = emo.get("character", "").strip()
            emotion = emo.get("emotion", "").strip()
            if char and emotion:
                self.upsert_triple(
                    novel_id=novel_id,
                    subject_id=char,
                    predicate="情感状态",
                    object_id=emotion,
                    subject_type="character",
                    object_type="concept",
                    source_type="auto",
                    confidence=0.6,
                    chapter_number=chapter_number,
                )
                count += 1

        logger.info(
            "[KnowledgeGraph] 从第%d章提取 %d 条三元组",
            chapter_number, count,
        )
        return count

    # ==================== 格式化输出 ====================

    def format_subnetwork(
        self, novel_id: str, entity_names: List[str], chapter_number: int,
    ) -> str:
        """格式化图谱子网为可读文本（供 ContextBudgetAllocator T1 槽位使用）"""
        all_triples = {}
        for name in entity_names:
            for t in self.get_by_entity(novel_id, name):
                all_triples[t.id] = t

        # 补充最近章节三元组
        for t in self.get_recent(novel_id, chapter_number, limit=10):
            all_triples[t.id] = t

        if not all_triples:
            return ""

        # 按类型分组
        char_rels = []
        char_states = []
        loc_info = []
        item_info = []
        other = []

        for t in sorted(all_triples.values(), key=lambda x: -x.confidence):
            line = f"- {t.subject_id} —{t.predicate}→ {t.object_id}"
            if t.description:
                line += f" | {t.description[:50]}"

            if t.subject_type == "character" and t.object_type == "character":
                char_rels.append(line)
            elif t.object_type == "location":
                loc_info.append(line)
            elif t.object_type == "item":
                item_info.append(line)
            elif t.predicate in ("状态", "情感状态", "心理"):
                char_states.append(line)
            else:
                other.append(line)

        parts = ["【图谱子网】"]
        if char_rels:
            parts.append("\n[人物关系]")
            parts.extend(char_rels[:10])
        if char_states:
            parts.append("\n[人物状态]")
            parts.extend(char_states[:5])
        if loc_info:
            parts.append("\n[地点信息]")
            parts.extend(loc_info[:5])
        if item_info:
            parts.append("\n[道具/装备]")
            parts.extend(item_info[:5])
        if other:
            parts.append("\n[其他设定]")
            parts.extend(other[:5])

        return "\n".join(parts)

    def get_stats(self, novel_id: str) -> dict:
        """获取知识图谱统计"""
        total = self.db.query(KnowledgeTriple).filter_by(novel_id=novel_id, is_active=True).count()
        by_type = {}
        for row in (
            self.db.query(KnowledgeTriple.subject_type, KnowledgeTriple.object_type)
            .filter_by(novel_id=novel_id, is_active=True)
            .all()
        ):
            key = f"{row[0]}→{row[1]}"
            by_type[key] = by_type.get(key, 0) + 1

        return {"total": total, "by_type": by_type}
