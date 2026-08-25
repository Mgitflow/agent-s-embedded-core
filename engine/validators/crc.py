"""CRC 校验器：校验 CRC 初始化顺序与 Calculate/DeInit 收尾（4 条 MUST）。"""
from __future__ import annotations

import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    strip_comments,
)

_check_crc_clk_late = make_clock_first_validator(
    r"__HAL_RCC_CRC_CLK_ENABLE\s*\(",
    r"\bHAL_CRC_Init\s*\(",
    use_regex=True,
)


def _check_crc_init_present(ctx: dict[str, Any]) -> bool:
    """使能了 CRC 时钟就必须有 HAL_CRC_Init。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"__HAL_RCC_CRC_CLK_ENABLE\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_CRC_Init\s*\(", code))


def _check_crc_calculate_present(ctx: dict[str, Any]) -> bool:
    """初始化了 CRC 就必须有 HAL_CRC_Calculate（否则校验和算不出来）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_CRC_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_CRC_Calculate\s*\(", code))


def _check_crc_deinit_present(ctx: dict[str, Any]) -> bool:
    """初始化了 CRC 就必须有 HAL_CRC_DeInit 收尾。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_CRC_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_CRC_DeInit\s*\(", code))


def register(registry: ValidatorRegistry) -> None:
    """Register CRC validators with the validator registry."""
    registry.register("E_CRC_CLK_LATE", _check_crc_clk_late)
    registry.register("E_CRC_NO_INIT", _check_crc_init_present)
    registry.register("E_CRC_NO_CALCULATE", _check_crc_calculate_present)
    registry.register("E_CRC_NO_DEINIT", _check_crc_deinit_present)
