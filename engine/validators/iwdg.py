"""IWDG 校验器：拦截不喂狗、中断里喂狗、重复初始化/reload 越界三类经典坑。"""
from __future__ import annotations

import re
from typing import Any

from engine.validators.base import ValidatorRegistry, find_function_bodies, strip_comments

_RELOAD_MAX = 4095

_REFRESH_PATTERN = r"\bHAL_IWDG_Refresh\s*\("
_INIT_PATTERN = r"\bHAL_IWDG_Init\s*\("
_RELOAD_PATTERN = r"hiwdg\.Init\.Reload\s*=\s*(\d+)"

# 中断/回调函数名特征：放在这些函数体里的喂狗无法保护主循环
_ISR_FUNC_HINTS = ("IRQHandler", "Callback")


def _check_iwdg_refresh_present(ctx: dict[str, Any]) -> bool:
    """配置了 IWDG 就必须有喂狗调用（否则上电即复位）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(_INIT_PATTERN, code):
        return True
    return bool(re.search(_REFRESH_PATTERN, code))


def _check_iwdg_refresh_not_in_isr(ctx: dict[str, Any]) -> bool:
    """喂狗不能出现在中断/回调函数里（会掩盖主循环卡死）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(_REFRESH_PATTERN, code):
        return True
    for name, body in find_function_bodies(code):
        if any(hint in name for hint in _ISR_FUNC_HINTS) and re.search(_REFRESH_PATTERN, body):
            return False
    return True


def _check_iwdg_no_double_init(ctx: dict[str, Any]) -> bool:
    """IWDG 配置后即锁定，出现多次 HAL_IWDG_Init 视为重复配置。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    return len(re.findall(_INIT_PATTERN, code)) <= 1


def _check_iwdg_reload_range(ctx: dict[str, Any]) -> bool:
    """hiwdg.Init.Reload 必须落在 1..4095（12 位寄存器）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    for raw in re.findall(_RELOAD_PATTERN, code):
        try:
            if int(raw) > _RELOAD_MAX:
                return False
        except ValueError:
            return False
    return True


def register(registry: ValidatorRegistry) -> None:
    """Register IWDG validators with the validator registry."""
    registry.register("E_IWDG_NO_REFRESH", _check_iwdg_refresh_present)
    registry.register("E_IWDG_REFRESH_IN_ISR", _check_iwdg_refresh_not_in_isr)
    registry.register("E_IWDG_DOUBLE_INIT", _check_iwdg_no_double_init)
    registry.register("E_IWDG_RELOAD_RANGE", _check_iwdg_reload_range)
