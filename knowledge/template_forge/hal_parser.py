"""HAL 库解析器：从外部 HAL 库正则解析每个外设的 API 骨架（句柄/Init 字段/函数签名/宏），输出 JSON 供模板拼装消费。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from infrastructure.chip_gateway import gateway  # 芯片系列识别接口：hal_prefix / reference_dir（动态对接，不写死系列）

_log = logging.getLogger(__name__)

# 结构体块匹配：typedef struct [__XXX] { ... } YYY;
_STRUCT_BLOCK_RE = re.compile(
    r"typedef\s+struct\s+(?:__)?(\w*)\s*\{(.*?)\}\s*(\w+)\s*;",
    re.DOTALL,
)
# 字段行匹配：类型 + 名字（含指针），跳过注释行
_FIELD_RE = re.compile(
    r"^\s*(?:(?:const\s+)?(?:volatile\s+)?[\w\s\*]+?)\s+(\w+)\s*;",
    re.MULTILINE,
)
# 函数签名匹配：返回类型 HAL_Xxx(...);
_FUNC_RE = re.compile(
    r"^\s*(HAL_StatusTypeDef|void|uint32_t|uint16_t|uint8_t|int32_t|"
    r"HAL_Tim_StateTypeDef|HAL_LockTypeDef|HAL_UART_StateTypeDef|"
    r"HAL_DMA_StateTypeDef|HAL_ADC_StateTypeDef|HAL_ADC_LevelTypeDef|"
    r"HAL_CRC_StateTypeDef|HAL_I2C_StateTypeDef|HAL_SPI_StateTypeDef|"
    r"HAL_CAN_StateTypeDef|HAL_RTC_StateTypeDef|HAL_RTC_DateTypeDef\*?|"
    r"HAL_RTC_TimeTypeDef\*?|HAL_SD_CardStateTypeDef|HAL_SD_ErrorTypedef|"
    r"HAL_SD_StateTypeDef)\s*"
    r"(HAL_\w+)\s*\(([^)]*)\)\s*;",
    re.MULTILINE,
)
# 宏匹配：__HAL_RCC_*_CLK_ENABLE 等
_MACRO_RE = re.compile(
    r"^\s*#define\s+(__HAL_\w+|HAL_\w+)\b",
    re.MULTILINE,
)

# 外设名 → 头文件名后缀（不含系列前缀；前缀由 chip_gateway 的 hal_prefix 动态注入，换系列不改本表）
_PERI_TO_HEADER_SUFFIX = {
    "gpio": "hal_gpio.h",
    "uart": "hal_uart.h",
    "usart": "hal_uart.h",
    "tim": "hal_tim.h",
    "spi": "hal_spi.h",
    "i2c": "hal_i2c.h",
    "adc": "hal_adc.h",
    "dac": "hal_dac.h",
    "dma": "hal_dma.h",
    "rtc": "hal_rtc.h",
    "can": "hal_can.h",
    "crc": "hal_crc.h",
    "rng": "hal_rng.h",
    "sdio": "hal_sd.h",
    "iwdg": "hal_iwdg.h",
    "wwdg": "hal_wwdg.h",
    "exti": "hal_gpio.h",  # EXTI 在 gpio 头
    "pwr": "hal_pwr.h",
    "flash": "hal_flash.h",
    "eth": "hal_eth.h",
    "usb": "hal_pcd.h",
    "i2s": "hal_i2s.h",
    "dma2d": "hal_dma2d.h",
    "dfsdm": "hal_dfsdm.h",
    "dsi": "hal_dsi.h",
    "fmc": "hal_fmc.h",
    "fsmc": "hal_fsmc.h",
    "hash": "hal_hash.h",
    "hcd": "hal_hcd.h",
    "irda": "hal_irda.h",
    "ltdc": "hal_ltdc.h",
    "nand": "hal_nand.h",
    "nor": "hal_nor.h",
    "pcd": "hal_pcd.h",
    "qspi": "hal_qspi.h",
    "sai": "hal_sai.h",
    "sd": "hal_sd.h",
    "smartcard": "hal_smartcard.h",
    "smbus": "hal_smbus.h",
    "spdifrx": "hal_spdifrx.h",
    "swpmi": "hal_swpmi.h",
    "uart_legacy": "hal_uart.h",
    # G4 新外设 + 核心模块（补，丢手册材料提取白名单需要）
    "comp": "hal_comp.h",
    "opamp": "hal_opamp.h",
    "cordic": "hal_cordic.h",
    "fmac": "hal_fmac.h",
    "fdcan": "hal_fdcan.h",
    "rcc": "hal_rcc.h",
    "cortex": "hal_cortex.h",
}

# 常见句柄结构体名模式：<PERI>_HandleTypeDef
_HANDLE_RE = re.compile(r"^(\w+)_HandleTypeDef$")
_INIT_RE = re.compile(r"^(\w+)_InitTypeDef$")


class HalParser:
    """HAL 库解析器：从 26 万行库提取外设 API 骨架。"""

    def __init__(self, hal_dir: Path | str | None = None, chip: str | None = None) -> None:
        # 芯片系列动态对接（修跨系列断层）：不再写死 stm32f4xx，
        # 由 chip_gateway 按芯片名解析 hal_prefix（stm32f4xx/f1xx/g4xx）与 reference 库目录。
        self._chip = chip or gateway.default_chip()
        self._hal_prefix = gateway.hal_prefix(self._chip)
        self._hal_dir = Path(hal_dir) if hal_dir else gateway.reference_dir(self._chip) / "hal" / "Inc"
        self._cache: dict[str, dict[str, Any]] = {}
        self._header_cache: dict[str, str] = {}
        _log.info("HalParser: chip=%s prefix=%s hal_dir=%s", self._chip, self._hal_prefix, self._hal_dir)

    # ---- 公开入口 ----

    def get_skeleton(self, peripheral: str) -> dict[str, Any] | None:
        """获取外设 API 骨架（缓存，二次调用零 IO）。

        Returns:
            {"peripheral": "UART", "handle": {...}, "init": {...},
             "funcs": [...], "macros": [...]} 或 None（解析失败）
        """
        key = peripheral.strip().lower()
        if key in self._cache:
            return self._cache[key]
        header_name = self._header_name(key)
        if not header_name:
            _log.debug("HalParser: 无头文件映射: %s", peripheral)
            return None
        text = self._read_header(header_name)
        if not text:
            return None
        skeleton = self._parse_header(text, key)
        if skeleton is None:
            return None
        self._cache[key] = skeleton
        return skeleton

    def all_peripherals(self) -> list[str]:
        """可用外设清单（有头文件映射的）。"""
        return sorted(_PERI_TO_HEADER_SUFFIX)

    def export_all(self, out_dir: Path | str | None = None) -> dict[str, dict[str, Any]]:
        """导出全部外设骨架到 JSON（供锻造器批量消费）。"""
        result: dict[str, dict[str, Any]] = {}
        for peri in self.all_peripherals():
            sk = self.get_skeleton(peri)
            if sk:
                result[peri] = sk
        if out_dir:
            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "hal_skeleton_all.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return result

    # ---- 内部实现 ----

    def _header_name(self, peripheral_key: str) -> str | None:
        """外设名 → 完整头文件名（{hal_prefix}_{suffix}，如 stm32f1xx_hal_uart.h）。"""
        suffix = _PERI_TO_HEADER_SUFFIX.get(peripheral_key)
        if not suffix:
            return None
        return f"{self._hal_prefix}_{suffix}"

    def _read_header(self, header_name: str) -> str:
        if header_name in self._header_cache:
            return self._header_cache[header_name]
        path = self._hal_dir / header_name
        if not path.exists():
            # 兜底：模糊匹配 {hal_prefix}_hal_<name>*.h（如 stm32f4xx_hal_uart_ex.h 变体）
            stem = header_name[:-2] if header_name.endswith(".h") else header_name
            candidates = list(self._hal_dir.glob(f"{stem}*.h"))
            if not candidates:
                _log.debug("HalParser: 头文件不存在: %s", path)
                return ""
            path = candidates[0]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _log.debug("HalParser: 读取失败 %s: %s", path, exc)
            return ""
        # 条件编译扁平化：保留 #if 第一分支（HAL 头文件里条件编译多为平铺，简单版够用）
        text = self._flatten_cond(text)
        self._header_cache[header_name] = text
        return text

    @staticmethod
    def _flatten_cond(text: str) -> str:
        """去掉 #if/#else/#endif 行，保留 #if 后第一分支（删 #else 分支）。"""
        out: list[str] = []
        depth = 0
        skip = False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#if"):
                depth += 1
                continue  # 删 #if 行，保留其后第一分支
            if s.startswith("#else"):
                skip = True
                continue
            if s.startswith("#endif"):
                if depth > 0:
                    depth -= 1
                skip = False
                continue
            if skip:
                continue
            out.append(line)
        return "\n".join(out)

    def _parse_header(self, text: str, peripheral_key: str) -> dict[str, Any] | None:
        """解析头文件 → 骨架。"""
        structs = self._extract_structs(text)
        handle_name = f"{peripheral_key.upper()}_HandleTypeDef"
        init_name = f"{peripheral_key.upper()}_InitTypeDef"
        # UART 特例：句柄是 UART_HandleTypeDef，Init 也是 UART_InitTypeDef
        if peripheral_key == "uart":
            handle_name = "UART_HandleTypeDef"
            init_name = "UART_InitTypeDef"
        if peripheral_key == "usart":
            handle_name = "UART_HandleTypeDef"
            init_name = "UART_InitTypeDef"
        # SDIO 特例：用 SD_HandleTypeDef
        if peripheral_key == "sdio":
            handle_name = "SD_HandleTypeDef"
            init_name = "SD_InitTypeDef"

        handle = structs.get(handle_name, {})
        init = structs.get(init_name, {})
        # 模糊回退：TIM_Base_InitTypeDef / SD_InitTypeDef 等带修饰前缀的结构体
        if not handle:
            for name, fields in structs.items():
                if name.startswith(peripheral_key.upper()) and name.endswith("_HandleTypeDef"):
                    handle = fields
                    break
        if not init:
            for name, fields in structs.items():
                if name.startswith(peripheral_key.upper()) and name.endswith("_InitTypeDef"):
                    init = fields
                    break
        # GPIO 特例：无句柄结构体，init 用 GPIO_InitTypeDef（已在模糊回退覆盖）

        funcs = self._extract_funcs(text)
        macros = self._extract_macros(text)

        if not handle and not init and not funcs:
            _log.debug("HalParser: %s 骨架为空", peripheral_key)
            return None

        return {
            "peripheral": peripheral_key.upper(),
            "handle": handle,
            "init": init,
            "funcs": funcs,
            "macros": macros,
            "source": self._header_name(peripheral_key) or f"{self._hal_prefix}_hal_{peripheral_key}.h",
        }

    @staticmethod
    def _extract_structs(text: str) -> dict[str, dict[str, str]]:
        """提取所有 typedef struct 块 → {结构体名: {字段: 注释}}。"""
        result: dict[str, dict[str, str]] = {}
        for m in _STRUCT_BLOCK_RE.finditer(text):
            struct_name = m.group(3).strip()
            body = m.group(2)
            fields: dict[str, str] = {}
            # 提取字段名（跳过回调函数指针、位域、嵌套匿名结构体）
            for fm in _FIELD_RE.finditer(body):
                field = fm.group(1)
                if field in ("uint32_t", "uint16_t", "uint8_t", "int32_t", "void"):
                    continue
                if field.startswith("__") or field == "reserved":
                    continue
                if field in fields:
                    continue
                fields[field] = HalParser._field_comment(body, fm.start())
            if struct_name.endswith("_HandleTypeDef") or struct_name.endswith("_InitTypeDef"):
                result[struct_name] = fields
        return result

    @staticmethod
    def _extract_funcs(text: str) -> list[dict[str, str]]:
        """提取 HAL 函数签名 → [{name, returns, args}]。"""
        funcs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for m in _FUNC_RE.finditer(text):
            name = m.group(2)
            if name in seen:
                continue
            seen.add(name)
            returns = m.group(1).strip()
            args_raw = m.group(3).strip()
            args = [a.strip() for a in args_raw.split(",") if a.strip()]
            funcs.append({"name": name, "returns": returns, "args": args})
        return funcs

    @staticmethod
    def _extract_macros(text: str) -> list[str]:
        """提取 HAL 相关宏名。"""
        macros: list[str] = []
        seen: set[str] = set()
        for m in _MACRO_RE.finditer(text):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            macros.append(name)
        return macros

    @staticmethod
    def _field_comment(body: str, field_start: int) -> str:
        """提取字段后面的 /*!< ... */ 注释（单行）。"""
        rest = body[field_start:]
        cm = re.search(r"/\*!?\s*<([^*]*)\*/", rest)
        if cm:
            return cm.group(1).strip()
        return ""


def load_all_skeletons(hal_dir: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """便捷入口：解析全部外设骨架。"""
    return HalParser(hal_dir).export_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = HalParser()
    sk = parser.get_skeleton("uart")
    if sk:
        print(f"UART handle fields: {list(sk['handle'].keys())}")
        print(f"UART init fields:   {list(sk['init'].keys())}")
        print(f"UART funcs:         {[f['name'] for f in sk['funcs'][:10]]}")
        print(f"UART macros:        {sk['macros'][:8]}")
