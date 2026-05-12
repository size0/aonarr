"""全托管写作 — 自动循环：大纲节拍 → 写章节 → 章后管线

支持暂停/继续/停止控制。
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from app.services.creation.outline_generator import OutlineGenerator
from app.services.creation.chapter_writer import ChapterWriter
from app.services.creation.post_pipeline import PostPipeline
from app.services.creation.context_builder import ContextBuilder
from app.models.novel import AutopilotCheckpoint

logger = logging.getLogger(__name__)


class AutopilotState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


@dataclass
class AutopilotStatus:
    """托管写作状态"""
    novel_id: str = ""
    state: AutopilotState = AutopilotState.IDLE
    current_chapter: int = 0
    target_end_chapter: int = 0
    chapters_completed: int = 0
    total_words_written: int = 0
    started_at: Optional[str] = None
    message: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "novel_id": self.novel_id,
            "state": self.state.value,
            "current_chapter": self.current_chapter,
            "target_end_chapter": self.target_end_chapter,
            "chapters_completed": self.chapters_completed,
            "total_words_written": self.total_words_written,
            "started_at": self.started_at,
            "message": self.message,
            "errors": self.errors[-10:],
        }


# 全局状态存储（进程内单例）
_autopilot_sessions: dict[str, AutopilotStatus] = {}
_autopilot_tasks: dict[str, asyncio.Task] = {}
_autopilot_streams: dict[str, asyncio.Queue] = {}  # novel_id → SSE event queue


def get_autopilot_stream(novel_id: str) -> asyncio.Queue | None:
    """获取指定小说的流式事件队列"""
    return _autopilot_streams.get(novel_id)


def get_autopilot_status(novel_id: str) -> AutopilotStatus:
    """获取指定小说的托管写作状态（内存优先，回退 DB）"""
    if novel_id in _autopilot_sessions:
        return _autopilot_sessions[novel_id]
    # 尝试从 DB 恢复
    from app.db.connection import SessionLocal
    db = SessionLocal()
    try:
        cp = db.query(AutopilotCheckpoint).filter_by(novel_id=novel_id).first()
        if cp and cp.state not in ("idle", "completed"):
            return AutopilotStatus(
                novel_id=novel_id,
                state=AutopilotState(cp.state),
                current_chapter=cp.current_chapter,
                target_end_chapter=cp.target_end_chapter,
                chapters_completed=cp.chapters_completed,
                total_words_written=cp.total_words_written,
                started_at=cp.started_at,
                message="上次未完成（可恢复）",
                errors=json.loads(cp.errors_json) if cp.errors_json else [],
            )
    except Exception:
        pass
    finally:
        db.close()
    return AutopilotStatus(novel_id=novel_id)


def _save_checkpoint(db: Session, status: AutopilotStatus, auto_beats: bool = True) -> None:
    """将当前进度写入 DB"""
    try:
        cp = db.query(AutopilotCheckpoint).filter_by(novel_id=status.novel_id).first()
        if not cp:
            cp = AutopilotCheckpoint(novel_id=status.novel_id)
            db.add(cp)
        cp.state = status.state.value
        cp.current_chapter = status.current_chapter
        cp.target_end_chapter = status.target_end_chapter
        cp.chapters_completed = status.chapters_completed
        cp.total_words_written = status.total_words_written
        cp.auto_beats = auto_beats
        cp.errors_json = json.dumps(status.errors[-20:], ensure_ascii=False)
        cp.started_at = status.started_at or ""
        db.commit()
    except Exception as e:
        logger.warning("保存 autopilot 检查点失败: %s", e)
        db.rollback()


class AutopilotDaemon:
    """全托管写作守护进程"""

    def __init__(self, db: Session):
        self.db = db
        self._writer = ChapterWriter(db)
        self._outline = OutlineGenerator(db)
        self._pipeline = PostPipeline(db)
        self._context = ContextBuilder(db)

    async def start(
        self,
        novel_id: str,
        start_chapter: int,
        end_chapter: int,
        *,
        auto_beats: bool = True,
    ) -> AutopilotStatus:
        """启动全托管写作

        Args:
            novel_id: 小说 ID
            start_chapter: 起始章节号
            end_chapter: 结束章节号
            auto_beats: 是否自动生成节拍（否则用默认结构）
        """
        if novel_id in _autopilot_sessions:
            existing = _autopilot_sessions[novel_id]
            if existing.state == AutopilotState.RUNNING:
                raise ValueError("该小说已有运行中的托管任务")

        status = AutopilotStatus(
            novel_id=novel_id,
            state=AutopilotState.RUNNING,
            current_chapter=start_chapter,
            target_end_chapter=end_chapter,
            started_at=datetime.now(timezone.utc).isoformat(),
            message="托管写作已启动",
        )
        _autopilot_sessions[novel_id] = status
        _autopilot_streams[novel_id] = asyncio.Queue(maxsize=500)

        # 持久化初始检查点
        _save_checkpoint(self.db, status, auto_beats)

        # 在后台运行
        task = asyncio.create_task(
            self._run_loop(novel_id, start_chapter, end_chapter, auto_beats)
        )
        _autopilot_tasks[novel_id] = task
        return status

    async def resume_from_checkpoint(self, novel_id: str) -> AutopilotStatus:
        """从 DB 检查点恢复中断的托管写作"""
        cp = self.db.query(AutopilotCheckpoint).filter_by(novel_id=novel_id).first()
        if not cp or cp.state in ("idle", "completed"):
            raise ValueError("没有可恢复的检查点")
        if novel_id in _autopilot_sessions:
            existing = _autopilot_sessions[novel_id]
            if existing.state == AutopilotState.RUNNING:
                raise ValueError("该小说已有运行中的托管任务")

        resume_chapter = cp.current_chapter
        status = AutopilotStatus(
            novel_id=novel_id,
            state=AutopilotState.RUNNING,
            current_chapter=resume_chapter,
            target_end_chapter=cp.target_end_chapter,
            chapters_completed=cp.chapters_completed,
            total_words_written=cp.total_words_written,
            started_at=cp.started_at,
            message=f"从第{resume_chapter}章恢复托管写作",
            errors=json.loads(cp.errors_json) if cp.errors_json else [],
        )
        _autopilot_sessions[novel_id] = status
        _autopilot_streams[novel_id] = asyncio.Queue(maxsize=500)

        task = asyncio.create_task(
            self._run_loop(novel_id, resume_chapter, cp.target_end_chapter, cp.auto_beats)
        )
        _autopilot_tasks[novel_id] = task
        logger.info("从检查点恢复: %s, 从第%d章继续", novel_id, resume_chapter)
        return status

    def stop(self, novel_id: str) -> AutopilotStatus:
        """请求停止托管写作（当前章节写完后停止）"""
        status = _autopilot_sessions.get(novel_id)
        if not status or status.state != AutopilotState.RUNNING:
            raise ValueError("没有运行中的托管任务")
        status.state = AutopilotState.STOPPING
        status.message = "正在停止，等待当前章节完成..."
        return status

    def pause(self, novel_id: str) -> AutopilotStatus:
        """暂停托管写作"""
        status = _autopilot_sessions.get(novel_id)
        if not status or status.state != AutopilotState.RUNNING:
            raise ValueError("没有运行中的托管任务")
        status.state = AutopilotState.PAUSED
        status.message = "已暂停"
        return status

    def resume(self, novel_id: str) -> AutopilotStatus:
        """恢复托管写作"""
        status = _autopilot_sessions.get(novel_id)
        if not status or status.state != AutopilotState.PAUSED:
            raise ValueError("没有暂停中的任务")
        status.state = AutopilotState.RUNNING
        status.message = "已恢复"
        return status

    def _replace_db(self, db: Session) -> None:
        """替换所有子服务的 DB session"""
        self.db = db
        self._writer.db = db
        self._outline.db = db
        self._pipeline.db = db
        self._context.db = db

    async def _run_loop(
        self,
        novel_id: str,
        start_chapter: int,
        end_chapter: int,
        auto_beats: bool,
    ) -> None:
        """核心循环：逐章 生成节拍 → 写章节 → 跑管线"""
        # 创建独立的 DB session，不再依赖请求级 session
        from app.db.connection import SessionLocal
        db = SessionLocal()
        self._replace_db(db)
        try:
            status = _autopilot_sessions[novel_id]

            # 获取小说设定（字数等）
            from app.models.novel import Novel
            novel = db.query(Novel).filter_by(id=novel_id).first()
            words_per_chapter = (novel.words_per_chapter if novel else 2000) or 2000

            for ch_num in range(start_chapter, end_chapter + 1):
                # 检查控制信号
                if status.state == AutopilotState.STOPPING:
                    status.state = AutopilotState.IDLE
                    status.message = f"已停止，完成到第{ch_num - 1}章"
                    logger.info("托管写作已停止: %s, 完成到 #%d", novel_id, ch_num - 1)
                    return

                while status.state == AutopilotState.PAUSED:
                    await asyncio.sleep(1)

                if status.state != AutopilotState.RUNNING:
                    return

                status.current_chapter = ch_num
                status.message = f"正在写第{ch_num}章..."

                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    try:
                        # 1. 生成节拍
                        beats = None
                        if auto_beats:
                            status.message = f"第{ch_num}章 — 生成节拍中...{f' (重试{attempt-1})' if attempt > 1 else ''}"
                            ctx = self._context.build(novel_id, ch_num)
                            tv = ctx.to_template_vars()
                            beats_data = await self._outline.generate_chapter_beats(
                                novel_id, ch_num,
                                outline=tv.get("outline", ""),
                                previous_summaries=tv.get("previous_summaries", ""),
                                previous_ending=tv.get("previous_ending", ""),
                                story_log=tv.get("story_log", ""),
                                characters=tv.get("characters", ""),
                                active_foreshadows=tv.get("foreshadows", ""),
                                words_per_chapter=words_per_chapter,
                            )
                            beats = beats_data.get("beats")

                        # 2. 流式写章节 — 推送到 SSE 队列
                        status.message = f"第{ch_num}章 — 正在写作...{f' (重试{attempt-1})' if attempt > 1 else ''}"
                        q = _autopilot_streams.get(novel_id)
                        full_text = []
                        stream_error = None
                        async for event_json in self._writer.generate_chapter_stream(
                            novel_id, ch_num, beats=beats,
                            enable_settlement=False,  # PostPipeline 统一处理 truth 更新
                        ):
                            # 推送给前端
                            if q and not q.full():
                                await q.put(event_json)
                            # 收集正文 / 检查错误
                            try:
                                ev = json.loads(event_json)
                                if ev.get("type") == "chapter_chunk":
                                    full_text.append(ev.get("text", ""))
                                elif ev.get("type") == "error":
                                    stream_error = ev.get("message", "未知写作错误")
                            except (json.JSONDecodeError, TypeError):
                                pass

                        # 如果写作流内部报错，跳过章后管线
                        if stream_error:
                            raise RuntimeError(f"写作流错误: {stream_error}")

                        chapter_words = sum(len(t) for t in full_text)

                        # 3. 章后管线
                        status.message = f"第{ch_num}章写完({chapter_words}字)，运行章后管线..."
                        await self._pipeline.run(novel_id, ch_num)

                        status.chapters_completed += 1
                        status.total_words_written += chapter_words
                        # 每章完成后持久化
                        _save_checkpoint(self.db, status, auto_beats)
                        logger.info(
                            "托管写作 #%d 完成: %d字, 累计%d章/%d字",
                            ch_num, chapter_words,
                            status.chapters_completed, status.total_words_written,
                        )
                        break  # 成功，跳出重试循环

                    except Exception as e:
                        error_msg = f"第{ch_num}章失败(尝试{attempt}/{max_retries}): {e}"
                        logger.exception(error_msg)
                        if attempt < max_retries:
                            wait_sec = 10 * attempt
                            status.message = f"第{ch_num}章失败，{wait_sec}秒后重试..."
                            status.errors.append(error_msg)
                            await asyncio.sleep(wait_sec)
                        else:
                            status.errors.append(f"第{ch_num}章最终失败(已重试{max_retries}次): {e}")
                            # 全部重试用尽，跳到下一章

            # 循环正常结束
            if status.errors:
                status.state = AutopilotState.COMPLETED_WITH_ERRORS
            else:
                status.state = AutopilotState.COMPLETED
            _save_checkpoint(self.db, status, auto_beats)
            status.message = f"全部完成！共{status.chapters_completed}章/{status.total_words_written}字"
            if status.errors:
                status.message += f" ({len(status.errors)}个错误)"
            logger.info("托管写作完成: %s, %d章/%d字", novel_id, status.chapters_completed, status.total_words_written)
            # 发送结束信号并清理队列
            q = _autopilot_streams.get(novel_id)
            if q:
                await q.put(json.dumps({"type": "autopilot_done", "chapters_completed": status.chapters_completed, "total_words": status.total_words_written}, ensure_ascii=False))
            _autopilot_streams.pop(novel_id, None)
        finally:
            db.close()
