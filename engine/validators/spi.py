"""SPI 校验器。"""
import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    make_deinit_clk_off_validator,
    make_reconfig_deinit_validator,
    strip_comments,
)

_spi_clock_first = make_clock_first_validator(
    r"__HAL_RCC_SPI\d+_CLK_ENABLE\s*\(\)", "HAL_SPI_"
)


def _spi_gpio_af(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'GPIO_Init\s*\(', code))


def _spi_mode(ctx: Any) -> bool:
    """检查 SPI 模式是否设置（CPOL/CPHA 或 SPI_MODE）"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'\bSPI_MODE_|\bCLKPolarity|\bCLKPhase', code))


def _spi_irq_nvic(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'NVIC_EnableIRQ\s*\(', code))


def _spi_irq_rxne(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'\bSPI_IT_RXNE\b', code))


_spi_reconfig_deinit = make_reconfig_deinit_validator(r"\bHAL_SPI_DeInit\s*\(")

_spi_deinit_clk_off = make_deinit_clk_off_validator(
    r"__HAL_RCC_SPI\d+_CLK_DISABLE\s*\("
)


def register(registry: ValidatorRegistry) -> None:
    """Register validators with the validator registry."""
    registry.register("E_SPI_CLK_LATE", _spi_clock_first)
    registry.register("E_SPI_NO_GPIO_AF", _spi_gpio_af)
    registry.register("W_SPI_MODE_MISSING", _spi_mode)
    registry.register("E_SPI_IRQ_NO_NVIC", _spi_irq_nvic)
    registry.register("E_SPI_IRQ_NO_RXNE", _spi_irq_rxne)
    registry.register("E_SPI_RECONFIG_NO_DEINIT", _spi_reconfig_deinit)
    registry.register("E_SPI_DEINIT_NO_CLK_OFF", _spi_deinit_clk_off)
