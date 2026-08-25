"""I2C 校验器。"""
import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    make_deinit_clk_off_validator,
    make_reconfig_deinit_validator,
    strip_comments,
)

_i2c_clock_first = make_clock_first_validator(
    r"__HAL_RCC_I2C\d+_CLK_ENABLE\s*\(\)", "HAL_I2C_"
)


def _i2c_gpio_af(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'GPIO_Init\s*\(', code))


def _i2c_speed(ctx: Any) -> bool:
    """检查 I2C 速度是否为有效值（100k/400k/1MHz）"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    m = re.search(r'\.ClockSpeed\s*=\s*(\d+)', code)
    if m:
        speed = int(m.group(1))
        return speed in (100000, 400000, 1000000)
    return False


def _i2c_irq_nvic(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'NVIC_EnableIRQ\s*\(', code))


def _i2c_irq_evt(ctx: Any) -> bool:
    code = strip_comments(ctx.get("_code_artifact", ""))
    return bool(re.search(r'\bI2C_IT_EVT\b', code))


_i2c_reconfig_deinit = make_reconfig_deinit_validator(r"\bHAL_I2C_DeInit\s*\(")

_i2c_deinit_clk_off = make_deinit_clk_off_validator(
    r"__HAL_RCC_I2C\d+_CLK_DISABLE\s*\("
)


def register(registry: ValidatorRegistry) -> None:
    """Register validators with the validator registry."""
    registry.register("E_I2C_CLK_LATE", _i2c_clock_first)
    registry.register("E_I2C_NO_GPIO_AF", _i2c_gpio_af)
    registry.register("W_I2C_SPEED_MISSING", _i2c_speed)
    registry.register("E_I2C_IRQ_NO_NVIC", _i2c_irq_nvic)
    registry.register("E_I2C_IRQ_NO_EVT", _i2c_irq_evt)
    registry.register("E_I2C_RECONFIG_NO_DEINIT", _i2c_reconfig_deinit)
    registry.register("E_I2C_DEINIT_NO_CLK_OFF", _i2c_deinit_clk_off)
