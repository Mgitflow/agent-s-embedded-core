"""WWDG 校验器：拦截不喂狗、中断喂狗、窗口值越界、计数器越界、重复初始化五类经典坑。"""
from __future__ import annotations

import re
from typing import Any

from engine.validators.base import ValidatorRegistry, find_function_bodies, strip_comments

_COUNTER_MIN = 64   # 0x40
_COUNTER_MAX = 127  # 0x7F

_INIT_PATTERN = r"\bHAL_WWDG_Init\s*\("
_REFRESH_PATTERN = r"\bHAL_WWDG_Refresh\s*\("
_COUNTER_PATTERN = r"hwwdg\.Init\.Counter\s*=\s*(\d+)"
_WINDOW_PATTERN = r"hwwdg\.Init\.Window\s*=\s*(\d+)"

# 中断/回调函数名特征：放在这些函数体里的喂狗无法保护主循环
_ISR_FUNC_HINTS = ("IRQHandler", "Callback")



def _check_wwdg_refresh_present(ctx: dict[str, Any]) -> bool:
    """配置了 WWDG 就必须有喂狗调用（否则上电即复位）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(_INIT_PATTERN, code):
        return True
    return bool(re.search(_REFRESH_PATTERN, code))

def _check_wwdg_refresh_not_in_isr(ctx: dict[str, Any]) -> bool:
    """喂狗不能出现在中断/回调函数里（会掩盖主循环卡死）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(_REFRESH_PATTERN, code):
        return True
    for name, body in find_function_bodies(code):
        if any(hint in name for hint in _ISR_FUNC_HINTS) and re.search(_REFRESH_PATTERN, body):
            return False
    return True

def _check_wwdg_window_lt_counter(ctx: dict[str, Any]) -> bool:
    """窗口值必须 < 计数器值（否则无窗口期，喂狗必复位）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(_INIT_PATTERN, code):
        return True
    counter_m = re.search(_COUNTER_PATTERN, code)
    window_m = re.search(_WINDOW_PATTERN, code)
    if not counter_m or not window_m:
        return True  # 无显式值 → 模板兜底（不误报）
    counter = int(counter_m.group(1))
    window = int(window_m.group(1))
    return window < counter

def _check_wwdg_counter_range(ctx: dict[str, Any]) -> bool:
    """计数器必须落在 0x40..0x7F（越界 → 上电即复位）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(_INIT_PATTERN, code):
        return True
    counter_m = re.search(_COUNTER_PATTERN, code)
    if not counter_m:
        return True
    counter = int(counter_m.group(1))
    return _COUNTER_MIN <= counter <= _COUNTER_MAX

def _check_wwdg_no_double_init(ctx: dict[str, Any]) -> bool:
    """WWDG 重复初始化无意义（使能后不可关闭，重配会干扰窗口期）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    return len(re.findall(_INIT_PATTERN, code)) <= 1


def register(registry: ValidatorRegistry) -> None:
    """注册 WWDG 校验规则到注册表（与 IWDG 同签名：code + check 位置参数）。"""
    registry.register("E_WWDG_NO_REFRESH", _check_wwdg_refresh_present)
    registry.register("E_WWDG_REFRESH_IN_ISR", _check_wwdg_refresh_not_in_isr)
    registry.register("E_WWDG_WINDOW_INVALID", _check_wwdg_window_lt_counter)
    registry.register("E_WWDG_COUNTER_RANGE", _check_wwdg_counter_range)
    registry.register("E_WWDG_DOUBLE_INIT", _check_wwdg_no_double_init)
