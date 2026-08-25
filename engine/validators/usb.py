"""USB 校验器：校验 PCD/HCD 初始化顺序与 Start 调用（3 条 MUST）。"""
from __future__ import annotations

import re
from typing import Any

from engine.validators.base import (
    ValidatorRegistry,
    make_clock_first_validator,
    strip_comments,
)

_check_usb_clk_late = make_clock_first_validator(
    r"__HAL_RCC_USB_CLK_ENABLE\s*\(",
    r"\bHAL_(?:PCD|HCD)_Init\s*\(",
    use_regex=True,
)


def _check_usb_init_present(ctx: dict[str, Any]) -> bool:
    """使能了 USB 时钟就必须有 HAL_PCD_Init / HAL_HCD_Init。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"__HAL_RCC_USB_CLK_ENABLE\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_(?:PCD|HCD)_Init\s*\(", code))


def _check_usb_start_present(ctx: dict[str, Any]) -> bool:
    """初始化了 USB 就必须有 HAL_PCD_Start / HAL_HCD_Start（否则不工作）。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"\bHAL_(?:PCD|HCD)_Init\s*\(", code):
        return True
    return bool(re.search(r"\bHAL_(?:PCD|HCD)_Start\s*\(", code))


# ── 参数级校验（2026-08-17 补：查"参数对不对"）──
_USB_EP_MAX = 7  # FS 设备 8 个端点（EP0..EP7）


def _check_usb_ep_valid(ctx: dict[str, Any]) -> bool:
    """USB 端点号必须 0..7，非法端点拦截。"""
    code = strip_comments(ctx.get("_code_artifact", ""))
    if not code or not re.search(r"HAL_PCD_EP_(Open|Close|Transmit|Receive)\s*\(", code):
        return True
    for m in re.finditer(r"\bPCD_EP_(\d+)\b", code):
        try:
            if not (0 <= int(m.group(1)) <= _USB_EP_MAX):
                return False
        except ValueError:
            continue
    return True


def register(registry: ValidatorRegistry) -> None:
    """Register USB validators with the validator registry."""
    registry.register("E_USB_CLK_LATE", _check_usb_clk_late)
    registry.register("E_USB_NO_INIT", _check_usb_init_present)
    registry.register("E_USB_NO_START", _check_usb_start_present)
    registry.register("E_USB_EP_INVALID", _check_usb_ep_valid)
