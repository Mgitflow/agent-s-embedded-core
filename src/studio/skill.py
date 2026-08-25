"""Skill 基类（空壳契约）：只定义 name/title/schema/run 契约，业务由各技能包外部实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from .context import SkillContext
from .result import SkillResult


class Skill(ABC):
    """
    Skill 抽象基类。

    子类必须定义 name/title/description 并实现 run()。
    注册：@register_skill 装饰器（src/studio/registry.py）。
    """

    name: ClassVar[str] = ""
    title: ClassVar[str] = ""
    description: ClassVar[str] = ""
    version: ClassVar[str] = "3.6.0"
    input_schema: ClassVar[dict[str, Any]] = {}     # {param: 类型/说明}
    output_schema: ClassVar[dict[str, Any]] = {}    # {key: 类型/说明}

    # --- 状态（由 studio.yaml 声明，静态；workspace.mode 是运行时选择） ---
    status: ClassVar[str] = "active"      # active / preview / reserved

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            raise TypeError(f"Skill {cls.__name__} 必须定义 name")

    @abstractmethod
    async def run(self, ctx: SkillContext, **params: Any) -> SkillResult:
        """
        技能执行入口（统一契约）。

        Args:
            ctx: 工作室注入的共享依赖（SkillContext）。
            **params: 技能入参（与 input_schema 对齐）。

        Returns:
            SkillResult（RPC 字段 + 可选流水线字段）。
        """
        raise NotImplementedError

    # --- 对外元数据 ---
    # 注：manifest 技能序列化统一走 registry.to_manifest_skills()（字段过滤版），
    # 本处不保留重复的 to_manifest（2026-08-05 清理死代码时移除）。
