"""TIM 校验器。"""
import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    make_reconfig_deinit_validator,
    strip_comments,
)


def _tim_pwm_started(ctx: Any) -> bool:
    """检查是否调用了 PWM 启动函数（排除变量名误匹配）"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'\bHAL_TIM_PWM_Start\b', code))


def _tim_pwm_channel(ctx: Any) -> bool:
    """检查 PWM 通道配置函数调用"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'\bHAL_TIM_PWM_ConfigChannel\s*\(', code))


_tim_reconfig_deinit = make_reconfig_deinit_validator(
    r"\bHAL_TIM_DeInit\s*\(|\bHAL_TIM_Base_DeInit\s*\("
)


def _tim_irq_nvic(ctx: Any) -> bool:
    """检查是否配置了 NVIC 中断使能（确认是函数调用）"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'NVIC_EnableIRQ\s*\(', code))


def _tim_irq_clear(ctx: Any) -> bool:
    """检查中断服务函数中是否清除标志位"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'__HAL_TIM_CLEAR_FLAG\s*\(', code) or
                re.search(r'__HAL_TIM_CLEAR_IT\s*\(', code) or
                re.search(r'\bTIM_SR\b', code))


_tim_clock_first = make_clock_first_validator(
    r"__HAL_RCC_TIM\d+_CLK_ENABLE\s*\(\)", "HAL_TIM_"
)


def _tim_period_nonzero(ctx: Any) -> bool:
    """检查 Period (ARR) 是否设置且不为零（2026-08-13 上下文化：无 TIM 初始化则放行）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not re.search(r"\bHAL_TIM_\w+_Init\s*\(|\bhtim\d", code):
        return True  # 无 TIM 外设（无 Init 调用且无句柄）不要求 Period
    m = re.search(r'\.Period\s*=\s*(\d+)', code)
    if m:
        return int(m.group(1)) > 0
    return "Period" in code


def _tim_psc_zero(ctx: Any) -> bool:
    """检查预分频器是否设为零（零意味着不分频，需确认是否是预期值）"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    m = re.search(r"\.Prescaler\s*=\s*(-?\d+)", code)
    if m and m.group(1) == "0":
        return False
    return True


def _tim_pwm_pulse_large(ctx: Any) -> bool:
    """检查 PWM 脉冲值（CCR）是否超过周期值（ARR）"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    period_m = re.search(r"\.Period\s*=\s*(\d+)", code)
    pulse_m = re.search(r"\.Pulse\s*=\s*(\d+)", code)
    if period_m and pulse_m:
        period = int(period_m.group(1))
        pulse = int(pulse_m.group(1))
        if pulse >= period:
            return False
    return True


def _tim_irq_blocking(ctx: Any) -> bool:
    """检查 TIM 中断服务函数中是否有阻塞调用"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    has_handler = re.search(r"TIM\d+_IRQHandler\b", code)
    if not has_handler:
        return True
    handler_match = re.search(r"void\s+\w+IRQHandler\s*\([^)]*\)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}", code, re.DOTALL)
    if not handler_match:
        return True
    body = handler_match.group(1)
    blocking = bool(re.search(r"HAL_Delay\b", body))
    return not blocking


def register(registry: ValidatorRegistry) -> None:
    """Register validators with the validator registry."""
    registry.register("E_TIM_PWM_NOT_STARTED", _tim_pwm_started)
    registry.register("E_TIM_PWM_NO_CHANNEL", _tim_pwm_channel)
    registry.register("E_TIM_RECONFIG_NO_DEINIT", _tim_reconfig_deinit)
    registry.register("E_TIM_IRQ_NO_NVIC", _tim_irq_nvic)
    registry.register("E_TIM_IRQ_NO_CLEAR", _tim_irq_clear)
    registry.register("E_TIM_CLK_LATE", _tim_clock_first)
    registry.register("E_TIM_PERIOD_ZERO", _tim_period_nonzero)
    registry.register("W_TIM_PSC_ZERO", _tim_psc_zero)
    registry.register("E_TIM_PWM_PULSE_LARGE", _tim_pwm_pulse_large)
    registry.register("W_TIM_IRQ_BLOCKING", _tim_irq_blocking)
