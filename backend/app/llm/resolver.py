"""StageModelResolver — 按阶段读取固定 LLM Profile，零自动判断。

运行时调用 get_llm_for_stage("chapter_writing") 即可获得该阶段绑定的 LLM 客户端。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.llm.profiles import (
    LLMProfileRow, StageBindingRow, LLMConfigMeta,
    LLMProfile, StageBinding,
)
from app.llm.presets import get_preset
from app.llm.client import create_llm_client, LLMClient

logger = logging.getLogger(__name__)


class StageModelResolver:
    """按阶段解析 LLM Profile 并返回对应客户端。

    设计原则：
    - 零自动判断：每个阶段绑定哪个 Profile 完全由用户手动选定
    - 全局兜底：未绑定的阶段使用全局默认 Profile
    - 双预设：内置 practical(实用版) 和 flagship(旗舰版) 两套预设
    """

    def __init__(self, db: Session):
        self.db = db

    # ── 公共接口 ──────────────────────────────────────────────────

    def get_profile_for_stage(self, stage: str) -> Optional[LLMProfile]:
        """获取某阶段绑定的 LLMProfile（支持 model_override）"""
        binding = self.db.query(StageBindingRow).filter_by(stage=stage).first()
        if binding:
            row = self.db.query(LLMProfileRow).filter_by(id=binding.profile_id).first()
            if row:
                profile = self._row_to_profile(row)
                # 如果绑定指定了 model_override，覆盖 profile 的 model
                if binding.model_override:
                    profile.model = binding.model_override
                return profile

        # 没有覆盖 → 返回全局默认
        return self._get_global_default()

    def get_llm_for_stage(self, stage: str) -> LLMClient:
        """获取某阶段的 LLM 客户端（直接可用）"""
        profile = self.get_profile_for_stage(stage)
        if profile is None:
            raise ValueError(f"阶段 '{stage}' 未配置 LLM Profile，请在设置页完成配置")
        return create_llm_client(profile)

    def get_active_preset(self) -> str:
        """获取当前激活的预设名称"""
        meta = self.db.query(LLMConfigMeta).filter_by(key="active_preset").first()
        return meta.value if meta else "practical"

    def get_all_bindings(self) -> list[StageBinding]:
        """获取所有阶段绑定"""
        rows = self.db.query(StageBindingRow).all()
        return [StageBinding(stage=r.stage, profile_id=r.profile_id, preset_name=r.preset_name) for r in rows]

    def get_all_profiles(self) -> list[LLMProfile]:
        """获取所有已配置的 Profile"""
        rows = self.db.query(LLMProfileRow).order_by(LLMProfileRow.sort_order).all()
        return [self._row_to_profile(r) for r in rows]

    # ── 预设操作 ──────────────────────────────────────────────────

    def apply_preset(self, preset_name: str) -> None:
        """一键应用预设，覆盖所有阶段绑定"""
        preset = get_preset(preset_name)
        profiles = self.get_all_profiles()
        profile_map = {p.model: p.id for p in profiles}

        # 清空旧绑定
        self.db.query(StageBindingRow).delete()

        for stage, stage_model in preset.items():
            profile_id = profile_map.get(stage_model.model)
            if profile_id:
                self.db.add(StageBindingRow(
                    stage=stage,
                    profile_id=profile_id,
                    preset_name=preset_name,
                ))
            else:
                logger.warning(
                    "预设 '%s' 阶段 '%s' 指定模型 '%s' 未找到对应 Profile，跳过",
                    preset_name, stage, stage_model.model,
                )

        # 更新激活预设
        meta = self.db.query(LLMConfigMeta).filter_by(key="active_preset").first()
        if meta:
            meta.value = preset_name
        else:
            self.db.add(LLMConfigMeta(key="active_preset", value=preset_name))

        self.db.commit()

    def set_stage_binding(self, stage: str, profile_id: str, model_override: str = "") -> None:
        """手动设置单个阶段的绑定（自动变为 custom 预设）"""
        binding = self.db.query(StageBindingRow).filter_by(stage=stage).first()
        if binding:
            binding.profile_id = profile_id
            binding.preset_name = "custom"
            binding.model_override = model_override
        else:
            self.db.add(StageBindingRow(
                stage=stage, profile_id=profile_id,
                preset_name="custom", model_override=model_override,
            ))

        # 标记为自定义
        meta = self.db.query(LLMConfigMeta).filter_by(key="active_preset").first()
        if meta:
            meta.value = "custom"
        else:
            self.db.add(LLMConfigMeta(key="active_preset", value="custom"))

        self.db.commit()

    # ── Profile CRUD ──────────────────────────────────────────────

    def create_profile(self, profile: LLMProfile) -> LLMProfile:
        """创建新的 LLM Profile"""
        row = LLMProfileRow(
            id=profile.id, name=profile.name, protocol=profile.protocol,
            base_url=profile.base_url, api_key=profile.api_key,
            model=profile.model, temperature=profile.temperature,
            max_tokens=profile.max_tokens, timeout_seconds=profile.timeout_seconds,
            notes=profile.notes,
        )
        self.db.add(row)
        self.db.commit()
        return profile

    def update_profile(self, profile_id: str, updates: dict) -> Optional[LLMProfile]:
        """更新 Profile"""
        row = self.db.query(LLMProfileRow).filter_by(id=profile_id).first()
        if not row:
            return None
        for k, v in updates.items():
            if hasattr(row, k):
                setattr(row, k, v)
        self.db.commit()
        return self._row_to_profile(row)

    def delete_profile(self, profile_id: str) -> bool:
        """删除 Profile（同时清理绑定）"""
        self.db.query(StageBindingRow).filter_by(profile_id=profile_id).delete()
        count = self.db.query(LLMProfileRow).filter_by(id=profile_id).delete()
        self.db.commit()
        return count > 0

    # ── 内部工具 ──────────────────────────────────────────────────

    def _get_global_default(self) -> Optional[LLMProfile]:
        """获取全局默认 Profile（第一个 Profile）"""
        row = self.db.query(LLMProfileRow).order_by(LLMProfileRow.sort_order).first()
        return self._row_to_profile(row) if row else None

    @staticmethod
    def _row_to_profile(row: LLMProfileRow) -> LLMProfile:
        return LLMProfile(
            id=row.id, name=row.name, protocol=row.protocol,
            base_url=row.base_url, api_key=row.api_key,
            model=row.model, temperature=row.temperature,
            max_tokens=row.max_tokens, timeout_seconds=row.timeout_seconds,
            notes=row.notes,
        )
