"""Skill 注册中心：@register_skill 装饰器收集能力声明，studio.yaml 三态控制启用，并做能力自检。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .skill import Skill

logger = logging.getLogger(__name__)

# 类级注册表：name -> Skill 子类
_SKILL_CLASSES: dict[str, type[Skill]] = {}


def register_skill(cls: type[Skill]) -> type[Skill]:
    """技能注册装饰器。

    用法：
        @register_skill
        class CodeGenSkill(Skill):
            name = "code_gen"
            ...
    """
    if cls.name in _SKILL_CLASSES:
        logger.warning("Skill 名称重复，后者覆盖前者: %s", cls.name)
    _SKILL_CLASSES[cls.name] = cls
    logger.debug("已注册 Skill 类: %s", cls.name)
    return cls


class SkillRegistry:
    """技能注册表：按 studio.yaml 三态实例化技能。"""

    def __init__(self, config_path: Path | None = None):
        self._config_path = Path(config_path) if config_path else (
            Path(__file__).resolve().parent.parent.parent / "config" / "studio.yaml"
        )
        self._config = self._load_config()
        self._skills: dict[str, Skill] = {}
        self._init_skills()

    # --- 配置 ---

    def _load_config(self) -> dict[str, Any]:
        """加载 studio.yaml 的 studio.skills 段。"""
        if not self._config_path.exists():
            logger.warning("Studio 配置不存在: %s", self._config_path)
            return {}
        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("studio", {}).get("skills", {}) or {}
        except Exception as e:
            logger.warning("读取 Studio 配置失败: %s", e)
            return {}

    def _init_skills(self) -> None:
        """按配置三态实例化：active/preview 实例化，reserved 仅保留元数据。"""
        cfg_skills = self._config or {}
        for name, meta in cfg_skills.items():
            status = meta.get("status", "reserved")
            cls = _SKILL_CLASSES.get(name)
            if cls is None:
                if status != "reserved":
                    logger.warning("技能 %s 状态=%s 但未注册 @register_skill", name, status)
                continue
            # 将配置状态回写到类（reserved 类不实例化，但保留状态信息）
            cls.status = status
            if status == "reserved":
                logger.debug("技能 %s 为 reserved，跳过实例化", name)
                continue
            try:
                self._skills[name] = cls()
                logger.info("技能 %s 已实例化（状态=%s）", name, status)
            except Exception as e:
                logger.warning("技能 %s 实例化失败: %s", name, e)

    # --- 查询 ---

    @property
    def names(self) -> list[str]:
        return sorted(self._skills.keys())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def has(self, name: str) -> bool:
        return name in self._skills

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def list_skills(self) -> list[dict[str, Any]]:
        """全部技能元数据（含 reserved，供 /skills 端点展示）。"""
        result = []
        cfg_skills = self._config or {}
        for name, meta in cfg_skills.items():
            cls = _SKILL_CLASSES.get(name)
            result.append({
                "name": name,
                "title": (meta.get("name") or (cls.title if cls else name)),
                "description": meta.get("description", ""),
                "status": meta.get("status", "unknown"),
                "active": name in self._skills,
            })
        return result

    def resolve_endpoint(self, endpoint: str) -> str | None:
        """按 endpoint 路径反查技能配置名（如 /skill/code -> code_gen）。"""
        cfg_skills = self._config or {}
        for key, meta in cfg_skills.items():
            if meta.get("endpoint", f"/skill/{key}") == endpoint:
                return key
        return None

    def to_manifest_skills(self) -> list[dict[str, Any]]:
        """
        studio 技能清单（过滤到 SkillSchema 兼容字段，供 manifest 使用）。

        与 Skill.to_manifest() 不同：只保留 SkillSchema 认识的字段
        （name/description/input_schema/output_schema/async_only/dangerous），
        避免多余字段撑爆契约。
        """
        result = []
        cfg_skills = self._config or {}
        for name, meta in cfg_skills.items():
            cls = _SKILL_CLASSES.get(name)
            result.append({
                "name": name,
                "description": meta.get("description") or (cls.description if cls else ""),
                "input_schema": getattr(cls, "input_schema", {}) if cls else {},
                "output_schema": getattr(cls, "output_schema", {}) if cls else {},
                "async_only": True,
                "dangerous": False,
            })
        return result

    # --- 自检 ---

    def check_capabilities(self, declared: list[str]) -> dict[str, Any]:
        """
        能力自检：声明了但没入口的能力清单。

        Args:
            declared: manifest/配置中声明的技能名列表。

        Returns:
            {"ok": bool, "missing": [...], "declared": [...], "registered": [...]}
        """
        registered = set(self._skills.keys()) | set(_SKILL_CLASSES.keys())
        declared_set = set(declared)
        missing = sorted(declared_set - registered)
        return {
            "ok": not missing,
            "missing": missing,
            "declared": sorted(declared_set),
            "registered": sorted(registered),
        }


def create_registry(config_path: Path | None = None) -> SkillRegistry:
    """创建技能注册表实例。"""
    return SkillRegistry(config_path=config_path)


def registered_names() -> list[str]:
    """已注册的技能类名（无需实例化）。"""
    return sorted(_SKILL_CLASSES.keys())
