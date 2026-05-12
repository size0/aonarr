"""故事日志 — 按卷分层管理，保障章间连贯

文件结构（每部小说一个目录）：
data/story_logs/{novel_id}/
├── global.md          ← 全书概要（~300字，每章重写）
├── vol_1_summary.md   ← 第一卷总结（卷结束时生成，~200字）
├── vol_2_summary.md   ← 第二卷总结（卷结束时生成）
├── vol_2_chapters.md  ← 当前卷的章节详细日志（只保留当前卷）
└── ...

读取逻辑：
- 写第25章（第二卷第5章）时读取：
  全书概要(300字) + 第一卷总结(200字) + 第二卷章节日志(21-24章，~600字)
  ≈ 1100字，恒定

- 写第100章（第五卷第20章）时读取：
  全书概要(300字) + 前4卷总结(800字) + 第五卷近5章日志(750字)
  ≈ 1850字，可控
"""
from __future__ import annotations

import re
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.llm.resolver import StageModelResolver
from app.llm.client import GenerationConfig
from app.models.novel import Chapter, OutlineNode

logger = logging.getLogger(__name__)

_LOG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "story_logs"

_CHAPTER_LOG_PROMPT = """你是小说编辑助手。阅读章节正文，输出结构化日志。

格式（严格遵守，不加多余内容）：
概述：一句话说本章发生了什么（60字内）
结尾：本章结束时谁在哪、在做什么、什么悬而未决（50字内）
人物：
- 名字 — 关键行为 — 当前状态
线索：本章埋下或推进的伏笔（没有写"无"）
衔接：下一章应从什么情境开始（30字内）"""

_VOLUME_SUMMARY_PROMPT = """你是小说编辑。请为这一卷写一份完结总结，供后续卷次写作参考。

要求（总计200字以内）：
1. 本卷主线：这一卷讲了什么故事（80字内）
2. 人物结局状态：每个重要角色在本卷结束时的状态（每人一句）
3. 遗留线索：本卷留下的未解决伏笔/悬念（最多3条）
4. 卷末情境：本卷最后一幕的具体场景（30字内）

直接输出内容，不加标记。"""

_GLOBAL_SUMMARY_PROMPT = """你是小说编辑。根据下面的【旧概要】和【新增章节日志】，重写一份全书进度概要。

要求：
1. 主线进度：当前故事推进到哪了（100字内）
2. 人物现状：每个重要角色一句话当前状态（最多6人）
3. 关键线索：目前未解决的悬念/伏笔（最多5条）
4. 已完成事件：已结束的重大事件（一句话带过，最多3条）

总字数控制在300字以内。直接输出内容。"""

_RECENT_KEEP = 5  # 当前卷内保留最近几章日志


# ─────────── 路径管理 ───────────

def _get_novel_dir(novel_id: str) -> Path:
    d = _LOG_DIR / novel_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _global_path(novel_id: str) -> Path:
    return _get_novel_dir(novel_id) / "global.md"


def _vol_summary_path(novel_id: str, vol_num: int) -> Path:
    return _get_novel_dir(novel_id) / f"vol_{vol_num}_summary.md"


def _vol_chapters_path(novel_id: str, vol_num: int) -> Path:
    return _get_novel_dir(novel_id) / f"vol_{vol_num}_chapters.md"


# ─────────── 卷号查询 ───────────

def _get_volume_info(db: Session, novel_id: str, chapter_number: int) -> dict:
    """查询章节所在的卷号和卷内信息"""
    volumes = db.query(OutlineNode).filter_by(novel_id=novel_id, level='volume').all()
    chapters = db.query(OutlineNode).filter_by(novel_id=novel_id, level='chapter').all()

    # 构建卷→章节范围映射
    vol_info = {}
    for vol in volumes:
        m = re.match(r'^第(\d+)卷', vol.title)
        if not m:
            continue
        vol_num = int(m.group(1))
        vol_chapters = sorted(
            [c for c in chapters if c.parent_id == vol.id],
            key=lambda c: int(m.group(1)) if (m := re.match(r'^第(\d+)章', c.title)) else 9999,
        )
        if vol_chapters:
            first_ch = int(re.match(r'^第(\d+)章', vol_chapters[0].title).group(1))
            last_ch = int(re.match(r'^第(\d+)章', vol_chapters[-1].title).group(1))
            vol_info[vol_num] = {
                "title": vol.title,
                "first_chapter": first_ch,
                "last_chapter": last_ch,
                "chapter_count": len(vol_chapters),
            }

    # 找当前章属于哪一卷
    current_vol = 1
    for vn, vi in sorted(vol_info.items()):
        if vi["first_chapter"] <= chapter_number <= vi["last_chapter"]:
            current_vol = vn
            break

    return {
        "current_volume": current_vol,
        "total_volumes": len(vol_info),
        "volumes": vol_info,
        "is_last_of_volume": vol_info.get(current_vol, {}).get("last_chapter") == chapter_number,
    }


# ─────────── 读取 ───────────

def read_story_log(novel_id: str) -> str:
    """读取故事日志全文（兼容旧格式）"""
    gp = _global_path(novel_id)
    if gp.exists():
        return gp.read_text(encoding="utf-8")
    # 兼容旧单文件格式
    old_path = _LOG_DIR / f"{novel_id}.md"
    if old_path.exists():
        return old_path.read_text(encoding="utf-8")
    return ""


