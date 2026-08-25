"""ETH 校验器：校验 ETH 初始化顺序与 MAC 配置获取（3 条 MUST）。"""
from __future__ import annotations

import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    strip_comments,
)

_check_eth_clk_late = make_clock_first_validator(
    r"__HAL_RCC_ETH_CLK_ENABLE\s*\(",
    r"\bHAL_ETH_Init\s*\(",
    use_regex=True,
)


def _check_eth_init_present(ctx: dict[str, Any]) -> bool:
    """使能了 ETH 时钟就必须有 HAL_ETH_Init。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"__HAL_RCC_ETH_CLK_ENABLE\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_ETH_Init\s*\(", code))


def _check_eth_maccfg_present(ctx: dict[str, Any]) -> bool:
    """初始化了 ETH 就必须有 MAC 配置（HAL_ETH_GetMACConfig/SetMACConfig）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_ETH_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_ETH_(?:Get|Set)MACConfig\s*\(", code))


# ── 参数级校验（2026-08-17 补：查"参数对不对"）──
# 标准速度/双工枚举（来源：STM32 HAL eth.h）
_ETH_SPEEDS = {"ETH_SPEED_10M", "ETH_SPEED_100M"}
_ETH_DUPLEX = {"ETH_MODE_FULLDUPLEX", "ETH_MODE_HALFDUPLEX"}


def _check_eth_speed_valid(ctx: dict[str, Any]) -> bool:
    """ETH 速度必须是 ETH_SPEED_10M/100M，非法速度拦截。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"HAL_ETH_Init\s*\(", code):
        return True
    return all(m.group(1) in _ETH_SPEEDS for m in re.finditer(r"\b(ETH_SPEED_\w+)\b", code))


def _check_eth_duplex_valid(ctx: dict[str, Any]) -> bool:
    """ETH 双工必须是 ETH_MODE_FULLDUPLEX/HALFDUPLEX，非法（含非标准变体 ETH_FULLDUPLEX_MODE）拦截。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"HAL_ETH_Init\s*\(", code):
        return True
    # 标准双工常量
    for m in re.finditer(r"\b(ETH_MODE_\w+)\b", code):
        if m.group(1) not in _ETH_DUPLEX:
            return False
    # 非标准变体（template 曾误用 ETH_FULLDUPLEX_MODE，非 HAL 官方名）
    if re.search(r"\bETH_(?:FULL|HALF)DUPLEX_MODE\b", code):
        return False
    return True


def register(registry: ValidatorRegistry) -> None:
    """Register ETH validators with the validator registry."""
    registry.register("E_ETH_CLK_LATE", _check_eth_clk_late)
    registry.register("E_ETH_NO_INIT", _check_eth_init_present)
    registry.register("E_ETH_NO_MACCFG", _check_eth_maccfg_present)
    registry.register("E_ETH_SPEED_INVALID", _check_eth_speed_valid)
    registry.register("E_ETH_DUPLEX_INVALID", _check_eth_duplex_valid)
