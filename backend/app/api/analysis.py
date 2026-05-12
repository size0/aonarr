"""拆书分析 API 路由"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.db.connection import get_db, SessionLocal
from app.models.analysis import AnalysisJob, AnalysisChapterResult

router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = logging.getLogger(__name__)


# ── 任务列表 / 详情 ──────────────────────────────────────────────

@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(AnalysisJob).order_by(AnalysisJob.created_at.desc()).all()
    return [_job_dto(j) for j in jobs]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(AnalysisJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, "分析任务不存在")
    return _job_dto(job)


@router.get("/jobs/{job_id}/chapters")
def get_job_chapters(job_id: str, db: Session = Depends(get_db)):
    """获取某任务的逐章分析结果"""
    job = db.query(AnalysisJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, "分析任务不存在")
    rows = (
        db.query(AnalysisChapterResult)
        .filter_by(job_id=job_id)
        .order_by(AnalysisChapterResult.chapter_number)
        .all()
    )
    return [_chapter_dto(r) for r in rows]


# ── 上传 + 触发 ──────────────────────────────────────────────────

@router.post("/upload", status_code=201)
async def upload_and_analyze(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """上传文件并创建拆书分析任务"""
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = os.path.splitext(file.filename or "")[1] or ".txt"
    saved_name = f"{uuid.uuid4()}{ext}"
    saved_path = upload_dir / saved_name

    content = await file.read()
    with open(saved_path, "wb") as f:
        f.write(content)

    job = AnalysisJob(
        id=str(uuid.uuid4()),
        novel_title=os.path.splitext(file.filename or "未命名")[0],
        source_file=str(saved_path),
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 触发异步分析任务
    background_tasks.add_task(_run_analysis_pipeline, job.id)

    return _job_dto(job)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(AnalysisJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, "分析任务不存在")
    # 删除关联章节结果
    db.query(AnalysisChapterResult).filter_by(job_id=job_id).delete()
    db.delete(job)
    db.commit()


# ── 异步分析管线 ──────────────────────────────────────────────────

def _run_analysis_pipeline(job_id: str) -> None:
    """在后台线程中执行完整分析管线"""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_pipeline(job_id))
    finally:
        loop.close()


async def _async_pipeline(job_id: str) -> None:
    """完整的八步分析管线（含 LLM 深度步骤 + 向量化）

    步骤:
    1. 文件导入
    2. 章节切分
    3. jieba 实体预扫描
    3.5 LLM 实体确认补充（容错）
    4. 逐章 LLM 深度提取
    5. 纯算法全局聚合
    5.5 LLM 深度全局分析（容错）
    6. 纯统计文风指纹
    6.5 LLM 文风深度分析（容错）
    7. 拆书结果写入向量库（容错）
    """
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter_by(id=job_id).first()
        if not job:
            logger.error("分析任务不存在: %s", job_id)
            return

        warnings: list[str] = []

        try:
            # Step 1: 导入文件
            _update_job(db, job, status="scanning", progress=0.05)
            from app.services.analysis.importer import import_file
            imp = import_file(job.source_file)

            # Step 2: 章节切分
            _update_job(db, job, status="scanning", progress=0.10)
            from app.services.analysis.chapter_splitter import split_chapters
            split = split_chapters(imp.text)
            job.chapter_count = split.chapter_count
            db.commit()

            if split.chapter_count == 0:
                _update_job(db, job, status="failed", error_message="未能切分出任何章节")
                return

            # Step 3: jieba 实体扫描
            _update_job(db, job, status="scanning", progress=0.12)
            from app.services.analysis.entity_scanner import scan_entities, confirm_entities_with_llm
            scan = scan_entities(imp.text)

            # Step 3.5: LLM 实体确认（容错 — 失败则继续用 jieba 结果）
            try:
                _update_job(db, job, status="scanning", progress=0.15)
                llm_scan = _get_llm(db, "book_analysis_extract")
                scan = await confirm_entities_with_llm(scan, imp.text, llm_scan)
            except Exception as e:
                logger.warning("LLM 实体确认跳过: %s", e)
                warnings.append(f"LLM实体确认跳过: {e}")

            known_names = scan.get_entity_names("person")

            # Step 4: 逐章 LLM 提取
            _update_job(db, job, status="extracting", progress=0.20)
            from app.services.analysis.chapter_extractor import extract_all_chapters

            llm = _get_llm(db, "book_analysis_extract")
            chapter_dicts = [
                {"number": ch.number, "title": ch.title, "text": ch.text}
                for ch in split.chapters
            ]

            def _progress_cb(done: int, total: int):
                pct = 0.20 + 0.45 * (done / total)
                _update_job(db, job, progress=pct)

            analyses = await extract_all_chapters(
                llm=llm,
                chapters=chapter_dicts,
                novel_title=job.novel_title,
                known_entities=known_names,
                concurrency=3,
                progress_callback=_progress_cb,
            )

            # 保存逐章结果到数据库
            for a in analyses:
                row = AnalysisChapterResult(
                    job_id=job_id,
                    chapter_number=a.chapter_number,
                    chapter_title=a.chapter_title,
                    characters=json.dumps(a.characters, ensure_ascii=False),
                    events=json.dumps(a.events, ensure_ascii=False),
                    relationships=json.dumps(a.relationships, ensure_ascii=False),
                    foreshadows=json.dumps(a.foreshadows, ensure_ascii=False),
                    summary=a.summary,
                    word_count=a.word_count,
                )
                db.add(row)
            db.commit()

            # Step 5: 纯算法全局聚合
            _update_job(db, job, status="aggregating", progress=0.70)
            from app.services.analysis.aggregator import aggregate, deep_aggregate
            chapter_dicts_for_agg = [a.to_dict() for a in analyses]
            agg = aggregate(chapter_dicts_for_agg)
            agg_dict = agg.to_dict()

            # Step 5.5: LLM 深度全局分析（容错）
            deep_analysis = {}
            try:
                _update_job(db, job, status="aggregating", progress=0.78)
                llm_deep = _get_llm(db, "book_analysis_deep")
                deep_analysis = await deep_aggregate(
                    llm=llm_deep,
                    chapter_analyses=chapter_dicts_for_agg,
                    novel_title=job.novel_title,
                )
                # 合并 LLM 深度分析结果到聚合数据
                if deep_analysis.get("global_summary"):
                    agg_dict["global_summary"] = deep_analysis["global_summary"]
                if deep_analysis.get("theme_keywords"):
                    agg_dict["theme_keywords"] = deep_analysis["theme_keywords"]
                if deep_analysis.get("character_arcs"):
                    # 回填角色弧线到 profiles
                    arc_map = {a["name"]: a.get("arc_summary", "") for a in deep_analysis["character_arcs"]}
                    for prof in agg_dict.get("character_profiles", []):
                        if prof["name"] in arc_map:
                            prof["arc_summary"] = arc_map[prof["name"]]
                if deep_analysis.get("plot_structure"):
                    agg_dict["plot_structure"] = deep_analysis["plot_structure"]
            except Exception as e:
                logger.warning("LLM 深度聚合跳过: %s", e)
                warnings.append(f"LLM深度聚合跳过: {e}")

            # Step 6: 纯统计文风指纹
            _update_job(db, job, status="aggregating", progress=0.85)
            from app.services.analysis.style_fingerprint import analyze_style, analyze_style_with_llm
            style = analyze_style(imp.text)

            # Step 6.5: LLM 文风深度分析（容错）
            try:
                _update_job(db, job, status="aggregating", progress=0.90)
                llm_style = _get_llm(db, "style_detection")
                style = await analyze_style_with_llm(imp.text, llm_style, style)
            except Exception as e:
                logger.warning("LLM 文风分析跳过: %s", e)
                warnings.append(f"LLM文风分析跳过: {e}")

            # Step 7: 拆书结果写入向量库（容错）
            try:
                _update_job(db, job, status="indexing", progress=0.95)
                _index_to_vector_store(job_id, split, analyses)
            except Exception as e:
                logger.warning("向量库索引跳过: %s", e)
                warnings.append(f"向量库索引跳过: {e}")

            # 汇总结果
            summary = {
                "aggregation": agg_dict,
                "style_fingerprint": style.to_dict(),
                "entity_scan": scan.to_dict(),
                "pattern_used": split.pattern_used,
            }
            if deep_analysis:
                summary["deep_analysis"] = deep_analysis
            if warnings:
                summary["warnings"] = warnings

            job.result_summary = json.dumps(summary, ensure_ascii=False)
            job.status = "done"
            job.progress = 1.0
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("分析任务完成: %s (%d 警告)", job_id, len(warnings))

        except Exception as e:
            logger.exception("分析管线失败: %s", e)
            _update_job(db, job, status="failed", error_message=str(e))

    finally:
        db.close()


def _index_to_vector_store(job_id: str, split, analyses) -> None:
    """将拆书章节内容写入 ChromaDB 向量库"""
    from app.services.creation.vector_store import NovelVectorStore

    # 使用 job_id 作为 novel_id（拆书场景无 novel_id）
    vs = NovelVectorStore(f"analysis_{job_id}")
    total = 0
    for ch in split.chapters:
        if ch.text.strip():
            count = vs.upsert_chapter(ch.number, ch.text)
            total += count
    logger.info("拆书向量化完成: job=%s, %d 段落入库", job_id, total)


def _update_job(
    db: Session,
    job: AnalysisJob,
    status: str | None = None,
    progress: float | None = None,
    error_message: str | None = None,
) -> None:
    if status is not None:
        job.status = status
    if progress is not None:
        job.progress = progress
    if error_message is not None:
        job.error_message = error_message
        job.finished_at = datetime.now(timezone.utc)
    db.commit()


def _get_llm(db: Session, stage: str):
    """获取指定阶段的 LLM 客户端"""
    from app.llm.resolver import StageModelResolver
    resolver = StageModelResolver(db)
    return resolver.get_llm_for_stage(stage)


# ── DTO ──────────────────────────────────────────────────────────

def _job_dto(j: AnalysisJob) -> dict:
    return {
        "id": j.id,
        "novel_title": j.novel_title,
        "source_file": j.source_file,
        "status": j.status,
        "progress": j.progress,
        "chapter_count": j.chapter_count,
        "result_summary": json.loads(j.result_summary) if j.result_summary else {},
        "error_message": j.error_message,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


def _chapter_dto(r: AnalysisChapterResult) -> dict:
    return {
        "id": r.id,
        "job_id": r.job_id,
        "chapter_number": r.chapter_number,
        "chapter_title": r.chapter_title,
        "characters": json.loads(r.characters) if r.characters else [],
        "events": json.loads(r.events) if r.events else [],
        "relationships": json.loads(r.relationships) if r.relationships else [],
        "foreshadows": json.loads(r.foreshadows) if r.foreshadows else [],
        "summary": r.summary,
        "word_count": r.word_count,
    }
