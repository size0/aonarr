"""自动修订循环 — 审计不通过时自动 修订→再审计（最多 3 轮）

流程：
1. audit(chapter) → QualityScore
2. if not passed → revision(chapter, issues) → revised_text
3. audit(revised) → if passed → save; else → repeat (max 3 rounds)
4. 关键问题自动修复，非关键标记给人工

修订策略按 issue severity 分级：
- critical: AI味过重 / 自然度极低 → 自动调 LLM 改写
- warning: 节奏/对话/词汇 → 自动微调
- info: 情感弧线平淡 → 标记给人工
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.models.novel import Chapter, AuditResult
from app.services.audit.quality_radar import score_chapter, QualityScore
from app.services.audit.anti_detect import post_process

logger = logging.getLogger(__name__)

MAX_REVISION_ROUNDS = 3


_REVISION_SYSTEM = """你是一位小说修改专家。根据审计报告指出的问题，修改文本。

修改规则：
1. 不改变情节、对话内容、人物行为
2. 仅针对审计指出的具体问题进行修改
3. 保持原文风格和语气
4. 修改幅度尽量小，精准修复

输出修改后的完整文本，不要解释修改内容。"""


class RevisionLoop:
    """审计→修订→再审计 自动循环"""

    def __init__(self, db: Session):
        self.db = db

    async def run(
        self,
        novel_id: str,
        chapter_number: int,
        *,
        max_rounds: int = MAX_REVISION_ROUNDS,
        auto_save: bool = True,
    ) -> dict:
        """执行审计-修订循环

        Returns:
            {
                "rounds": int,
                "initial_score": float,
                "final_score": float,
                "passed": bool,
                "issues_fixed": list,
                "issues_human": list,
                "audit_history": list[dict],
            }
        """
        chapter = (
            self.db.query(Chapter)
            .filter_by(novel_id=novel_id, number=chapter_number)
            .first()
        )
        if not chapter or not chapter.content:
            return {"error": "章节不存在或内容为空"}

        text = chapter.content
        audit_history = []
        issues_fixed = []
        issues_human = []
        initial_score = None

        for round_num in range(max_rounds + 1):
            # Step 1: 审计
            qs = score_chapter(text)

            # 保存审计结果到 DB
            self._save_audit_result(novel_id, chapter_number, qs, round_num)

            audit_entry = {
                "round": round_num,
                "overall": round(qs.overall, 1),
                "passed": qs.pass_rate,
                "issues": qs.issues,
                "scores": qs.to_dict(),
            }
            audit_history.append(audit_entry)

            if initial_score is None:
                initial_score = qs.overall

            logger.info(
                "[RevisionLoop] novel=%s ch=%d round=%d overall=%.1f passed=%s issues=%d",
                novel_id, chapter_number, round_num,
                qs.overall, qs.pass_rate, len(qs.issues),
            )

            # Step 2: 通过 → 结束
            if qs.pass_rate:
                break

            # 最后一轮不再修订
            if round_num >= max_rounds:
                # 标记剩余问题给人工
                for issue in qs.issues:
                    issues_human.append(issue)
                break

            # Step 3: 分级修订
            critical_issues = [i for i in qs.issues if i.get("severity") == "critical"]
            warning_issues = [i for i in qs.issues if i.get("severity") == "warning"]
            info_issues = [i for i in qs.issues if i.get("severity") == "info"]

            # info 级别标记给人工
            issues_human.extend(info_issues)

            # critical + warning 自动修复
            fixable = critical_issues + warning_issues
            if not fixable:
                break

            text = await self._revise(text, fixable, novel_id, chapter_number)
            issues_fixed.extend([i.get("message", "") for i in fixable])

        # 保存最终文本
        if auto_save and text != chapter.content:
            chapter.content = text
            chapter.word_count = len(text)
            chapter.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.info("[RevisionLoop] 已保存修订结果: novel=%s ch=%d", novel_id, chapter_number)

        final_qs = score_chapter(text)

        return {
            "rounds": len(audit_history) - 1,
            "initial_score": round(initial_score or 0, 1),
            "final_score": round(final_qs.overall, 1),
            "passed": final_qs.pass_rate,
            "issues_fixed": issues_fixed,
            "issues_human": issues_human,
            "audit_history": audit_history,
        }

    async def _revise(
        self,
        text: str,
        issues: list[dict],
        novel_id: str,
        chapter_number: int,
    ) -> str:
        """根据审计问题修订文本"""
        # Step 1: 基础后处理（疲劳词替换）
        has_ai_issue = any(
            i.get("dimension") == "ai_detect" for i in issues
        )
        if has_ai_issue:
            text, _ = post_process(text)

        # Step 2: LLM 修订（针对非AI味问题）
        non_ai_issues = [i for i in issues if i.get("dimension") != "ai_detect"]
        if non_ai_issues:
            text = await self._llm_revise(text, non_ai_issues)

        return text

    async def _llm_revise(self, text: str, issues: list[dict]) -> str:
        """LLM 驱动的精准修订"""
        try:
            resolver = StageModelResolver(self.db)
            llm = resolver.get_llm_for_stage("audit_review")
        except Exception as e:
            logger.warning("审核LLM未配置，跳过LLM修订: %s", e)
            return text

        issues_desc = "\n".join(
            f"- [{i.get('severity', '?')}] {i.get('message', '')}"
            for i in issues[:5]
        )

        # 优先从 DB 加载审核修订提示词
        from app.services.prompt_loader import PromptLoader
        db_prompt = PromptLoader(self.db).get_prompt("audit_review")
        system = db_prompt if db_prompt else _REVISION_SYSTEM

        config = GenerationConfig(
            system=system,
            temperature=0.5,
            max_tokens=8192,
        )

        prompt = f"""以下是审计报告指出的问题：
{issues_desc}

请针对以上问题修改以下文本：

---原文---
{text[:6000]}
---原文结束---

请输出修改后的完整文本。"""

        try:
            result = await llm.generate(prompt, config)
            revised = result.content.strip()

            # 验证改写长度合理
            if len(revised) < len(text) * 0.5:
                logger.warning("LLM修订结果过短 (%d vs %d)，跳过", len(revised), len(text))
                return text

            return revised
        except Exception as e:
            logger.error("LLM修订失败: %s", e)
            return text

    def _save_audit_result(
        self,
        novel_id: str,
        chapter_number: int,
        qs: QualityScore,
        round_num: int,
    ) -> None:
        """保存审计结果到 DB"""
        try:
            ar = AuditResult(
                id=str(uuid.uuid4()),
                novel_id=novel_id,
                chapter_number=chapter_number,
                audit_type="full",
                scores_json=json.dumps(qs.to_dict(), ensure_ascii=False),
                issues_json=json.dumps(qs.issues, ensure_ascii=False),
                overall_score=qs.overall,
                passed=qs.pass_rate,
                revision_round=round_num,
            )
            self.db.add(ar)
            self.db.flush()
        except Exception as e:
            logger.warning("保存审计结果失败: %s", e)
