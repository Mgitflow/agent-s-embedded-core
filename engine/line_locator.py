"""违规行号定位器：把未通过的校验规则定位到精确代码行，输出行号+该行代码作为修正锚点；匹配不到则不伪造行号。"""
from __future__ import annotations

import re
from typing import Any

# ── 精确码 → 定位正则（参数类：违规的是具体赋值行）──
_PARAM_LOCATORS: dict[str, str] = {
    "E_PARAM_TIM_PRESCALER_RANGE": r"(?:htim\d*\.Init\.)?Prescaler\s*=\s*\d+",
    "E_PARAM_TIM_PERIOD_RANGE": r"(?:htim\d*\.Init\.)?Period\s*=\s*\d+",
    "E_PARAM_TIM_PULSE_RANGE": r"(?:htim\d*\.)?Pulse\s*=\s*\d+",
    "E_PARAM_GPIO_PIN_VALID": r"GPIO_PIN_\d+\b",
    "E_PARAM_UART_BAUD_VALID": r"(?:huart\d*\.Init\.)?BaudRate\s*=\s*\d+",
    "E_PARAM_ADC_CHANNEL_VALID": r"ADC_CHANNEL_\d+\b",
    "E_IWDG_RELOAD_RANGE": r"Reload\s*=\s*\d+",
}

# ── 前缀族 → 定位正则（违规"病灶"所在处）──
_FAMILY_LOCATORS: list[tuple[str, str]] = [
    ("_CLK_LATE", r"\bHAL_\w+_Init\s*\("),            # Init 先于 CLK → 定位 Init 行
    ("_NO_INIT", r"__HAL_RCC_\w+_CLK_ENABLE\s*\("),   # 使能了却没 Init → 定位使能行
    ("_NO_DEINIT", r"\bHAL_\w+_Init\s*\("),
    ("_RECONFIG_NO_DEINIT", r"\bHAL_\w+_Init\s*\("),
    ("_NOT_STARTED", r"\bHAL_\w+_Init\s*\("),
    ("_NO_FILTER", r"\bHAL_\w+_Init\s*\("),
    ("_IRQ_NO_NVIC", r"\bHAL_\w+_Activate\w*\s*\("),
    ("_NO_CALCULATE", r"\bHAL_CRC_Init\s*\("),
    ("_NO_GENERATE", r"\bHAL_RNG_Init\s*\("),
    ("_NO_READ", r"\bHAL_SD_Init\s*\("),
    ("_NO_WRITE", r"\bHAL_SD_Init\s*\("),
    ("_REFRESH_IN_ISR", r"(?:IRQHandler|Callback)"),
    ("_DOUBLE_INIT", r"\bHAL_\w+_Init\s*\("),
    ("_DEINIT_NO_CLK_OFF", r"\bHAL_\w+_DeInit\s*\("),
    ("_DEINIT", r"\bHAL_\w+_Init\s*\("),
    ("_NO_", r"\bHAL_\w+_Init\s*\("),                  # 兜底：缺调用类 → 最近 Init
]

# 兜底正则：任何 HAL 调用（找不到更精确的用第一个）
_FALLBACK = r"\bHAL_[A-Z]\w*\s*\("


def _locate_line(code: str, pattern: str) -> tuple[int | None, str]:
    """在代码中定位模式所在行（1-based），返回 (行号, 该行代码)。"""
    m = re.search(pattern, code)
    if not m:
        return None, ""
    line_no = code.count("\n", 0, m.start()) + 1
    lines = code.splitlines()
    code_line = lines[line_no - 1].strip() if line_no <= len(lines) else ""
    return line_no, code_line


def _locate_by_code(error_code: str, code: str) -> tuple[int | None, str]:
    """按 error_code 定位（精确码 → 前缀族 → 兜底）。"""
    if error_code in _PARAM_LOCATORS:
        line, text = _locate_line(code, _PARAM_LOCATORS[error_code])
        if line:
            return line, text
    for suffix, pattern in _FAMILY_LOCATORS:
        if error_code.endswith(suffix):
            line, text = _locate_line(code, pattern)
            if line:
                return line, text
    # 最终兜底：第一个 HAL 调用
    line, text = _locate_line(code, _FALLBACK)
    return line, text


def locate_violations(code: str, failures: list[Any]) -> list[dict[str, Any]]:
    """批量定位未通过规则 → [{error_code, line, code_line}]。

    failures 兼容 RuleResult 对象（getattr）或 dict（get）。
    """
    out: list[dict[str, Any]] = []
    for f in failures:
        if isinstance(f, dict):
            ec = str(f.get("error_code") or f.get("rule_id") or "")
        else:
            ec = str(getattr(f, "error_code", "") or getattr(f, "rule_id", ""))
        if not ec:
            continue
        line, code_line = _locate_by_code(ec, code)
        out.append({"error_code": ec, "line": line, "code_line": code_line})
    return out


__all__ = ["locate_violations", "_locate_by_code"]
