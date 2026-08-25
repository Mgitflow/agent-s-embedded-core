"""骨架模板包：按芯片族拆分（base/f1/f4/f7/g4），自动发现注册，供骨架引擎按族动态选择。

去枚举（2026-08-22）：扫描本包下带 ``ORG_META`` 元数据的模板模块自动注册——
加一个系列 = 放一个模板模块（含 ORG_META），不改本文件。
"""
import importlib
import pkgutil
from typing import Any

from knowledge.loaders.mx_skeleton_templates.base import LINKER_LD_TEMPLATE, PROJECT_INFO_TEMPLATE


class OrgTemplates:
    """单个芯片族的完整模板集合。

    ECC Skills 元数据（2026-08-08）：version（模板版本）/ supported_peripherals
    （适用外设清单）/ hooks（建议挂载点）——供 manifest 自检与外部消费。
    """

    def __init__(
        self,
        name: str,
        hal_header: str,
        main_h_template: str,
        main_c_header: str,
        it_c_template: str,
        it_h_template: str,
        system_template: str,
        startup_template: str,
        version: str = "1.0",
        supported_peripherals: tuple[str, ...] = (),
        hooks: tuple[str, ...] = ("post_generate", "post_verify"),
    ) -> None:
        self.name = name
        self.hal_header = hal_header
        self.main_h_template = main_h_template
        self.main_c_header = main_c_header
        self.it_c_template = it_c_template
        self.it_h_template = it_h_template
        self.system_template = system_template
        self.startup_template = startup_template
        self.version = version
        self.supported_peripherals = supported_peripherals
        self.hooks = hooks

    def template_manifest(self) -> dict[str, Any]:
        """SKILL.md 式清单：模板名/版本/适用外设/hooks（ECC Skills 借鉴）。"""
        return {
            "name": f"templates.{self.name.lower()}",
            "version": self.version,
            "hal_header": self.hal_header,
            "supported_peripherals": list(self.supported_peripherals),
            "hooks": list(self.hooks),
            "members": [
                "main_h", "main_c", "it_c", "it_h", "system", "startup", "linker_ld",
            ],
        }


def _discover_templates() -> dict[str, OrgTemplates]:
    """扫描本包下带 ORG_META 元数据的模板模块，自动注册 OrgTemplates。"""
    registry: dict[str, OrgTemplates] = {}
    pkg_name = __name__
    pkg = importlib.import_module(pkg_name)
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        name = mod_info.name
        if name.startswith("_") or name == "base":
            continue
        try:
            mod = importlib.import_module(f"{pkg_name}.{name}")
        except Exception:  # noqa: BLE001 —— 模板模块 import 失败则跳过，不影响其它系列
            continue
        meta = getattr(mod, "ORG_META", None)
        if not isinstance(meta, dict):
            continue
        family_key = meta.get("family_key")
        if not family_key:
            continue
        registry[family_key] = OrgTemplates(
            name=family_key,
            hal_header=meta.get("hal_header", ""),
            main_h_template=meta.get("main_h_template", ""),
            main_c_header=meta.get("main_c_header", ""),
            it_c_template=meta.get("it_c_template", ""),
            it_h_template=meta.get("it_h_template", ""),
            system_template=meta.get("system_template", ""),
            startup_template=meta.get("startup_template", ""),
            version="1.0",
            supported_peripherals=tuple(meta.get("supported_peripherals", ())),
        )
    return registry


_REGISTRY: dict[str, OrgTemplates] = _discover_templates()

_FALLBACK_KEY = "STM32F4xx"


def get_family_templates(family_name: str) -> OrgTemplates:
    """按芯片族名称返回对应模板集合。未知族回退到 F4（材料基座，缺失则 fail-closed）。"""
    if family_name in _REGISTRY:
        return _REGISTRY[family_name]
    return _REGISTRY[_FALLBACK_KEY]


__all__ = [
    "OrgTemplates",
    "LINKER_LD_TEMPLATE",
    "PROJECT_INFO_TEMPLATE",
    "get_family_templates",
]
