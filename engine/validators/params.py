"""参数值合法性硬规则查表：补上寄存器位宽/枚举范围类校验（TIM/GPIO/UART/ADC），确定性优先、只拦明显越界、不走 LLM。"""
from __future__ import annotations

import re
from typing import Any

from engine.validators.base import ValidatorRegistry, strip_comments

# ── 参数位宽/范围表（硬规则，来源：寄存器位宽）──
_TIM_16BIT_MAX = 65535  # 16 位计数器/预分频/比较值
_GPIO_PIN_MAX = 15      # 端口 16 引脚（PIN_0..PIN_15）
_ADC_CH_MAX = 15        # 12 位 ADC 共 16 通道
_UART_BAUD_MIN = 1200
_UART_BAUD_MAX = 4_000_000
# 标准波特率集合（超出集合但在范围内 → 警告级由上层定；这里只拦范围）
_UART_STANDARD_BAUDS = {
    1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200,
    230400, 460800, 921600, 1500000, 2000000, 3000000, 4000000,
}

# ── 提取模式（hInit.Init.X = N 或 X = N）──
_TIM_PRESCALER = r"(?:htim\d*\.Init\.)?Prescaler\s*=\s*(\d+)"
_TIM_PERIOD = r"(?:htim\d*\.Init\.)?Period\s*=\s*(\d+)"
_TIM_PULSE = r"(?:htim\d*\.)?Pulse\s*=\s*(\d+)"
_GPIO_PIN = r"GPIO_PIN_(\d+)\b"
_UART_BAUD = r"(?:huart\d*\.Init\.)?BaudRate\s*=\s*(\d+)"
_ADC_CHANNEL = r"ADC_CHANNEL_(\d+)\b"


def _check_tim_prescaler_range(ctx: dict[str, Any]) -> bool:
    """Prescaler 必须 ≤ 65535（16 位预分频）。"""
    return _all_in_range(ctx, _TIM_PRESCALER, 0, _TIM_16BIT_MAX, "TIM Prescaler")


def _check_tim_period_range(ctx: dict[str, Any]) -> bool:
    """Period 必须 ≤ 65535（16 位自动重装载）。"""
    return _all_in_range(ctx, _TIM_PERIOD, 0, _TIM_16BIT_MAX, "TIM Period")


def _check_tim_pulse_range(ctx: dict[str, Any]) -> bool:
    """Pulse（比较值）必须 ≤ 65535（16 位）。"""
    return _all_in_range(ctx, _TIM_PULSE, 0, _TIM_16BIT_MAX, "TIM Pulse")


def _check_gpio_pin_valid(ctx: dict[str, Any]) -> bool:
    """GPIO_PIN_x 的 x ∈ 0..15。"""
    return _all_in_range(ctx, _GPIO_PIN, 0, _GPIO_PIN_MAX, "GPIO_PIN")


def _check_uart_baud_valid(ctx: dict[str, Any]) -> bool:
    """BaudRate ∈ 1200..4000000（标准波特率集合之外但在范围内→提示由上层定）。"""
    return _all_in_range(ctx, _UART_BAUD, _UART_BAUD_MIN, _UART_BAUD_MAX, "UART BaudRate")


def _check_adc_channel_valid(ctx: dict[str, Any]) -> bool:
    """ADC_CHANNEL_x 的 x ∈ 0..15。"""
    return _all_in_range(ctx, _ADC_CHANNEL, 0, _ADC_CH_MAX, "ADC_CHANNEL")


def _all_in_range(ctx: dict[str, Any], pattern: str, lo: int, hi: int, label: str) -> bool:
    """提取全部数值并校验范围；取不到值/未出现 → 通过（低误报）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    for raw in re.findall(pattern, code):
        try:
            val = int(raw)
        except ValueError:
            continue
        if not (lo <= val <= hi):
            return False
    return True


def register(registry: ValidatorRegistry) -> None:
    """Register parameter-range validators（E_PARAM_* 前缀）。"""
    registry.register("E_PARAM_TIM_PRESCALER_RANGE", _check_tim_prescaler_range)
    registry.register("E_PARAM_TIM_PERIOD_RANGE", _check_tim_period_range)
    registry.register("E_PARAM_TIM_PULSE_RANGE", _check_tim_pulse_range)
    registry.register("E_PARAM_GPIO_PIN_VALID", _check_gpio_pin_valid)
    registry.register("E_PARAM_UART_BAUD_VALID", _check_uart_baud_valid)
    registry.register("E_PARAM_ADC_CHANNEL_VALID", _check_adc_channel_valid)
