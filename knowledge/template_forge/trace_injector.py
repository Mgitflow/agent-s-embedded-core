"""探针注入器：生成代码时可选埋 AS_PROBE（带芯片手册真值预期值）。

念安 2026-08-23「生成代码 → 编译 → 预值指定位置 → 回传」的最后一公里：
把 as_trace 探针（AS_PROBE 宏，板内对账）埋进生成的 main.c，预期值来自芯片手册真值
（probes.expectations.build_expectations）。默认关闭（enable_trace=False），
开了才注入；release 不定义 AS_TRACE_ENABLE 时 AS_PROBE 展开成空、零开销。

探针埋点（念安「关键节点，定位很精准」）：
  - estack        读链接脚本栈顶符号 _estack，预期 = 手册真值（如 0x20020000）
  - flash_base    读 CMSIS 宏 FLASH_BASE
  - ram_base      读 CMSIS 宏 SRAM_BASE
  - peripheral_base 读 CMSIS 宏 PERIPH_BASE

这些能抓「内存映射算错」——尤其念安举例的「128K SRAM + 64K CCM 写成连续 192K」
（链接脚本算出的 _estack 会偏到 0x20030000，跟手册真值 0x20020000 对不上，板内对账回传偏差）。

纯函数：不 import 主项目装配逻辑，只读预期值（由调用方传入），保持可独立测试。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# as_trace.h/.c 素材目录（串口车间探针子集）
_AS_TRACE_DIR = Path(__file__).resolve().parents[2] / "serial_workshop"

# 探针点 → 实际值读法（C 表达式：链接脚本符号 / CMSIS 宏）
_PROBE_READS: dict[str, str] = {
    "estack": "(uint32_t)&_estack",
    "flash_base": "(uint32_t)FLASH_BASE",
    "ram_base": "(uint32_t)SRAM_BASE",
    "peripheral_base": "(uint32_t)PERIPH_BASE",
}


def build_init_block(chip: str = "", fw: str = "") -> str:
    """生成 as_trace_init + ID 自报块（放 main 函数最开头、HAL_Init 之前）。

    先 init 再自报，保证后续 TR 埋点（as_trace_report）都能入缓冲。
    """
    lines = ["  as_trace_init(as_trace_uart_send, HAL_GetTick);"]
    if chip:
        lines.append(f'  as_trace_report_id("{chip}", "{fw}");')
    return "\n".join(lines)


def build_probe_block(expectations: Any) -> str:
    """从预期值表生成 AS_PROBE 对账块（放所有驱动初始化之后、App_Init 之前）。

    板内对账：正常静默零回传，偏差才回传 [AS:DEV]。
    """
    lines = ["  extern uint32_t _estack;"]
    for p in getattr(expectations, "points", []):
        read = _PROBE_READS.get(p.point)
        if read:
            lines.append(f'  AS_PROBE("{p.point}", {p.expect}, {read});')
    return "\n".join(lines)


def build_send_fn() -> str:
    """生成发送函数（用调试串口 huart1；工程需有 usart.c 定义 huart1）。

    返回 HAL_UART_Transmit 的返回值（HAL_OK=0 成功，HAL_BUSY/HAL_TIMEOUT=非0 失败），
    flush 据此判断是否丢帧——不静默吞发送失败（念安「绝不静默放行」）。
    timeout 用 100ms（与业务打印 hello 一致）。
    """
    return (
        "int as_trace_uart_send(const uint8_t *data, uint16_t len)\n"
        "{\n"
        "  extern UART_HandleTypeDef huart1;\n"
        "  return (HAL_UART_Transmit(&huart1, (uint8_t *)data, len, 100) == HAL_OK) ? 0 : -1;\n"
        "}\n"
    )


def inject(main_c: str, init_block: str, probe_block: str, send_fn: str) -> str:
    """把探针注入 main.c（字符串后处理，不改模板）。

    注入顺序（保证顺序正确）：
      ① include 区：main.h 后加 AS_TRACE_ENABLE + as_trace.h + 发送函数前置声明
      ② as_trace_init + ID 自报：HAL_Init() 之前（先 init 后自报，TR 才能入缓冲）
      ③ TR 埋点：HAL_Init / SystemClock_Config / 每个 MX_xxx_Init 后插 as_trace_report
      ④ AS_PROBE 对账：App_Init() 之前（所有驱动初始化完，板内对账）
      ⑤ 主循环 flush：while (1) 之后
      ⑥ 发送函数：文件末尾追加
    """
    # ① include 区：main.h 后加 AS_TRACE_ENABLE + as_trace.h + 发送函数前置声明
    if '#include "as_trace.h"' not in main_c:
        main_c = main_c.replace(
            '#include "main.h"',
            '#define AS_TRACE_ENABLE\n#include "main.h"\n#include "as_trace.h"\n\n'
            'int as_trace_uart_send(const uint8_t *data, uint16_t len);',
            1,
        )

    # ② as_trace_init + ID 自报：HAL_Init() 之前
    if "as_trace_init(as_trace_uart_send" not in main_c:
        main_c = main_c.replace(
            "  HAL_Init();",
            init_block + "\n\n  /* MCU Configuration */\n  HAL_Init();",
            1,
        )

    # ③ TR 埋点：关键节点后插 as_trace_report（HAL_Init / SystemClock_Config / MX_xxx_Init）
    for call, name in (
        ("HAL_Init();", "HAL_Init"),
        ("SystemClock_Config();", "SystemClock_Config"),
    ):
        if f'as_trace_report("{name}");' not in main_c:
            main_c = main_c.replace(
                f"  {call}", f"  {call}\n  as_trace_report(\"{name}\");", 1
            )
    for name in sorted(set(re.findall(r"\b(MX_\w+_Init)\(\);", main_c))):
        if f'as_trace_report("{name}");' not in main_c:
            main_c = main_c.replace(
                f"  {name}();", f"  {name}();\n  as_trace_report(\"{name}\");", 1
            )

    # ④ AS_PROBE 对账：App_Init() 之前（所有驱动初始化完）
    if "extern uint32_t _estack;" not in main_c:
        main_c = main_c.replace(
            "  App_Init();",
            probe_block + "\n\n  App_Init();",
            1,
        )

    # ⑤ 主循环 flush：while (1) 之后
    if "as_trace_flush();" not in main_c:
        main_c = main_c.replace(
            "while (1)\n  {",
            "while (1)\n  {\n    as_trace_flush();",
            1,
        )

    # ⑥ 发送函数：文件末尾追加
    if "int as_trace_uart_send(const uint8_t *data, uint16_t len)\n{" not in main_c:
        main_c = main_c.rstrip("\n") + "\n\n/* Agent-S trace send（调试串口回传）*/\n" + send_fn + "\n"

    return main_c


def copy_as_trace(files: dict[str, str], base: str) -> dict[str, str]:
    """把 as_trace.h/.c 复制进工程文件树。"""
    header = _AS_TRACE_DIR / "as_trace.h"
    source = _AS_TRACE_DIR / "as_trace.c"
    if header.exists():
        files[f"{base}/Core/Inc/as_trace.h"] = header.read_text(encoding="utf-8")
    if source.exists():
        files[f"{base}/Core/Src/as_trace.c"] = source.read_text(encoding="utf-8")
    return files


def apply_trace(
    files: dict[str, str],
    base: str,
    expectations: Any,
    enable: bool,
    chip: str = "",
    fw: str = "",
) -> dict[str, str]:
    """对生成的文件树可选注入探针。

    Args:
        files: build_standard_project 产出的文件树 {路径: 内容}。
        base: 工程目录名（如 "proj"）。
        expectations: 预期值表（有 .points）。
        enable: 是否注入（False 原样返回）。
        chip: 芯片型号（ID 自报用）。
        fw: 固件版本（ID 自报用）。
    """
    if not enable:
        return files

    main_c_path = f"{base}/Core/Src/main.c"
    main_c = files.get(main_c_path, "")
    if not main_c:
        return files

    files[main_c_path] = inject(
        main_c,
        build_init_block(chip, fw),
        build_probe_block(expectations),
        build_send_fn(),
    )
    return copy_as_trace(files, base)
