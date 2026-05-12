"""预置内置提示词模板 — 首次启动自动写入，已存在则跳过

提示词体系参考 PlotPilot prompts_defaults.json v3
集成 chinese-novelist-skill 封神版 v2.0 六维体系
"""
from __future__ import annotations

import logging
import pathlib
from sqlalchemy.orm import Session

from app.db.connection import SessionLocal
from app.models.prompt import PromptTemplate

logger = logging.getLogger(__name__)

# ── 内置提示词（从 JSON 文件加载）────────────────────────────────

_JSON_FILE = pathlib.Path(__file__).parent / "prompts_defaults.json"


def _load_builtin_prompts() -> list[dict]:
    """从 prompts_defaults.json 加载内置提示词列表。"""
    if not _JSON_FILE.exists():
        logger.warning("prompts_defaults.json 不存在，跳过种子")
        return []
    import json
    with open(_JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_prompts() -> int:
    """写入/更新内置提示词。

    - 新的 stage+name → 插入
    - 已存在且 JSON 有 version > DB version → 更新 content + description
    - 其余跳过
    返回 新增+更新 条数。
    """
    prompts = _load_builtin_prompts()
    if not prompts:
        return 0
    db: Session = SessionLocal()
    changed = 0
    try:
        for item in prompts:
            stage = item["stage"]
            name = item["name"]
            new_version = item.get("version", 1)
            existing = (
                db.query(PromptTemplate)
                .filter_by(stage=stage, name=name)
                .first()
            )
            if existing:
                if new_version > (existing.version or 0):
                    existing.content = item["content"]
                    existing.description = item.get("description", existing.description)
                    existing.version = new_version
                    changed += 1
                    logger.debug("更新提示词 [%s/%s] v%d→v%d", stage, name, existing.version, new_version)
                continue
            row = PromptTemplate(
                stage=stage,
                name=name,
                content=item["content"],
                description=item.get("description", ""),
                version=new_version,
                is_active=True,
            )
            db.add(row)
            changed += 1
        db.commit()
    finally:
        db.close()

    if changed:
        logger.info("提示词模板同步: %d 条新增/更新", changed)
    return changed