def read_recent_log(novel_id: str, last_n: int = _RECENT_KEEP, db: Session = None,
                    chapter_number: int = 0) -> str:
    """读取供 prompt 注入的故事日志

    输出 = 全书概要 + 前几卷总结 + 当前卷近期章节日志
    """
    parts = []

    # 1. 全书概要
    gp = _global_path(novel_id)
    if gp.exists():
        parts.append(gp.read_text(encoding="utf-8"))

    # 2. 查卷号信息
    vol_num = 1
    if db and chapter_number > 0:
        try:
            vi = _get_volume_info(db, novel_id, chapter_number)
            vol_num = vi["current_volume"]
        except Exception:
            vol_num = 1

    # 3. 前几卷的总结
    for v in range(1, vol_num):
        vsp = _vol_summary_path(novel_id, v)
        if vsp.exists():
            parts.append(f"══ 第{v}卷总结 ══\n" + vsp.read_text(encoding="utf-8"))

    # 4. 当前卷的近期章节日志
    vcp = _vol_chapters_path(novel_id, vol_num)
    if vcp.exists():
        full = vcp.read_text(encoding="utf-8")
        # 按章节分割，取最后 last_n 章
        sections = re.split(r'\n(?=---第\d+章)', full)
        ch_sections = [s.strip() for s in sections if s.strip().startswith("---第")]
        recent = ch_sections[-last_n:]
        if recent:
            parts.append(f"══ 当前卷(第{vol_num}卷)近期章节 ══\n" + "\n\n".join(recent))

    return "\n\n".join(parts) if parts else ""


# ─────────── 写入 ───────────

async def generate_and_append_log(
    db: Session,
    resolver: StageModelResolver,
    novel_id: str,
    chapter_number: int,
) -> str:
    """为指定章节生成日志并更新文件"""
    chapter = (
        db.query(Chapter)
        .filter_by(novel_id=novel_id, number=chapter_number)
        .first()
    )
    if not chapter or not chapter.content:
        logger.warning("故事日志跳过: 章节 %d 无内容", chapter_number)
        return ""

    llm = resolver.get_llm_for_stage("post_chapter_pipeline")
    title = chapter.title or f"第{chapter_number}章"

    # 查卷信息
    vol_info = _get_volume_info(db, novel_id, chapter_number)
    vol_num = vol_info["current_volume"]
    is_last = vol_info["is_last_of_volume"]

    # ── Step 1: 生成本章日志 ──
    config = GenerationConfig(system=_CHAPTER_LOG_PROMPT, max_tokens=500, temperature=0.3)
    user_prompt = f"第{chapter_number}章《{title}》（{len(chapter.content)}字）：\n\n{chapter.content[:6000]}"

    try:
        result = await llm.generate(user_prompt, config)
        new_log = result.content.strip() if hasattr(result, "content") else str(result).strip()
    except Exception as e:
        logger.warning("章节日志生成失败，降级: %s", e)
        new_log = f"概述：{chapter.summary or '未提取'}\n结尾：见正文末段\n衔接：接续上文"

    chapter_entry = f"---第{chapter_number}章 {title}---\n{new_log}"

    # ── Step 2: 追加到当前卷的章节日志 ──
    vcp = _vol_chapters_path(novel_id, vol_num)
    with open(vcp, "a", encoding="utf-8") as f:
        f.write(("\n\n" if vcp.exists() and vcp.stat().st_size > 0 else "") + chapter_entry)

    # ── Step 3: 更新全书概要 ──
    gp = _global_path(novel_id)
    old_global = gp.read_text(encoding="utf-8") if gp.exists() else ""
    try:
        config2 = GenerationConfig(system=_GLOBAL_SUMMARY_PROMPT, max_tokens=600, temperature=0.3)
        prompt2 = f"【旧概要】\n{old_global or '无（第一章）'}\n\n【新增章节日志】\n{chapter_entry}"
        result2 = await llm.generate(prompt2, config2)
        new_global = result2.content.strip() if hasattr(result2, "content") else str(result2).strip()
        gp.write_text(new_global, encoding="utf-8")
    except Exception as e:
        logger.warning("全书概要更新失败: %s", e)

    # ── Step 4: 如果是本卷最后一章 → 生成卷总结 ──
    if is_last:
        await _generate_volume_summary(db, llm, novel_id, vol_num)

    logger.info(
        "故事日志更新: %s #%d (第%d卷), 是否卷末=%s",
        novel_id, chapter_number, vol_num, is_last,
    )
    return chapter_entry


async def _generate_volume_summary(
    db: Session, llm, novel_id: str, vol_num: int,
) -> str:
    """读取本卷所有章节日志，生成卷总结"""
    vcp = _vol_chapters_path(novel_id, vol_num)
    if not vcp.exists():
        return ""

    vol_chapters_text = vcp.read_text(encoding="utf-8")

    config = GenerationConfig(system=_VOLUME_SUMMARY_PROMPT, max_tokens=500, temperature=0.3)
    prompt = f"第{vol_num}卷全部章节日志：\n\n{vol_chapters_text[:4000]}"

    try:
        result = await llm.generate(prompt, config)
        summary = result.content.strip() if hasattr(result, "content") else str(result).strip()
    except Exception as e:
        logger.warning("卷总结生成失败: %s", e)
        summary = f"第{vol_num}卷已完成，详见章节日志。"

    vsp = _vol_summary_path(novel_id, vol_num)
    vsp.write_text(summary, encoding="utf-8")
    logger.info("第%d卷总结生成: %d字", vol_num, len(summary))
    return summary
