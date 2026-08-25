"""RNG 校验器：校验 RNG 初始化顺序与 Generate/DeInit 收尾（4 条 MUST）。"""
from __future__ import annotations

import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    strip_comments,
)

_check_rng_clk_late = make_clock_first_validator(
    r"__HAL_RCC_RNG_CLK_ENABLE\s*\(",
    r"\bHAL_RNG_Init\s*\(",
    use_regex=True,
)

def _check_rng_init_present(ctx: dict[str, Any]) -> bool:
    """使能了 RNG 时钟就必须有 HAL_RNG_Init。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"__HAL_RCC_RNG_CLK_ENABLE\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_RNG_Init\s*\(", code))

def _check_rng_generate_present(ctx: dict[str, Any]) -> bool:
    """初始化了 RNG 就必须有 HAL_RNG_GenerateRandomNumber（否则随机数取不到）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_RNG_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_RNG_GenerateRandomNumber\s*\(", code))

def _check_rng_deinit_present(ctx: dict[str, Any]) -> bool:
    """初始化了 RNG 就必须有 HAL_RNG_DeInit 收尾。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_RNG_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_RNG_DeInit\s*\(", code))


def register(registry: ValidatorRegistry) -> None:
    """Register RNG validators with the validator registry."""
    registry.register("E_RNG_CLK_LATE", _check_rng_clk_late)
    registry.register("E_RNG_NO_INIT", _check_rng_init_present)
    registry.register("E_RNG_NO_GENERATE", _check_rng_generate_present)
    registry.register("E_RNG_NO_DEINIT", _check_rng_deinit_present)
