"""RTC 校验器。"""
import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    make_deinit_clk_off_validator,
    make_reconfig_deinit_validator,
    strip_comments,
)

_check_rtc_clk_late = make_clock_first_validator(
    r"__HAL_RCC_RTC_ENABLE\s*\(",
    r"\bHAL_RTC_Init\s*\(",
    use_regex=True,
)

_check_rtc_reconfig_no_deinit = make_reconfig_deinit_validator(r"\bHAL_RTC_DeInit\s*\(")

_check_rtc_deinit_no_clk_off = make_deinit_clk_off_validator(r"__HAL_RCC_RTC_DISABLE\s*\(")

def _check_rtc_time_set(ctx: dict[str, Any]) -> bool:
    """检查是否设置了 RTC 时间（上下文化：无 RTC 初始化则放行）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    if not re.search(r"\bHAL_RTC_Init\s*\(", code):
        return True  # 无 RTC 外设不要求 SetTime
    return bool(re.search(r"\bHAL_RTC_SetTime\s*\(", code))

def _check_rtc_date_set(ctx: dict[str, Any]) -> bool:
    """检查是否设置了 RTC 日期（上下文化：无 RTC 初始化则放行）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    if not re.search(r"\bHAL_RTC_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_RTC_SetDate\s*\(", code))

def _check_rtc_alarm_nvic(ctx: dict[str, Any]) -> bool:
    """如果使用了 RTC 闹钟中断，则必须配置 NVIC。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    if not re.search(r"\bHAL_RTC_SetAlarm_IT\s*\(", code):
        return True
    has_priority = bool(re.search(r"\bHAL_NVIC_SetPriority\s*\(", code))
    has_enable = bool(re.search(r"\bHAL_NVIC_EnableIRQ\s*\(", code))
    return has_priority and has_enable


def register(registry: ValidatorRegistry) -> None:
    """Register RTC validators with the validator registry."""
    registry.register("E_RTC_CLK_LATE", _check_rtc_clk_late)
    registry.register("E_RTC_NO_TIME_SET", _check_rtc_time_set)
    registry.register("E_RTC_NO_DATE_SET", _check_rtc_date_set)
    registry.register("E_RTC_ALARM_NO_NVIC", _check_rtc_alarm_nvic)
    registry.register("E_RTC_RECONFIG_NO_DEINIT", _check_rtc_reconfig_no_deinit)
    registry.register("E_RTC_DEINIT_NO_CLK_OFF", _check_rtc_deinit_no_clk_off)
