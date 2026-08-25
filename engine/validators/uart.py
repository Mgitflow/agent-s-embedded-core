"""UART 校验器。"""
import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    make_deinit_clk_off_validator,
    make_reconfig_deinit_validator,
    strip_comments,
)

_uart_clock_first = make_clock_first_validator(
    r"__HAL_RCC_USART\d+_CLK_ENABLE\s*\(\)", "HAL_UART_"
)


def _uart_gpio_af(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'GPIO_Init\s*\(', code))


def _uart_baud(ctx: Any) -> bool:
    """检查波特率是否设置且为合理范围（1200-4608000）"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    m = re.search(r'\.BaudRate\s*=\s*(\d+)', code)
    if m:
        baud = int(m.group(1))
        return 1200 <= baud <= 4608000
    return False


def _uart_irq_nvic(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'NVIC_EnableIRQ\s*\(', code))


def _uart_irq_rxne(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'\bUART_IT_RXNE\b', code))


def _uart_irq_receive(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'\bHAL_UART_Receive(?:[_]IT)?\s*\(', code))


_uart_reconfig_deinit = make_reconfig_deinit_validator(r"\bHAL_UART_DeInit\s*\(")

_uart_deinit_clk_off = make_deinit_clk_off_validator(
    r"__HAL_RCC_USART\d+_CLK_DISABLE\s*\("
)


def register(registry: ValidatorRegistry) -> None:
    """Register validators with the validator registry."""
    registry.register("E_UART_CLK_LATE", _uart_clock_first)
    registry.register("E_UART_NO_GPIO_AF", _uart_gpio_af)
    registry.register("W_UART_BAUD_MISSING", _uart_baud)
    registry.register("E_UART_IRQ_NO_NVIC", _uart_irq_nvic)
    registry.register("E_UART_IRQ_NO_RXNE", _uart_irq_rxne)
    registry.register("W_UART_IRQ_NO_RECEIVE", _uart_irq_receive)
    registry.register("E_UART_RECONFIG_NO_DEINIT", _uart_reconfig_deinit)
    registry.register("E_UART_DEINIT_NO_CLK_OFF", _uart_deinit_clk_off)
