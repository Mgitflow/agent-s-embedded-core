"""工业级标杆契约：把 CubeMX 生成的工业级代码「固定结构」显式写成数据。

来源：STM32Cube_FW_F4_V1.28.3 官方 Templates（STM32F4-Discovery，F407VGT6），
已归档到 knowledge/template_forge/industrial_benchmark/f407_official/。

这个契约回答念安的核心问题：**工业级代码的「钉子孔」长什么样**——
HAL 引入 → 业务 .c → 时钟 → 重置 → 初始化 → 配置 → 按需时序。
工艺监测器据此校验生成的代码：每个孔是否钉对了钉子。

用途：
  1. 静态审查加孔：逐项校验生成 main.c 是否含这些固定结构
  2. 工业骨架更新依据：mx_skeleton 模板对齐本契约
"""

from __future__ import annotations

from typing import Any

# ────────────────────────── main.c 固定结构（按出现顺序） ──────────────────────────
# 每一项 = 一个「孔」，value 是必须出现的「钉子」（子串），缺失即工艺不合格。

MAIN_C_STRUCTURE: dict[str, list[str]] = {
    # 1. 头文件注释（@file/@brief 是 CubeMX 标准头部）
    "file_header": ["@file", "@brief"],
    # 2. HAL 引入（先标明 HAL 库引入）
    "hal_include": ["#include \"main.h\""],
    # 3. 私有区（typedef/define/macro/variables 四区齐全）
    "private_sections": [
        "Private typedef",
        "Private define",
        "Private macro",
        "Private variables",
    ],
    # 4. 函数原型声明（static 声明，工业级风格）
    "function_prototypes": [
        "SystemClock_Config",
        "Error_Handler",
    ],
    # 5. 主入口固定序列（顺序敏感）
    "main_sequence": [
        "int main(void)",
        "HAL_Init();",
        "SystemClock_Config();",
        "while (1)",
    ],
    # 6. 时钟配置（PLL 结构）
    "clock_config": [
        "RCC_OscInitTypeDef",
        "RCC_ClkInitTypeDef",
        "HAL_RCC_OscConfig",
        "HAL_RCC_ClockConfig",
        "Error_Handler();",
    ],
    # 7. 错误处理
    "error_handler": ["void Error_Handler(void)"],
}

# ────────────────────────── 时钟参数（工业标杆值，F407 168MHz） ──────────────────────────

F407_CLOCK_PARAMS: dict[str, str] = {
    "sysclk": "168000000",
    "hse": "8000000",
    "pll_m": "8",
    "pll_n": "336",
    "pll_p": "2",
    "pll_q": "7",
    "flash_latency": "5",
    "apb1_div": "4",
    "apb2_div": "2",
    "voltage_scale": "PWR_REGULATOR_VOLTAGE_SCALE1",
}

# ────────────────────────── 配套文件清单（完整工程该有的文件） ──────────────────────────
# key = 文件相对路径（相对工程根），value = 必须出现的锚点（子串）。
# 文件名随芯片系列前缀动态生成（2026-08-22 活接口化：不再写死 stm32f4xx）。


def project_file_anchors(chip: str | None = None) -> dict[str, list[str]]:
    """完整工程该有的文件 + 锚点（按芯片动态生成，文件名随系列前缀）。"""
    from infrastructure.chip_family import get_family
    from infrastructure.chip_gateway import gateway

    chip = chip or gateway.default_chip()
    prefix = gateway.hal_prefix(chip)
    startup = get_family(chip).startup_pattern
    return {
        "Core/Src/main.c": ["HAL_Init();", "SystemClock_Config();", "while (1)"],
        "Core/Inc/main.h": ["#ifndef", f'#include "{prefix}_hal.h"'],
        f"Core/Src/{prefix}_it.c": ["SysTick_Handler"],
        f"Core/Src/system_{prefix}.c": ["SystemInit"],
        f"Core/Src/{prefix}_hal_msp.c": ["HAL_MspInit"],
        startup: ["Reset_Handler"],
    }

# ────────────────────────── 工业骨架固定顺序（工艺链的「孔序」） ──────────────────────────
# 念安定调：HAL 引入 → 业务 .c → 时钟 → 重置 → 初始化 → 配置 → 按需时序。

INDUSTRIAL_ORDER: list[str] = [
    "hal_include",        # 先标明 HAL 库引入
    "business_logic",     # 业务层代码（功能 init/loop）
    "clock_config",       # 配置时钟
    "reset",              # 重置（HAL_Init 内部）
    "peripheral_init",    # 外设初始化
    "timing_logic",       # 按需时序逻辑（while(1) 内）
]


def check_structure(content: str, anchors: list[str]) -> tuple[bool, list[str]]:
    """校验一段代码是否含全部锚点。返回 (是否齐全, 缺失项列表)。"""
    missing = [a for a in anchors if a not in content]
    return (not missing), missing


def check_main_c(content: str) -> dict[str, Any]:
    """校验 main.c 是否含全部工业级固定结构。返回逐项结果。"""
    report: dict[str, Any] = {}
    for section, anchors in MAIN_C_STRUCTURE.items():
        ok, missing = check_structure(content, anchors)
        report[section] = {"ok": ok, "missing": missing}
    report["_all_ok"] = all(v["ok"] for v in report.values())
    return report
