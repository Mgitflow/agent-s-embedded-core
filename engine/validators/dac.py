"""DAC 校验器：校验 DAC 初始化顺序与 Start/SetValue 调用（4 条 MUST）。"""
from __future__ import annotations

import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    strip_comments,
)

_check_dac_clk_late = make_clock_first_validator(
    r"__HAL_RCC_DAC_CLK_ENABLE\s*\(",
    r"\bHAL_DAC_Init\s*\(",
    use_regex=True,
)


def _check_dac_init_present(ctx: dict[str, Any]) -> bool:
    """使能了 DAC 时钟就必须有 HAL_DAC_Init。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"__HAL_RCC_DAC_CLK_ENABLE\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_DAC_Init\s*\(", code))


def _check_dac_start_present(ctx: dict[str, Any]) -> bool:
    """初始化了 DAC 就必须有 HAL_DAC_Start（否则输出不生效）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_DAC_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_DAC_Start\s*\(", code))


def _check_dac_setvalue_present(ctx: dict[str, Any]) -> bool:
    """初始化了 DAC 就必须有 HAL_DAC_SetValue（否则无输出值）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_DAC_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_DAC_SetValue\s*\(", code))


# ── 参数级校验（2026-08-17 补：不只查"函数在不在"，查"参数对不对"）──
# 合法通道/对齐枚举（来源：STM32 HAL dac.h）
_DAC_CHANNELS = {"DAC_CHANNEL_1", "DAC_CHANNEL_2"}
_DAC_ALIGNS = {"DAC_ALIGN_8B_R", "DAC_ALIGN_12B_L", "DAC_ALIGN_12B_R"}


def _check_dac_channel_valid(ctx: dict[str, Any]) -> bool:
    """DAC 通道必须是 DAC_CHANNEL_1/2，出现非法通道（如 DAC_CHANNEL_3）拦截。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"HAL_DAC_(Init|Start|SetValue)\s*\(", code):
        return True
    return all(m.group(1) in _DAC_CHANNELS for m in re.finditer(r"\b(DAC_CHANNEL_\w+)\b", code))


def _check_dac_align_valid(ctx: dict[str, Any]) -> bool:
    """DAC 对齐必须是 8B_R/12B_L/12B_R，出现非法对齐拦截。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"HAL_DAC_(Init|Start|SetValue)\s*\(", code):
        return True
    return all(m.group(1) in _DAC_ALIGNS for m in re.finditer(r"\b(DAC_ALIGN_\w+)\b", code))


def register(registry: ValidatorRegistry) -> None:
    """Register DAC validators with the validator registry."""
    registry.register("E_DAC_CLK_LATE", _check_dac_clk_late)
    registry.register("E_DAC_NO_INIT", _check_dac_init_present)
    registry.register("E_DAC_NO_START", _check_dac_start_present)
    registry.register("E_DAC_NO_SETVALUE", _check_dac_setvalue_present)
    registry.register("E_DAC_CHANNEL_INVALID", _check_dac_channel_valid)
    registry.register("E_DAC_ALIGN_INVALID", _check_dac_align_valid)
