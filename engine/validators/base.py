"""校验器基础设施：ValidatorRegistry、注释剥离与通用校验函数工厂。"""
import re
from collections.abc import Callable
from typing import Any


def strip_comments(code: str) -> str:
    """移除 C 代码中的注释（// 和 /* */），避免校验器误匹配。"""
    # Remove /* ... */ blocks
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    # Remove // line comments
    code = re.sub(r"//[^\n]*", "", code)
    return code


def find_function_bodies(code: str) -> list[tuple[str, str]]:
    """提取顶层函数 (name, body)，用于判断喂狗是否位于中断回调内。

    2026-08-13 从 iwdg.py/wwdg.py 抽公共（两处原实现完全重复）。
    """
    bodies: list[tuple[str, str]] = []
    for match in re.finditer(r"(\w+)\s*\([^)]*\)\s*\{", code):
        name = match.group(1)
        body_start = match.end()
        depth = 1
        i = body_start
        while i < len(code) and depth > 0:
            if code[i] == "{":
                depth += 1
            elif code[i] == "}":
                depth -= 1
            i += 1
        bodies.append((name, code[body_start : i - 1]))
    return bodies


def _clean_pattern_name(pattern: str) -> str:
    """把正则模式转换成可用的函数名片段（只保留字母/数字/下划线）。"""
    return re.sub(r"[^a-zA-Z0-9_]+", "_", pattern).strip("_").lower()[:10]


class ValidatorRegistry:
    """校验器注册表：error_code → validator 函数"""

    def __init__(self) -> None:
        self._validators: dict[str, Callable[..., Any]] = {}

    def register(self, error_code: str, validator: Callable[..., Any]) -> None:
        self._validators[error_code] = validator

    def get(self, error_code: str) -> Callable[..., Any] | None:
        return self._validators.get(error_code)

    def has(self, error_code: str) -> bool:
        return error_code in self._validators


def make_clock_first_validator(
    clk_enable_pattern: str,
    hal_pattern: str,
    use_regex: bool = False,
) -> Callable[[dict[str, Any]], bool]:
    """工厂：生成「RCC 时钟使能必须在 HAL 外设初始化之前」校验器。

    Args:
        clk_enable_pattern: 匹配 ``__HAL_RCC_xxx_CLK_ENABLE()`` 的正则。
        hal_pattern: 匹配 HAL 外设初始化前缀/函数的正则或纯字符串。
        use_regex: 为 True 时用 ``re.search(hal_pattern)`` 定位初始化调用，
            否则用 ``code.find(hal_pattern)`` 定位前缀（兼容旧行为）。
    """

    def validator(ctx: dict[str, Any]) -> bool:
        code = strip_comments(ctx.get("_code_artifact", ""))
        clk_m = re.search(clk_enable_pattern, code)
        if not clk_m:
            return True  # 无时钟 → 不判定乱序（「缺时钟」是 CLK_MISSING 的职责，非 CLK_LATE）

        if use_regex:
            hal_m = re.search(hal_pattern, code)
            if not hal_m:
                return True
            return clk_m.start() < hal_m.start()

        hal_pos = code.find(hal_pattern)
        if hal_pos == -1:
            return True
        return clk_m.start() < hal_pos

    validator.__name__ = f"_clock_first_{_clean_pattern_name(hal_pattern)}"
    return validator


def make_deinit_clk_off_validator(clk_disable_pattern: str) -> Callable[[dict[str, Any]], bool]:
    """工厂：生成「DeInit 后必须关闭外设时钟」校验器。"""

    def validator(ctx: dict[str, Any]) -> bool:
        code = strip_comments(ctx.get("_code_artifact", ""))
        return bool(re.search(clk_disable_pattern, code))

    validator.__name__ = f"_deinit_clk_off_{_clean_pattern_name(clk_disable_pattern)}"
    return validator


def make_reconfig_deinit_validator(deinit_pattern: str) -> Callable[[dict[str, Any]], bool]:
    """工厂：生成「重新配置前必须 DeInit」校验器。"""

    def validator(ctx: dict[str, Any]) -> bool:
        code = strip_comments(ctx.get("_code_artifact", ""))
        return bool(re.search(deinit_pattern, code))

    validator.__name__ = f"_reconfig_deinit_{_clean_pattern_name(deinit_pattern)}"
    return validator
