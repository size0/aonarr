"""审核引擎 API 路由"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.llm.resolver import StageModelResolver
from app.models.novel import Novel, Chapter

router = APIRouter(prefix="/audit", tags=["audit"])
logger = logging.getLogger(__name__)


def _get_novel_or_404(novel_id: str, db: Session) -> Novel:
    novel = db.query(Novel).filter_by(id=novel_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    return novel


def _get_chapter_or_404(novel_id: str, number: int, db: Session) -> Chapter:
    chapter = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id, number=number)
        .first()
    )
    if not chapter:
        raise HTTPException(404, f"第{number}章不存在")
    return chapter


# ── 质量雷达 ────────────────────────────────────────────────────

@router.post("/{novel_id}/chapters/{number}/quality")
def quality_radar(novel_id: str, number: int, db: Session = Depends(get_db)):
    """本地启发式章节质量评分 (六维雷达)"""
    _get_novel_or_404(novel_id, db)
    chapter = _get_chapter_or_404(novel_id, number, db)

    if not chapter.content:
        raise HTTPException(400, "章节内容为空")

    from app.services.audit.quality_radar import score_chapter
    qs = score_chapter(chapter.content)

    return {
        "novel_id": novel_id,
        "chapter_number": number,
        "chapter_title": chapter.title,
        "word_count": chapter.word_count,
        "scores": qs.to_dict(),
    }


# ── 一致性校验 ──────────────────────────────────────────────────

@router.post("/{novel_id}/consistency")
async def consistency_check(novel_id: str, db: Session = Depends(get_db)):
    """全书一致性校验 (人物+时间线, 需 LLM)"""
    _get_novel_or_404(novel_id, db)

    try:
        resolver = StageModelResolver(db)
        llm = resolver.get_llm_for_stage("audit_review")
    except Exception as e:
        raise HTTPException(503, f"审核 LLM 未配置: {e}")

    from app.services.audit.consistency_checker import check_full_consistency
    report = await check_full_consistency(db, llm, novel_id)
    return report.to_dict()


# ── 文风漂移检测 ────────────────────────────────────────────────

@router.post("/{novel_id}/chapters/{number}/style-drift")
def style_drift(novel_id: str, number: int, db: Session = Depends(get_db)):
    """检测单章相对全书的文风漂移"""
    _get_novel_or_404(novel_id, db)
    chapter = _get_chapter_or_404(novel_id, number, db)

    if not chapter.content:
        raise HTTPException(400, "章节内容为空")

    # 收集全书文本作为基准
    all_chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .order_by(Chapter.number)
        .all()
    )
    full_text = "\n".join(ch.content for ch in all_chapters if ch.content)

    if len(full_text) < 200:
        raise HTTPException(400, "全书内容过少, 无法建立文风基准")

    from app.services.audit.style_drift_detector import detect_drift
    report = detect_drift(
        chapter_text=chapter.content,
        baseline_text=full_text,
        chapter_number=number,
    )
    return {
        "novel_id": novel_id,
        **report.to_dict(),
    }


# ── 批量文风漂移 ────────────────────────────────────────────────

@router.post("/{novel_id}/style-drift-all")
def style_drift_all(novel_id: str, db: Session = Depends(get_db)):
    """检测全部章节的文风漂移"""
    _get_novel_or_404(novel_id, db)

    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .order_by(Chapter.number)
        .all()
    )
    if len(chapters) < 2:
        raise HTTPException(400, "至少需要2个章节才能检测漂移")

    chapter_texts = [ch.content or "" for ch in chapters]
    full_text = "\n".join(chapter_texts)

    from app.services.audit.style_drift_detector import detect_drift_multi
    reports = detect_drift_multi(chapter_texts, full_text)

    return {
        "novel_id": novel_id,
        "chapter_count": len(chapters),
        "reports": [r.to_dict() for r in reports],
        "severe_count": sum(1 for r in reports if r.drift_level == "severe"),
        "moderate_count": sum(1 for r in reports if r.drift_level == "moderate"),
    }


# ── 去AI味 ────────────────────────────────────────────────────────

@router.post("/{novel_id}/chapters/{number}/anti-detect")
async def anti_detect(novel_id: str, number: int, db: Session = Depends(get_db)):
    """去AI味处理（后处理 + LLM改写）"""
    _get_novel_or_404(novel_id, db)
    chapter = _get_chapter_or_404(novel_id, number, db)

    if not chapter.content:
        raise HTTPException(400, "章节内容为空")

    from app.services.audit.anti_detect import full_anti_detect
    result = await full_anti_detect(db, chapter.content, genre=chapter.novel.genre if chapter.novel else "")

    # 如果改善了，保存
    if result.get("improved") and result.get("text"):
        chapter.content = result["text"]
        chapter.word_count = len(result["text"])
        db.commit()

    return {
        "novel_id": novel_id,
        "chapter_number": number,
        **{k: v for k, v in result.items() if k != "text"},
        "word_count": len(result.get("text", "")),
    }


# ── 自动修订循环 ──────────────────────────────────────────────────

@router.post("/{novel_id}/chapters/{number}/revision-loop")
async def revision_loop(novel_id: str, number: int, db: Session = Depends(get_db)):
    """审计→修订→再审计 自动循环（最多3轮）"""
    _get_novel_or_404(novel_id, db)
    chapter = _get_chapter_or_404(novel_id, number, db)

    if not chapter.content:
        raise HTTPException(400, "章节内容为空")

    from app.services.audit.revision_loop import RevisionLoop
    loop = RevisionLoop(db)
    result = await loop.run(novel_id, number)
    return {
        "novel_id": novel_id,
        "chapter_number": number,
        **result,
    }


# ── 审计历史 ──────────────────────────────────────────────────────

@router.get("/{novel_id}/chapters/{number}/audit-history")
def audit_history(novel_id: str, number: int, db: Session = Depends(get_db)):
    """获取章节审计历史"""
    from app.models.novel import AuditResult

    results = (
        db.query(AuditResult)
        .filter_by(novel_id=novel_id, chapter_number=number)
        .order_by(AuditResult.created_at.desc())
        .limit(20)
        .all()
    )

    import json
    return {
        "novel_id": novel_id,
        "chapter_number": number,
        "history": [
            {
                "id": r.id,
                "audit_type": r.audit_type,
                "overall_score": round(r.overall_score, 1),
                "passed": bool(r.passed),
                "revision_round": r.revision_round,
                "scores": json.loads(r.scores_json) if r.scores_json else {},
                "issues": json.loads(r.issues_json) if r.issues_json else [],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ],
    }


# ── 张力心电图 ────────────────────────────────────────────────────

@router.get("/{novel_id}/tension-ecg")
def tension_ecg(novel_id: str, db: Session = Depends(get_db)):
    """生成全书张力心电图（章节维度张力曲线 + 节奏评价）"""
    _get_novel_or_404(novel_id, db)

    from app.services.audit.tension_ecg import generate_tension_ecg
    ecg = generate_tension_ecg(db, novel_id)
    return ecg.to_dict()


# ── 张力分数批量重校准 ──────────────────────────────────────────

@router.post("/{novel_id}/tension-recalibrate")
def tension_recalibrate(novel_id: str, db: Session = Depends(get_db)):
    """用启发式校准重算所有章节的 tension_score（不调 LLM）"""
    _get_novel_or_404(novel_id, db)

    import json as json_mod
    from app.services.creation.post_pipeline import PostPipeline

    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .order_by(Chapter.number)
        .all()
    )

    from app.services.audit.quality_radar import score_chapter

    results = []
    for ch in chapters:
        if not ch.content:
            continue
        old_score = ch.tension_score or 0.0

        # 如果 tension_score 为 0，先用 quality_radar 算一个基准分
        if old_score == 0.0:
            qs = score_chapter(ch.content)
            old_score = round(qs.reading_power / 10.0, 1)

        events = []
        try:
            events = json_mod.loads(ch.events) if ch.events else []
        except (json_mod.JSONDecodeError, TypeError):
            pass
        new_score = PostPipeline._calibrate_tension(old_score, ch.content, events)
        ch.tension_score = new_score
        results.append({
            "chapter": ch.number,
            "old": round(old_score, 1),
            "new": round(new_score, 1),
        })

    db.commit()
    return {
        "novel_id": novel_id,
        "recalibrated": len(results),
        "details": results,
    }


# ── 综合审计（一键） ──────────────────────────────────────────────

@router.post("/{novel_id}/chapters/{number}/full-audit")
async def full_audit(novel_id: str, number: int, db: Session = Depends(get_db)):
    """综合审计: 质量雷达 + 去AI味评分 + 问题列表"""
    _get_novel_or_404(novel_id, db)
    chapter = _get_chapter_or_404(novel_id, number, db)

    if not chapter.content:
        raise HTTPException(400, "章节内容为空")

    from app.services.audit.quality_radar import score_chapter
    qs = score_chapter(chapter.content)

    # 保存审计结果
    import json as json_mod
    from app.models.novel import AuditResult
    import uuid

    ar = AuditResult(
        id=str(uuid.uuid4()),
        novel_id=novel_id,
        chapter_number=number,
        audit_type="full",
        scores_json=json_mod.dumps(qs.to_dict(), ensure_ascii=False),
        issues_json=json_mod.dumps(qs.issues, ensure_ascii=False),
        overall_score=qs.overall,
        passed=qs.pass_rate,
        revision_round=0,
    )
    db.add(ar)
    db.commit()

    return {
        "novel_id": novel_id,
        "chapter_number": number,
        "chapter_title": chapter.title,
        "word_count": chapter.word_count,
        "scores": qs.to_dict(),
        "audit_id": ar.id,
    }


# ═══════════════════════════════════════════════════════════════════
# PlotAnalysis — 结构化剧情分析
# ═══════════════════════════════════════════════════════════════════

@router.post("/{novel_id}/chapters/{number}/plot-analysis")
async def run_plot_analysis(
    novel_id: str, number: int, force: bool = False, db: Session = Depends(get_db)
):
    """对单章执行结构化剧情分析（LLM 驱动）"""
    _get_novel_or_404(novel_id, db)
    _get_chapter_or_404(novel_id, number, db)

    from app.services.audit.plot_analyzer import PlotAnalyzer
    analyzer = PlotAnalyzer(db)
    analysis = await analyzer.analyze(novel_id, number, force=force)

    return _plot_analysis_to_dict(analysis)


@router.get("/{novel_id}/chapters/{number}/plot-analysis")
async def get_plot_analysis(
    novel_id: str, number: int, db: Session = Depends(get_db)
):
    """获取已有的单章剧情分析"""
    _get_novel_or_404(novel_id, db)
    from app.services.audit.plot_analyzer import PlotAnalyzer
    analyzer = PlotAnalyzer(db)
    analysis = analyzer.get_analysis(novel_id, number)
    if not analysis:
        raise HTTPException(404, "该章节尚无剧情分析，请先执行 POST 分析")
    return _plot_analysis_to_dict(analysis)


@router.get("/{novel_id}/plot-analysis")
async def get_all_plot_analyses(novel_id: str, db: Session = Depends(get_db)):
    """获取全书剧情分析"""
    _get_novel_or_404(novel_id, db)
    from app.services.audit.plot_analyzer import PlotAnalyzer
    analyzer = PlotAnalyzer(db)
    analyses = analyzer.get_all_analyses(novel_id)
    return {
        "novel_id": novel_id,
        "count": len(analyses),
        "analyses": [_plot_analysis_to_dict(a) for a in analyses],
    }


@router.post("/{novel_id}/plot-analysis/all")
async def run_all_plot_analyses(
    novel_id: str, force: bool = False, db: Session = Depends(get_db)
):
    """对全书执行剧情分析"""
    _get_novel_or_404(novel_id, db)
    from app.services.audit.plot_analyzer import PlotAnalyzer
    analyzer = PlotAnalyzer(db)
    analyses = await analyzer.analyze_all(novel_id, force=force)
    return {
        "novel_id": novel_id,
        "analyzed": len(analyses),
        "analyses": [_plot_analysis_to_dict(a) for a in analyses],
    }


def _plot_analysis_to_dict(a) -> dict:
    """PlotAnalysis → API 响应 dict"""
    import json as json_mod
    return {
        "id": a.id,
        "novel_id": a.novel_id,
        "chapter_number": a.chapter_number,
        "plot_stage": a.plot_stage,
        "conflict_level": a.conflict_level,
        "conflict_types": json_mod.loads(a.conflict_types or "[]"),
        "emotional_tone": a.emotional_tone,
        "emotional_intensity": a.emotional_intensity,
        "emotional_curve": json_mod.loads(a.emotional_curve or "{}"),
        "hooks": json_mod.loads(a.hooks or "[]"),
        "hooks_count": a.hooks_count,
        "foreshadows_planted": a.foreshadows_planted,
        "foreshadows_resolved": a.foreshadows_resolved,
        "character_states": json_mod.loads(a.character_states or "[]"),
        "pacing": a.pacing,
        "scores": {
            "overall": a.overall_score,
            "pacing": a.pacing_score,
            "engagement": a.engagement_score,
            "coherence": a.coherence_score,
        },
        "suggestions": json_mod.loads(a.suggestions or "[]"),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ── 伏笔面板 ──────────────────────────────────────────────────────

@router.get("/{novel_id}/foreshadows")
def list_foreshadows(novel_id: str, db: Session = Depends(get_db)):
    """汇总全书活跃伏笔（从各章 Chapter.foreshadows JSON 聚合）"""
    import json as json_mod
    _get_novel_or_404(novel_id, db)
    chapters = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id)
        .filter(Chapter.foreshadows != "[]", Chapter.foreshadows != "")
        .order_by(Chapter.number)
        .all()
    )
    all_foreshadows: list[dict] = []
    resolved_keys: set[str] = set()

    for ch in chapters:
        try:
            items = json_mod.loads(ch.foreshadows) if ch.foreshadows else []
        except (json_mod.JSONDecodeError, TypeError):
            continue
        for item in items:
            if isinstance(item, dict):
                item.setdefault("chapter", ch.number)
                item.setdefault("chapter_title", ch.title or f"第{ch.number}章")
                # 追踪已回收的伏笔
                if item.get("status") == "resolved" or item.get("resolved"):
                    key = item.get("description", item.get("content", ""))
                    resolved_keys.add(key)
                all_foreshadows.append(item)

    # 标记活跃/已回收状态
    active = []
    resolved = []
    for f in all_foreshadows:
        desc = f.get("description", f.get("content", ""))
        if desc in resolved_keys or f.get("status") == "resolved" or f.get("resolved"):
            f["status"] = "resolved"
            resolved.append(f)
        else:
            f["status"] = "active"
            active.append(f)

    return {
        "novel_id": novel_id,
        "active": active,
        "resolved": resolved,
        "total": len(all_foreshadows),
        "active_count": len(active),
        "resolved_count": len(resolved),
    }
