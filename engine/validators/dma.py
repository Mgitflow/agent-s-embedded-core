"""DMA 校验器：正面引导优先、验证器仅兜底，只覆盖 5 条 MUST 级硬规则作最后防线。"""
import logging
import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    strip_comments,
)

logger = logging.getLogger(__name__)


def register(registry: ValidatorRegistry) -> None:
    """Register validators with the validator registry."""
    registry.register("E_DMA_CLK_LATE", _check_dma_clk_late)
    registry.register("E_DMA_NO_LINKDMA", _check_dma_linkdma)
    registry.register("E_DMA_ALIGN_MISMATCH", _check_dma_align)
    registry.register("E_DMA_RECONFIG_NO_DEINIT", _check_dma_reconfig_no_deinit)
    registry.register("E_DMA_IRQ_NO_NVIC", _check_dma_irq_nvic)
    logger.info("DMA validators registered (5 MUST rules)")


_check_dma_clk_late = make_clock_first_validator(
    r"__HAL_RCC_DMA\d_CLK_ENABLE\s*\(",
    r"\bHAL_DMA_Init\s*\(",
    use_regex=True,
)


def _check_dma_linkdma(ctx: dict[str, Any]) -> bool:
    """检查是否使用 __HAL_LINKDMA 绑定 DMA 句柄到外设"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True
    # DMA 初始化了但没 __HAL_LINKDMA → 外设不知道 DMA 句柄
    has_dma_init = bool(re.search(r'\bHAL_DMA_Init\s*\(', code))
    has_linkdma = bool(re.search(r'\b__HAL_LINKDMA\s*\(', code))
    if has_dma_init and not has_linkdma:
        return False
    return True


def _check_dma_align(ctx: dict[str, Any]) -> bool:
    """检查 DMA 数据对齐是否与外设数据宽度一致

    常见错误：
    - ADC 12bit 用了 BYTE 对齐 → 数据截断
    - Mem2Mem 用了 BYTE 对齐 → 效率极低
    """
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True

    # 检测 ADC 场景：HalfWord 对齐是必须的
    has_adc = bool(re.search(r'\bHAL_ADC_', code))
    if has_adc:
        align_match = re.search(
            r'(?:Periph|Mem)DataAlignment\s*=\s*(DMA_PDATAALIGN_\w+)', code
        )
        if align_match and align_match.group(1) == "DMA_PDATAALIGN_BYTE":
            return False

    return True


def _check_dma_reconfig_no_deinit(ctx: dict[str, Any]) -> bool:
    """检查重配置前是否调用了 HAL_DMA_DeInit"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True

    # 统计 HAL_DMA_Init 调用次数
    init_count = len(re.findall(r'\bHAL_DMA_Init\s*\(', code))
    if init_count <= 1:
        return True  # 只有一次 Init，不是重配置

    # 有多次 Init，必须有一次 DeInit 在两次 Init 之间
    deinit_matches = list(re.finditer(r'\bHAL_DMA_DeInit\s*\(', code))

    # 简单检查：DeInit 数量 >= Init 数量 - 1
    if len(deinit_matches) < init_count - 1:
        return False
    return True


def _check_dma_irq_nvic(ctx: dict[str, Any]) -> bool:
    """检查 DMA 中断场景是否有完整 NVIC 配置

    DMA 中断需要：SetPriority + EnableIRQ（DMA IRQ + 对应外设 IRQ 都需要）
    """
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code:
        return True

    # 如果代码中没有使能 DMA 中断相关的模式，则跳过检查
    has_dma_irq_mode = bool(re.search(r'\bDMA_IT_\w+\b', code))
    has_start_it = bool(re.search(r'\bHAL_\w+_Start_DMA\b', code))
    has_transmit_dma = bool(re.search(r'\bHAL_\w+_Transmit_DMA\b', code))
    has_receive_dma = bool(re.search(r'\bHAL_\w+_Receive_DMA\b', code))

    if not (has_dma_irq_mode or has_start_it or has_transmit_dma or has_receive_dma):
        return True  # 非 DMA 中断场景，跳过

    # DMA 中断场景必须有 NVIC 配置
    has_priority = bool(re.search(r'\bHAL_NVIC_SetPriority\s*\(', code))
    has_enable = bool(re.search(r'\bHAL_NVIC_EnableIRQ\s*\(', code))

    if not (has_priority and has_enable):
        return False

    return True
