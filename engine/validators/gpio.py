"""GPIO 校验器。"""
import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    make_deinit_clk_off_validator,
)

_gpio_clock_first = make_clock_first_validator(
    r"__HAL_RCC_GPIO[A-Z]_CLK_ENABLE\s*\(\)",
    r"\bHAL_GPIO_Init\s*\(",
    use_regex=True,
)


def _gpio_default_state(ctx: Any) -> bool:
    code = ctx.get("_code_artifact", "")
    return "BSRR" in code or "ODR" in code


def _gpio_no_register(ctx: Any) -> bool:
    violations = ctx.get("violation_list", [])
    return "E_GPIO_NO_REGISTER" not in violations


def _gpio_reconfig_deinit(ctx: Any) -> bool:
    """
    重配置检测：HAL_GPIO_Init 出现多次（重复配置）时必须先 DeInit。

    修复说明：原 make_reconfig_deinit_validator 把所有 GPIO 代码都要求
    HAL_GPIO_DeInit——首次初始化（MX_GPIO_Init 只调一次 Init）本就不需要
    DeInit，属误报。正确语义：只有"重复配置"（Init 调用 >1 次）才要求先 DeInit。
    """
    code = ctx.get("_code_artifact", "")
    init_count = len(re.findall(r"\bHAL_GPIO_Init\s*\(", code))
    if init_count <= 1:
        return True  # 首次配置，无需 DeInit
    return bool(re.search(r"\bHAL_GPIO_DeInit\s*\(", code))

_gpio_deinit_complete = make_deinit_clk_off_validator(
    r"__HAL_RCC_GPIO[A-Z]_CLK_DISABLE\s*\("
)


def _gpio_mode_mismatch(ctx: Any) -> bool:
    """检查 GPIO 模式配置是否一致：输出模式需要 Speed，输入模式不应配 Speed。

    修复（冒烟实证 R_GPIO_INIT_002 误报）：此前按"代码级"判断——
    代码里同时有输入结构（EXTI 中断）和输出结构（带 Speed）时误报；
    改为按 Init 结构分组判断，每个结构独立校验。
    """
    code = ctx.get("_code_artifact", "")
    if not code:
        return True
    # 按 Init 结构块切分（每块 = 一个 GPIO_InitTypeDef 的配置）
    blocks = re.split(r'GPIO_InitTypeDef\s+\w+\s*=\s*\{0\};', code)
    for block in blocks:
        has_output = bool(re.search(r'\bGPIO_MODE_OUTPUT', block))
        has_input = bool(re.search(r'\bGPIO_MODE_INPUT\b|\bGPIO_MODE_IT_|\bGPIO_MODE_EVT_', block))
        has_speed = bool(re.search(r'\bGPIO_SPEED_FREQ_', block))
        if has_input and has_speed:
            return False  # 输入模式不应配 Speed
        if has_output and not has_speed:
            return False  # 输出模式必须配 Speed
    return True


def _gpio_irq_pending(ctx: Any) -> bool:
    """检查中断服务函数中是否清除了 EXTI 挂起位。

    能力预判修复：has_clear 只认「显式清除挂起位」的宏/函数
    （__HAL_GPIO_EXTI_CLEAR_IT / HAL_GPIO_EXTI_ClearIT），不再把
    HAL_GPIO_EXTI_IRQHandler（仅分发回调、不清挂起位）误当清除。
    """
    code = ctx.get("_code_artifact", "")
    if not code:
        return True
    has_handler = re.search(r"EXTI\d+(_\d+)?_IRQHandler|HAL_GPIO_EXTI_IRQHandler", code)
    if not has_handler:
        return True
    has_clear = "__HAL_GPIO_EXTI_CLEAR_IT" in code or "HAL_GPIO_EXTI_ClearIT" in code
    return has_clear


def _gpio_irq_blocking(ctx: Any) -> bool:
    """检查 GPIO 中断服务函数中是否有阻塞调用（HAL_Delay 等）"""
    code = ctx.get("_code_artifact", "")
    if not code:
        return True
    has_handler = re.search(r"EXTI\d+(_\d+)?_IRQHandler\b", code)
    if not has_handler:
        return True
    # 提取 IRQHandler 函数体
    handler_match = re.search(r"void\s+\w+IRQHandler\s*\([^)]*\)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}", code, re.DOTALL)
    if not handler_match:
        return True
    body = handler_match.group(1)
    blocking = bool(re.search(r"HAL_Delay|while\s*\([^)]*\)\s*;|for\s*\([^;]*;[^;]*;[^)]*\)\s*;", body))
    return not blocking


def register(registry: ValidatorRegistry) -> None:
    """Register validators with the validator registry."""
    registry.register("E_GPIO_CLK_LATE", _gpio_clock_first)
    registry.register("W_GPIO_DEFAULT_UNSET", _gpio_default_state)
    registry.register("E_GPIO_NO_REGISTER", _gpio_no_register)
    registry.register("E_GPIO_RECONFIG_NO_DEINIT", _gpio_reconfig_deinit)
    registry.register("E_GPIO_DEINIT_INCOMPLETE", _gpio_deinit_complete)
    registry.register("E_GPIO_MODE_MISMATCH", _gpio_mode_mismatch)
    registry.register("E_GPIO_IRQ_PENDING", _gpio_irq_pending)
    registry.register("W_GPIO_IRQ_BLOCKING", _gpio_irq_blocking)
