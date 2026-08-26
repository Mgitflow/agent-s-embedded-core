"""保存前筛查：打包进 output/flash/ 前做 MUST/SHOULD 两级检查（SWD 复用、时钟超频、hex 起始地址等），MUST 不通过则拒绝打包。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 芯片时钟上限（从 profile 读不到时兜底；权威值在 chips/apm32f407vgt6/profile.json）
DEFAULT_MAX_CLOCK_MHZ = 168
FLASH_START = 0x08000000

# 受保护引脚（调试/启动/晶振/板载按键）——来自 board.json + profile.json special_pins
PROTECTED_PINS: tuple[tuple[str, str, bool], ...] = (
    ("PA13", "SWDIO（调试）", True),
    ("PA14", "SWCLK（调试）", True),
    ("PB2", "BOOT1（启动选择）", True),
    ("PA0", "KEY_UP（板载按键）", False),  # 板载按键非绝对禁止，但需需求提及
    ("PE4", "KEY0（板载按键）", False),
)

# 每引脚对应的时钟宏（HAL：__HAL_RCC_GPIOx_CLK_ENABLE）
PIN_CLOCK_MACRO = {
    "PA": "__HAL_RCC_GPIOA_CLK_ENABLE",
    "PB": "__HAL_RCC_GPIOB_CLK_ENABLE",
    "PC": "__HAL_RCC_GPIOC_CLK_ENABLE",
    "PD": "__HAL_RCC_GPIOD_CLK_ENABLE",
    "PE": "__HAL_RCC_GPIOE_CLK_ENABLE",
    "PF": "__HAL_RCC_GPIOF_CLK_ENABLE",
    "PG": "__HAL_RCC_GPIOG_CLK_ENABLE",
}


@dataclass
class GuardIssue:
    """单条筛查结果。"""

    level: str  # MUST / SHOULD
    code: str  # 如 F1_SWD_REUSE
    message: str
    location: str = ""  # 文件名或代码位置


@dataclass
class FlashGuardReport:
    """保存前筛查报告。"""

    passed: bool = True
    issues: list[GuardIssue] = field(default_factory=list)

    def add(self, level: str, code: str, message: str, location: str = "") -> None:
        self.issues.append(GuardIssue(level, code, message, location))
        if level == "MUST":
            self.passed = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "must_passed": not any(i.level == "MUST" for i in self.issues),
            "issues": [
                {
                    "level": i.level,
                    "code": i.code,
                    "message": i.message,
                    "location": i.location,
                }
                for i in self.issues
            ],
        }


class FlashGuard:
    """保存前筛查器：静态检查工程目录，返回 FlashGuardReport。"""

    def __init__(
        self,
        board_info: dict[str, Any] | None = None,
        profile_info: dict[str, Any] | None = None,
        max_clock_mhz: int | None = None,
    ) -> None:
        self._board = board_info or {}
        self._profile = profile_info or {}
        self._max_clock = max_clock_mhz or (
            self._profile.get("meta", {}).get("max_clock_mhz")
            or DEFAULT_MAX_CLOCK_MHZ
        )

    # ── 入口 ──

    def check(
        self,
        project_dir: str | Path,
        requirement: str = "",
        compile_passed: bool = False,
        artifact_path: str = "",
    ) -> FlashGuardReport:
        """对工程目录执行保存前筛查。

        :param project_dir: 工程根目录（含 Makefile / Core / firmware.*）
        :param requirement: 原始需求文本（用于按键占用等语义判断）
        :param compile_passed: 编译是否通过
        :param artifact_path: elf 路径（若有）
        """
        report = FlashGuardReport()
        proj = Path(project_dir)

        main_c = proj / "Core" / "Src" / "main.c"
        main_text = ""
        if main_c.exists():
            main_text = main_c.read_text(encoding="utf-8", errors="ignore")
        else:
            # 能力预判修复：main.c 缺失 → 引脚/时钟/主循环三个核心筛查
            # 无法执行，必须 fail-closed 拦截（「未过筛查绝不打包」是底线承诺，
            # 不能因为筛查被静默跳过而放行）。
            report.add("MUST", "F13_MAIN_MISSING", "main.c 缺失，核心筛查（引脚/时钟/主循环）无法执行", str(main_c))

        self._check_protected_pins(main_text, requirement, report)
        self._check_clock(main_text, report)
        self._check_artifacts(proj, compile_passed, artifact_path, report)
        self._check_main_loop(main_text, requirement, report)
        return report

    # ── 引脚安全 ──

    def _check_protected_pins(
        self, main_text: str, requirement: str, report: FlashGuardReport
    ) -> None:
        if not main_text:
            return
        req = (requirement or "").lower()

        # 找出代码中配置为输出的引脚集合
        output_pins: set[str] = set()
        # HAL: GPIO_InitStruct.Pin = GPIO_PIN_13 | GPIO_PIN_14;  ... Mode = GPIO_MODE_OUTPUT_PP
        for m in re.finditer(
            r"GPIO_InitStruct\.Pin\s*=\s*([^;]+);",
            main_text,
        ):
            pins_expr = m.group(1)
            port = "?"
            pm = re.search(r"HAL_GPIO_Init\((\w+),\s*&GPIO_InitStruct\)", main_text[m.end():m.end() + 300])
            if pm:
                port = pm.group(1).replace("GPIO", "")
            for pn in re.finditer(r"GPIO_PIN_(\d+)", pins_expr):
                pin_no = int(pn.group(1))
                pin = f"P{port}{pin_no}"
                # 是否输出模式（看结构体后续 Mode 赋值）
                mode_m = re.search(r"GPIO_InitStruct\.Mode\s*=\s*(GPIO_MODE_\w+)", main_text[m.end():m.end() + 400])
                mode = mode_m.group(1) if mode_m else "GPIO_MODE_OUTPUT_PP"
                if "OUTPUT" in mode:
                    output_pins.add(pin)

        for pin, desc, hard in PROTECTED_PINS:
            if pin in output_pins:
                # 板载按键：仅当需求提及按键时才豁免
                if not hard:
                    if "按键" in req or "key" in req:
                        continue
                    report.add(
                        "SHOULD",
                        "F2_BOARD_KEY_REUSE",
                        f"板载 {desc}（{pin}）被配置为输出但需求未提按键",
                        "main.c",
                    )
                    continue
                report.add(
                    "MUST",
                    "F1_PROTECTED_PIN_REUSE",
                    f"受保护引脚 {pin}（{desc}）被配置为 GPIO 输出——"
                    "烧录后调试通道/启动选择将失效，板子可能变砖",
                    "main.c",
                )

        # 时钟使能检查：输出的引脚必须有对应时钟使能（弱校验，缺时钟会导致外设不工作但不会烧板）
        for pin in output_pins:
            port = pin[1]
            macro = PIN_CLOCK_MACRO.get(port)
            if macro and macro not in main_text:
                report.add(
                    "SHOULD",
                    "F3_GPIO_CLK_MISSING",
                    f"引脚 {pin} 配置为输出但缺少 {macro}() 时钟使能",
                    "main.c",
                )

    # ── 时钟合法性（对标 CubeMX 时钟树校验）──

    def _check_clock(self, main_text: str, report: FlashGuardReport) -> None:
        if not main_text:
            return

        # PLL 倍频产物：SYSCLK = HSE * PLLN / (PLLM * PLLP)
        hse = 8  # 板载晶振
        pllm = self._first_int(main_text, r"PLLM\s*=\s*(\d+)", default=8)
        plln = self._first_int(main_text, r"PLLN\s*=\s*(\d+)", default=336)
        pllp = self._first_int(main_text, r"PLLP\s*=\s*(?:RCC_PLLP_DIV)?(\d+)", default=2)
        sysclk = hse * plln / (pllm * pllp) if pllm * pllp else 0

        if sysclk and sysclk > self._max_clock:
            report.add(
                "MUST",
                "F4_CLOCK_OVERCLOCK",
                f"时钟超频：SYSCLK≈{sysclk:.0f}MHz 超过芯片上限 {self._max_clock}MHz",
                "main.c",
            )

        # FLASH_LATENCY 匹配（F4 系：≤168MHz 用 5WS，168MHz 必须 5WS）
        latency = None
        lm = re.search(r"FLASH_LATENCY_(\d+)", main_text)
        if lm:
            latency = int(lm.group(1))
        if sysclk and latency is not None:
            if sysclk > 150 and latency < 5:
                report.add(
                    "MUST",
                    "F5_FLASH_LATENCY_LOW",
                    f"FLASH_LATENCY={latency} 过低：{sysclk:.0f}MHz 需要 5WS，"
                    "配置过低会导致 Flash 读取崩溃",
                    "main.c",
                )

        # APB1/APB2 上限（42/84MHz）
        apb1_div = self._first_int(main_text, r"APB1CLKDivider\s*=\s*RCC_HCLK_DIV(\d+)", default=4)
        apb2_div = self._first_int(main_text, r"APB2CLKDivider\s*=\s*RCC_HCLK_DIV(\d+)", default=2)
        if sysclk:
            apb1 = sysclk / apb1_div
            apb2 = sysclk / apb2_div
            if apb1 > 42:
                report.add(
                    "MUST",
                    "F6_APB1_OVERCLOCK",
                    f"APB1={apb1:.0f}MHz 超过 42MHz 上限（外设总线超频）",
                    "main.c",
                )
            if apb2 > 84:
                report.add(
                    "MUST",
                    "F7_APB2_OVERCLOCK",
                    f"APB2={apb2:.0f}MHz 超过 84MHz 上限（外设总线超频）",
                    "main.c",
                )

    # ── 产物完整性 ──

    def _check_artifacts(
        self,
        proj: Path,
        compile_passed: bool,
        artifact_path: str,
        report: FlashGuardReport,
    ) -> None:
        if not compile_passed:
            report.add("MUST", "F8_COMPILE_FAILED", "编译未通过，禁止打包烧录", "")
            return
        # hex 存在且非空
        hex_path = proj / "firmware.hex"
        if not hex_path.exists() or hex_path.stat().st_size == 0:
            report.add("MUST", "F9_HEX_MISSING", "firmware.hex 缺失或为空，无法烧录", str(hex_path))
        else:
            # 起始地址检查（Intel HEX 扩展地址记录）
            head = hex_path.read_text(encoding="utf-8", errors="ignore")[:64]
            m = re.search(r":02000004([0-9A-Fa-f]{4})", head)
            if m:
                base = int(m.group(1), 16) << 16
                if base != FLASH_START:
                    report.add(
                        "MUST",
                        "F10_HEX_BAD_ADDR",
                        f"hex 起始地址 0x{base:08X} 非 Flash 起始 0x{FLASH_START:08X}——烧错位置",
                        str(hex_path),
                    )
        bin_path = proj / "firmware.bin"
        if not bin_path.exists() or bin_path.stat().st_size == 0:
            report.add("SHOULD", "F11_BIN_MISSING", "firmware.bin 缺失（有 hex 仍可烧录，建议补齐）", str(bin_path))

    # ── 需求覆盖 ──

    def _check_main_loop(
        self, main_text: str, requirement: str, report: FlashGuardReport
    ) -> None:
        if not main_text:
            return
        loop = re.search(r"while\s*\(1\)\s*\{([^}]*)\}", main_text, re.DOTALL)
        if not loop or not loop.group(1).strip():
            report.add(
                "SHOULD",
                "F12_MAIN_LOOP_EMPTY",
                "主循环 while(1) 为空——需求功能可能未实现",
                "main.c",
            )

    # ── 工具 ──

    @staticmethod
    def _first_int(text: str, pattern: str, default: int) -> int:
        m = re.search(pattern, text)
        return int(m.group(1)) if m else default
