"""资源适配器：聚合 HL 库骨架/共享知识库/符号索引/芯片肖像四源，校验 HAL API 名真实性并生成注入注释增强模板。"""

from __future__ import annotations

import logging
import re
from typing import Any

from infrastructure.chip_gateway import gateway  # 芯片系列识别接口（跨系列动态，不写死 F4）

_log = logging.getLogger(__name__)

# 功能模板 → 关联外设（供知识聚合）
_FUNC_TO_PERIPHERAL = {
    "led_blink": "GPIO",
    "system_reset": "IWDG",
    "pwm_output": "TIM",
    "uart_print": "UART",
    "adc_read": "ADC",
    "button_read": "GPIO",
}


class ResourceAdapter:
    """四源资源适配器：聚合 HL 库/共享库/符号索引/芯片肖像。"""

    _api_cache: dict[str, set[str]] = {}       # chip → API 名集合（按芯片系列分键）
    _symbol_names: dict[str, set[str]] = {}    # chip → 符号名集合

    def __init__(self, chip: str | None = None) -> None:
        # 芯片系列动态对接（修跨系列断层）：不再写死 F4，由 chip_gateway 解析。
        self._chip = chip or gateway.default_chip()
        self._hal: Any = None
        self._external: Any = None
        self._symbol: Any = None
        self._portrait: Any = None

    # ---- 懒加载四源 ----

    def _get_hal(self) -> Any:
        if self._hal is None:
            try:
                from knowledge.template_forge.hal_parser import HalParser

                self._hal = HalParser(chip=self._chip)
            except Exception as exc:  # noqa: BLE001
                _log.debug("ResourceAdapter: HAL 加载失败 %s", exc)
                self._hal = False
        return self._hal or None

    def _get_external(self) -> Any:
        if self._external is None:
            try:
                from knowledge.external_kb import ExternalKnowledge

                self._external = ExternalKnowledge()
            except Exception as exc:  # noqa: BLE001
                _log.debug("ResourceAdapter: ExternalKB 加载失败 %s", exc)
                self._external = False
        return self._external or None

    def _get_symbol(self) -> Any:
        if self._symbol is None:
            try:
                from knowledge.symbol_index import SymbolIndex

                # 符号索引根 = 外部附属库 reference/hal（真实 HAL 库，随芯片系列）
                root = gateway.reference_dir(self._chip) / "hal"
                self._symbol = SymbolIndex(root)
            except Exception as exc:  # noqa: BLE001
                _log.debug("ResourceAdapter: SymbolIndex 加载失败 %s", exc)
                self._symbol = False
        return self._symbol or None

    def _get_portrait(self) -> Any:
        if self._portrait is None:
            try:
                from knowledge.template_forge.chip_portrait_adapter import ChipPortraitAdapter

                self._portrait = ChipPortraitAdapter()
            except Exception as exc:  # noqa: BLE001
                _log.debug("ResourceAdapter: ChipPortrait 加载失败 %s", exc)
                self._portrait = False
        return self._portrait or None

    # ---- API 名校验（HL 库骨架） ----

    def validate_api_names(self, code: str, peripheral: str) -> list[str]:
        """用**全 HAL 库**骨架验证代码里的 HAL_* 函数名真实存在。

        跨外设 API（HAL_GPIO_Init / HAL_RCC_OscConfig / HAL_Delay）在别的头文件——
        校验必须用全库白名单，不能只看当前外设头文件。
        Returns: 不存在的函数名列表（空 = 全通过）。
        """
        hal = self._get_hal()
        if not hal:
            return []
        real_names = self._all_api_names(hal)
        # 第四源：符号索引（真实 HAL 库函数定义），补 HalParser 骨架遗漏的 HAL_Ex 等扩展 API
        real_names.update(self._all_symbol_names())
        called = set(re.findall(r"\b(HAL_\w+|__HAL_\w+)\s*\(", code))
        # HAL_xxx_MspInit / HAL_xxx_MspDeInit 是 HAL 弱回调（标准工程 hal_msp.c 重载），
        # 总是合法（reference 精简库未收录其声明，跳过校验）
        called = {n for n in called if not n.endswith("_MspInit") and not n.endswith("_MspDeInit")}
        return sorted(n for n in called if n not in real_names)

    @staticmethod
    def _all_api_names(hal: Any) -> set[str]:
        """收集全 HAL 库所有头文件的函数名 + 宏名（按芯片系列缓存）。

        核心头文件（主 hal.h / rcc / pwr / gpio 等）用文本正则补充——
        HAL_Init/HAL_Delay/HAL_RCC_OscConfig 等跨外设 API 不在外设骨架里。
        """
        chip = getattr(hal, "_chip", "default")
        if chip not in ResourceAdapter._api_cache:
            names: set[str] = set()
            for peri in hal.all_peripherals():
                sk = hal.get_skeleton(peri)
                if not sk:
                    continue
                names.update(f["name"] for f in sk.get("funcs", []))
                names.update(sk.get("macros", []))
            # 核心头文件补充（主 HAL / RCC / PWR / GPIO / NVIC / Cortex）
            import re

            # 系列前缀 + 目录从 hal 对象取（随系列走，不再写死 stm32f4xx）
            prefix = getattr(hal, "_hal_prefix", "stm32f4xx")
            hal_dir = getattr(hal, "_hal_dir", None)
            if hal_dir is None:
                ResourceAdapter._api_cache[chip] = names  # 无目录信息则仅外设骨架名
                return ResourceAdapter._api_cache[chip]
            core_headers = [
                f"{prefix}_hal.h",
                f"{prefix}_hal_def.h",  # __HAL_LINKDMA 等通用宏
                f"{prefix}_hal_rcc.h",
                f"{prefix}_hal_rcc_ex.h",
                f"{prefix}_hal_pwr.h",
                f"{prefix}_hal_pwr_ex.h",
                f"{prefix}_hal_gpio.h",
                f"{prefix}_hal_gpio_ex.h",
                f"{prefix}_hal_cortex.h",
                f"{prefix}_hal_flash.h",
            ]
            func_re = re.compile(r"\b(HAL_\w+|__HAL_\w+)\s*\(")
            macro_re = re.compile(r"^\s*#define\s+(__HAL_\w+|HAL_\w+)\b", re.MULTILINE)
            for hdr in core_headers:
                path = hal_dir / hdr
                if not path.exists():
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                names.update(func_re.findall(text))
                names.update(macro_re.findall(text))
            ResourceAdapter._api_cache[chip] = names
        return ResourceAdapter._api_cache[chip]

    def _all_symbol_names(self) -> set[str]:
        """第四源：符号索引（真实 HAL 库函数定义），补 HalParser 骨架遗漏的 API，按芯片系列缓存。

        SymbolIndex 直接扫描真实 HAL 库 .c/.h 的函数定义，比 HalParser 的「外设骨架」
        更全（含 HAL_ADCEx_* 等扩展 API）。构建一次（约 3s）后类级缓存，后续秒回。
        """
        chip = self._chip
        if chip not in self._symbol_names:
            names: set[str] = set()
            try:
                from knowledge.symbol_index import SymbolIndex

                root = gateway.reference_dir(self._chip) / "hal"
                idx = SymbolIndex(root)
                idx.build()
                names.update(idx.symbols_by_prefix("HAL_"))
                names.update(idx.symbols_by_prefix("__HAL_"))
            except Exception as exc:  # noqa: BLE001 —— 符号索引不可用则跳过（三源兜底）
                _log.debug("ResourceAdapter: SymbolIndex 构建失败 %s", exc)
            self._symbol_names[chip] = names
        return self._symbol_names[chip]

    # ---- 知识注释构建（多源聚合） ----

    def build_knowledge_note(self, template_id: str, params: dict[str, Any] | None = None) -> str:
        """把四源知识聚合为模板头注释（官方写法/引脚/规则/API 提示）。"""
        params = params or {}
        peripheral = _FUNC_TO_PERIPHERAL.get(template_id, "")
        if not peripheral:
            return ""
        lines: list[str] = ["/*", f" * [资源适配] {template_id} — 四源知识聚合 (Agent-S Forge)"]

        # ① 芯片肖像：引脚/芯片
        portrait = self._get_portrait()
        if portrait:
            chip = portrait.get_chip_name()
            lines.append(f" *  芯片: {chip}")
            # UART 引脚
            inst = params.get("uart_instance", "1")
            pins = portrait.get_default_pins("USART", str(inst))
            if pins:
                lines.append(f" *  引脚: {pins}")

        # ② 共享库官方写法（取正文里有意义的行，附来源标注——依据来源链）
        ext = self._get_external()
        if ext:
            note = ext.get_for_peripheral(peripheral, limit=2, max_chars=600)
            if note:
                # 来源标记（--- 来源: X ---）从 ExternalKnowledge 透传，取 snippet 时带上
                src_m = re.search(r"--- 来源: ([^\s-]+) ---", note)
                src_tag = f" [来源:{src_m.group(1)}]" if src_m else ""
                lines_raw = [ln.strip() for ln in note.splitlines() if ln.strip()]
                # 优先含 HAL_API 实质的行；其次函数调用/定义行；跳过元数据（> 开头/来源/评分）
                useful = [ln for ln in lines_raw if "HAL_" in ln and not ln.startswith(">")]
                if not useful:
                    useful = [ln for ln in lines_raw if ("->" in ln or "void HAL" in ln or "HAL_StatusTypeDef" in ln) and not ln.startswith(">")]
                if useful:
                    snippet = useful[0][:120]
                    lines.append(f" *  官方写法: {snippet}{src_tag}")
                else:
                    first = lines_raw[0][:120] if lines_raw else ""
                    if first and "来源" not in first:
                        lines.append(f" *  官方参考: {first}{src_tag}")

        # ③ 规则（standards）
        if portrait:
            rules = portrait.get_standard_rules(peripheral.lower())
            if rules:
                lines.append(f" *  质量规则: {', '.join(rules[:4])}")

        # ④ HL 库 API 提示（该外设核心函数）
        hal = self._get_hal()
        if hal:
            skeleton = hal.get_skeleton(peripheral.lower())
            if skeleton and skeleton.get("funcs"):
                core = [f["name"] for f in skeleton["funcs"][:3]]
                lines.append(f" *  HAL API: {', '.join(core)}")

        lines.append(" */")
        return "\n".join(lines) + "\n"

    # ---- 便捷入口 ----

    def enhance(self, template_id: str, code: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """增强：校验 + 注注入。返回 {"code": 增强后代码, "api_errors": [...]}。"""
        params = params or {}
        peripheral = _FUNC_TO_PERIPHERAL.get(template_id, "")
        api_errors = self.validate_api_names(code, peripheral) if peripheral else []
        note = self.build_knowledge_note(template_id, params)
        enhanced = (note + code) if note and note not in code else code
        return {"code": enhanced, "api_errors": api_errors}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    adapter = ResourceAdapter()
    sample = "HAL_UART_Init(&h); HAL_UART_Transmit(&h, d, 1, 10);"
    errors = adapter.validate_api_names(sample, "UART")
    print("API 校验（真实 HAL 库）:", errors or "全部真实存在")
    note = adapter.build_knowledge_note("uart_print", {"uart_instance": "1"})
    print(note)
