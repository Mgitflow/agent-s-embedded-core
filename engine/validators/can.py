"""CAN 校验器。"""
import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    make_deinit_clk_off_validator,
    make_reconfig_deinit_validator,
    strip_comments,
)

_check_can_clk_late = make_clock_first_validator(
    r"__HAL_RCC_CAN\d+_CLK_ENABLE\s*\(",
    r"\bHAL_CAN_Init\s*\(",
    use_regex=True,
)

_check_can_reconfig_no_deinit = make_reconfig_deinit_validator(r"\bHAL_CAN_DeInit\s*\(")

_check_can_deinit_no_clk_off = make_deinit_clk_off_validator(
    r"__HAL_RCC_CAN\d+_CLK_DISABLE\s*\("
)


def _check_can_filter(ctx: dict[str, Any]) -> bool:
    """检查是否配置了 CAN 过滤器（2026-08-13 上下文化：无 CAN 初始化则放行）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    # 修复：无 HAL_CAN_Init 时要求 ConfigFilter 属误报（同 ADC 修复）
    if not re.search(r"\bHAL_CAN_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_CAN_ConfigFilter\s*\(", code))


def _check_can_started(ctx: dict[str, Any]) -> bool:
    """检查是否调用了 HAL_CAN_Start（2026-08-13 上下文化：无 CAN 初始化则放行）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    if not re.search(r"\bHAL_CAN_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_CAN_Start\s*\(", code))


def _check_can_irq_nvic(ctx: dict[str, Any]) -> bool:
    """如果使能了 CAN 中断通知，则必须配置 NVIC。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    if not re.search(r"\bHAL_CAN_ActivateNotification\s*\(", code):
        return True
    has_priority = bool(re.search(r"\bHAL_NVIC_SetPriority\s*\(", code))
    has_enable = bool(re.search(r"\bHAL_NVIC_EnableIRQ\s*\(", code))
    return has_priority and has_enable


def register(registry: ValidatorRegistry) -> None:
    """Register CAN validators with the validator registry."""
    registry.register("E_CAN_CLK_LATE", _check_can_clk_late)
    registry.register("E_CAN_NO_FILTER", _check_can_filter)
    registry.register("E_CAN_NOT_STARTED", _check_can_started)
    registry.register("E_CAN_IRQ_NO_NVIC", _check_can_irq_nvic)
    registry.register("E_CAN_RECONFIG_NO_DEINIT", _check_can_reconfig_no_deinit)
    registry.register("E_CAN_DEINIT_NO_CLK_OFF", _check_can_deinit_no_clk_off)
