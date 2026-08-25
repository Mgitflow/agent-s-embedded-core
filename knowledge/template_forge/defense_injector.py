"""防御件注入器：把 defense/bsp 标准件接进生成工程（D2 整改，消除孤岛）。

念安 2026-08-23 整改：defense/bsp 六件套此前是孤岛模板（写了文件、单独编译验证过，
但组装逻辑从没把它们接进生成工程——生成出来的代码毫无防御）。本模块在
build_standard_project 组装时，把防御件的 .c/.h 注入工程文件树，业务层
app_business.c 通过 include 调用（接线见功能模板的 defense 声明）。

分层（防御件归属）：
  - defense 三件套（filter/debounce/clamp）= 业务层防御，纯软件零 HAL 依赖，可无条件注入。
  - bsp 三件套（timeout/watchdog/flash）= 驱动层防御，依赖 HAL 模块（IWDG/FLASH），
    按功能需求注入（工程没启用 IWDG 时注入 bsp_watchdog.c 会编译失败）。
"""
from __future__ import annotations

from pathlib import Path

# 防御件源目录
_DEFENSE_SRC = Path(__file__).resolve().parent / "defense"
_BSP_SRC = Path(__file__).resolve().parent / "bsp"

# 防御件单元 → 源文件前缀（加防御件 = 加一个条目，不改注入逻辑）
_UNITS: dict[str, Path] = {
    "filter": _DEFENSE_SRC / "defense_filter",
    "debounce": _DEFENSE_SRC / "defense_debounce",
    "clamp": _DEFENSE_SRC / "defense_clamp",
    "timeout": _BSP_SRC / "bsp_timeout",
    "watchdog": _BSP_SRC / "bsp_watchdog",
    "flash": _BSP_SRC / "bsp_flash",
    "startup_gate": _BSP_SRC / "bsp_startup_gate",
}

# 防御件单元 → 头文件名（业务层接线 include 用）
_UNIT_HEADER: dict[str, str] = {
    "filter": "defense_filter.h",
    "debounce": "defense_debounce.h",
    "clamp": "defense_clamp.h",
    "timeout": "bsp_timeout.h",
    "watchdog": "bsp_watchdog.h",
    "flash": "bsp_flash.h",
    "startup_gate": "bsp_startup_gate.h",
}


def defense_include_lines(units: tuple[str, ...] | list[str]) -> list[str]:
    """按防御件单元生成业务层 include 行（按环节绑定，不是全 include）。"""
    return [f'#include "{_UNIT_HEADER[u]}"' for u in units if u in _UNIT_HEADER]

# 默认注入的防御件（按环节绑定：默认空，由功能模板 defense 声明决定绑哪些）
DEFAULT_DEFENSE_UNITS: tuple[str, ...] = ()


def defense_file_contents(
    units: tuple[str, ...] = DEFAULT_DEFENSE_UNITS,
) -> dict[str, str]:
    """读防御件模板文件内容 → {文件名: 内容}。"""
    out: dict[str, str] = {}
    for unit in units:
        base = _UNITS.get(unit)
        if base is None:
            continue
        for suffix in (".c", ".h"):
            p = Path(str(base) + suffix)
            if p.exists():
                out[p.name] = p.read_text(encoding="utf-8")
    return out


def inject_defense_files(
    files: dict[str, str],
    base: str,
    units: tuple[str, ...] = DEFAULT_DEFENSE_UNITS,
) -> None:
    """把防御件 .c/.h 注入生成工程文件树（.c 进 Core/Src，.h 进 Core/Inc）。"""
    for name, content in defense_file_contents(units).items():
        if name.endswith(".c"):
            files[f"{base}/Core/Src/{name}"] = content
        else:
            files[f"{base}/Core/Inc/{name}"] = content


__all__ = [
    "DEFAULT_DEFENSE_UNITS",
    "defense_include_lines",
    "defense_file_contents",
    "inject_defense_files",
]
