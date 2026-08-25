"""SDIO 校验器：校验 SD 初始化顺序及 ReadBlocks/WriteBlocks/DeInit 收尾（5 条 MUST）。"""
from __future__ import annotations

import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    strip_comments,
)

_check_sdio_clk_late = make_clock_first_validator(
    r"__HAL_RCC_SDIO_CLK_ENABLE\s*\(",
    r"\bHAL_SD_Init\s*\(",
    use_regex=True,
)

def _check_sdio_init_present(ctx: dict[str, Any]) -> bool:
    """使能了 SDIO 时钟就必须有 HAL_SD_Init。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"__HAL_RCC_SDIO_CLK_ENABLE\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_SD_Init\s*\(", code))

def _check_sdio_read_present(ctx: dict[str, Any]) -> bool:
    """初始化了 SD 卡就必须有 HAL_SD_ReadBlocks。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_SD_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_SD_ReadBlocks\s*\(", code))

def _check_sdio_write_present(ctx: dict[str, Any]) -> bool:
    """初始化了 SD 卡就必须有 HAL_SD_WriteBlocks。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_SD_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_SD_WriteBlocks\s*\(", code))

def _check_sdio_deinit_present(ctx: dict[str, Any]) -> bool:
    """初始化了 SD 卡就必须有 HAL_SD_DeInit 收尾。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_SD_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_SD_DeInit\s*\(", code))


def register(registry: ValidatorRegistry) -> None:
    """Register SDIO validators with the validator registry."""
    registry.register("E_SDIO_CLK_LATE", _check_sdio_clk_late)
    registry.register("E_SDIO_NO_INIT", _check_sdio_init_present)
    registry.register("E_SDIO_NO_READ", _check_sdio_read_present)
    registry.register("E_SDIO_NO_WRITE", _check_sdio_write_present)
    registry.register("E_SDIO_NO_DEINIT", _check_sdio_deinit_present)
