"""ADC 校验器。"""
import logging
import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    make_deinit_clk_off_validator,
    make_reconfig_deinit_validator,
    strip_comments,
)

logger = logging.getLogger(__name__)


def register(registry: ValidatorRegistry) -> None:
    """Register validators with the validator registry."""
    registry.register("E_ADC_CLK_LATE", _check_adc_clk_late)
    registry.register("E_ADC_NO_ANALOG_GPIO", _check_adc_gpio_analog)
    registry.register("E_ADC_IRQ_NO_NVIC", _check_adc_irq_nvic)
    registry.register("E_ADC_IRQ_NOT_STARTED", _check_adc_start_it)
    registry.register("E_ADC_RECONFIG_NO_DEINIT", _check_adc_reconfig_no_deinit)
    registry.register("E_ADC_DEINIT_NO_CLK_OFF", _check_adc_deinit_no_clk_off)
    logger.info("ADC validators registered (6)")


_check_adc_clk_late = make_clock_first_validator(
    r"__HAL_RCC_ADC\d+_CLK_ENABLE\s*\(",
    r"\bHAL_ADC_Init\s*\(",
    use_regex=True,
)


def _check_adc_gpio_analog(ctx: dict[str, Any]) -> bool:
    """检查 GPIO 是否配置为模拟模式（2026-08-13 上下文化：无 ADC 初始化则放行）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    # 修复：此前无条件要求 GPIO_MODE_ANALOG，纯 GPIO 工程被误伤（冒烟实证 R_ADC_INIT_002）
    if not re.search(r'\bHAL_ADC_Init\s*\(', code):
        return True
    return bool(re.search(r'\bGPIO_MODE_ANALOG\b', code))


def _check_adc_irq_nvic(ctx: dict[str, Any]) -> bool:
    """检查中断场景是否有完整 NVIC 配置（SetPriority 和 EnableIRQ 必须同时存在）"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    has_priority = bool(re.search(r'\bHAL_NVIC_SetPriority\s*\(', code))
    has_enable = bool(re.search(r'\bHAL_NVIC_EnableIRQ\s*\(', code))
    return has_priority and has_enable


def _check_adc_start_it(ctx: dict[str, Any]) -> bool:
    """检查是否启动了 ADC 中断模式"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    return bool(re.search(r'\bHAL_ADC_Start_IT\s*\(', code))


_check_adc_reconfig_no_deinit = make_reconfig_deinit_validator(r"\bHAL_ADC_DeInit\s*\(")

_check_adc_deinit_no_clk_off = make_deinit_clk_off_validator(
    r"__HAL_RCC_ADC\d+_CLK_DISABLE\s*\("
)
