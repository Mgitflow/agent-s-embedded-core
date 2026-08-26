"""芯片肖像适配器：把 af_map/standards/profile 转成模板参数自动填充源（外设→默认引脚/AF 编号），芯片缺失时返回空补全兜底。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

_log = logging.getLogger(__name__)

# 芯片肖像目录（skills/chips/）——parents[2]=项目根
_CHIPS_DIR = Path(__file__).resolve().parents[2] / "skills" / "chips"

# 默认芯片（统一：与 chip_gateway._DEFAULT_CHIP / config.DEFAULT_CHIP_NAME 对齐，
# 主开发板=探索者 stm32f407zgt6。此前 apm32f407vgt6 是最小系统板，导致 block_assembler
# RTC 铺开匹配不到探索者画像、LSE 回退 LSI 的「芯片名混用」缺陷。）
DEFAULT_CHIP = "stm32f407zgt6"

# 功能模板 → 需要的芯片肖像信息（外设名 / 参数键映射）
_PORTRAIT_KEYS: dict[str, dict[str, Any]] = {
    "uart_print": {
        "peripheral": "USART",
        "param_map": {
            "uart_instance": "instance_no",   # 用户给 instance，补 default_pins
            "tx_pin": "tx_pin",
            "rx_pin": "rx_pin",
            "af_number": "af_number",
        },
    },
    "pwm_output": {
        "peripheral": "TIM",
        "param_map": {
            "tim_instance": "instance_no",
            "pwm_pin": "ch1_pin",   # TIMx_CH1 默认引脚
        },
    },
    "adc_read": {
        "peripheral": "ADC",
        "param_map": {
            "adc_instance": "instance_no",
            "adc_pin": "adc_pin",
        },
    },
}

# 外设实例 → af_map 查询键
_INSTANCE_TO_KEY = {
    "1": "USART1", "2": "USART2", "3": "USART3", "4": "UART4", "5": "UART5", "6": "USART6",
}


class ChipPortraitAdapter:
    """芯片肖像适配器：af_map/standards/profile → 模板参数自动补全。"""

    def __init__(self, chips_dir: Path | str | None = None, chip: str | None = None) -> None:
        self._chips_dir = Path(chips_dir or _CHIPS_DIR)
        self._chip = chip or DEFAULT_CHIP
        self._af_map: dict[str, Any] = {}
        self._profile: dict[str, Any] = {}
        self._standards: dict[str, Any] = {}
        self._pin_map: dict[str, Any] = {}
        self._remap_map: dict[str, Any] = {}  # f103 专属：{信号: {引脚: [AFIO 重映射宏]}}
        self._load()

    # ---- 加载 ----

    def _load(self) -> None:
        chip_dir = self._chips_dir / self._chip
        if not chip_dir.exists():
            _log.debug("ChipPortrait: 芯片目录缺失 %s", chip_dir)
            # 共享知识库兜底（知识库融合：共享库是图书馆，S 从图书馆取）
            try:
                import os

                from infrastructure.config import SHARED_KB_ROOT

                kb_root = Path(os.environ.get("AGENT_SHARED_KB", str(SHARED_KB_ROOT)))
                kb_chip = kb_root / "chip_portraits" / self._chip
                if kb_chip.exists():
                    chip_dir = kb_chip
                    _log.info("ChipPortrait: 从共享知识库读取 %s", kb_chip)
                else:
                    return
            except Exception as exc:  # noqa: BLE001
                _log.debug("ChipPortrait: 共享库兜底失败 %s", exc)
                return
        self._af_map = self._load_json(chip_dir / "af_map.json")
        self._profile = self._load_json(chip_dir / "profile.json")
        self._pin_map = self._load_json(chip_dir / "pin_map.json")
        self._remap_map = self._load_json(chip_dir / "remap_map.json")  # f103 AFIO 重映射（无此文件则 {}）
        std_dir = chip_dir / "standards"
        if std_dir.exists():
            for path in std_dir.glob("*_standard.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    peri = str(data.get("peripheral", path.stem.split("_")[0])).lower()
                    self._standards[peri] = data
                except (OSError, json.JSONDecodeError) as exc:
                    _log.debug("ChipPortrait: standards 加载失败 %s: %s", path, exc)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        try:
            tmp = json.loads(path.read_text(encoding="utf-8"))
            return tmp if isinstance(tmp, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            _log.debug("ChipPortrait: 加载失败 %s: %s", path, exc)
            return {}

    # ---- 补全 ----

    def fill_params(self, template_id: str, params: dict[str, Any]) -> dict[str, Any]:
        """按功能模板的肖像需求补全参数（用户给的优先，肖像兜底）。"""
        filled = dict(params)
        keys = _PORTRAIT_KEYS.get(template_id)
        if not keys:
            return filled
        peri = keys["peripheral"]
        param_map = keys["param_map"]

        # 从用户参数或默认取实例号
        instance_no = str(params.get("uart_instance", params.get("tim_instance", params.get("adc_instance", "1"))))
        # 补 AF 引脚（default_pins）
        if peri == "USART":
            self._fill_uart(filled, instance_no, param_map)
        elif peri == "TIM":
            self._fill_tim(filled, instance_no, param_map)
        elif peri == "ADC":
            self._fill_adc(filled, instance_no, param_map)
        return filled

    # ---- 各外设补全 ----

    def _fill_uart(self, filled: dict[str, Any], instance_no: str, param_map: dict[str, Any]) -> None:
        key = _INSTANCE_TO_KEY.get(instance_no, f"USART{instance_no}")
        pins = (self._af_map.get("default_pins") or {}).get(key) or {}
        af = (self._af_map.get("af_numbers") or {}).get(key)
        if "uart_instance" in param_map and "uart_instance" not in filled:
            filled["uart_instance"] = instance_no
        if "tx_pin" in param_map and "tx_pin" not in filled and pins.get("tx"):
            filled["tx_pin"] = pins["tx"]
        if "rx_pin" in param_map and "rx_pin" not in filled and pins.get("rx"):
            filled["rx_pin"] = pins["rx"]
        if "af_number" in param_map and "af_number" not in filled and af is not None:
            filled["af_number"] = str(af)
        # 派生参数：PA9 → tx_port=A / tx_pin_no=9（模板 GPIO_AF 生成需要）
        self._derive_pin_parts(filled, "tx")
        self._derive_pin_parts(filled, "rx")

    @staticmethod
    def _derive_pin_parts(filled: dict[str, Any], prefix: str) -> None:
        """从 {prefix}_pin（如 PA9）派生 {prefix}_port（A）和 {prefix}_pin_no（9）。"""
        pin = filled.get(f"{prefix}_pin")
        if not pin:
            return
        port_key = f"{prefix}_port"
        no_key = f"{prefix}_pin_no"
        if port_key not in filled:
            filled[port_key] = str(pin)[1]  # PA9 → A
        if no_key not in filled:
            filled[no_key] = str(pin)[2:]  # PA9 → 9

    def _fill_tim(self, filled: dict[str, Any], instance_no: str, param_map: dict[str, Any]) -> None:
        if "tim_instance" in param_map and "tim_instance" not in filled:
            filled["tim_instance"] = instance_no
        # TIM 通道 1 默认引脚从 af_map default_pins（部分芯片有）
        if "pwm_pin" in param_map and "pwm_pin" not in filled:
            pins = (self._af_map.get("default_pins") or {}).get(f"TIM{instance_no}") or {}
            if pins.get("ch1"):
                filled["pwm_pin"] = pins["ch1"]

    def _fill_adc(self, filled: dict[str, Any], instance_no: str, param_map: dict[str, Any]) -> None:
        if "adc_instance" in param_map and "adc_instance" not in filled:
            filled["adc_instance"] = instance_no
        if "adc_pin" in param_map and "adc_pin" not in filled:
            # ADC 通道默认引脚（PA0=ADC123_IN0 惯例）
            filled["adc_pin"] = f"PA{int(instance_no) * 0}" if instance_no == "1" else "PA1"

    # ---- 查询 ----

    def get_af_number(self, peripheral: str, instance: str) -> str | None:
        key = f"{peripheral}{instance}"
        af = (self._af_map.get("af_numbers") or {}).get(key)
        return str(af) if af is not None else None

    def get_default_pins(self, peripheral: str, instance: str) -> dict[str, str]:
        # UART4/UART5 key 不一致修复（既有 bug）：default_pins 里 key 是 UART5，但
        # get_default_pins("USART","5") 构造 USART5 查不到。经 _INSTANCE_TO_KEY 映射
        # （"5"→"UART5"），与 _fill_uart 保持一致。其他外设（TIM/SPI/I2C）无此歧义。
        peri_u = peripheral.upper()
        if peri_u in ("USART", "UART"):
            key = _INSTANCE_TO_KEY.get(instance, f"{peri_u}{instance}")
        else:
            key = f"{peri_u}{instance}"
        return (self._af_map.get("default_pins") or {}).get(key) or {}

    # ---- 完整引脚查询（铺平：186 信号全引脚） ----

    def find_pins(self, signal: str) -> list[str]:
        """按信号名查所有可用引脚（full_af_map 反推表）。

        Example:
            find_pins("SPI1_SCK") -> ["PA5", "PB3"]  # 全部可选引脚
        """
        full = (self._af_map.get("full_af_map") or {})
        val = full.get(signal, "")
        if not val:
            return []
        return [p.strip() for p in str(val).split("/") if p.strip()]

    def get_signal_candidates(self, signal: str) -> list[dict[str, Any]]:
        """按信号查候选引脚（**带排序声明**，）。

        一类功能可能有多个可选引脚——这里声明清楚：
        "这一类有几个、都是哪些、哪个优先"。
        排序规则：
          1. default_pins 里的默认引脚（固定优先引脚）排最前
          2. 其余按字母序（PA5 < PB3）
        每个候选标注 priority（从 1 起）+ is_default（是否固定优先）。

        ADC/DAC 信号（模拟输入）无 AF 复用，从 pin_map 反推。

        Example:
            get_signal_candidates("USART1_TX")
            -> [{"pin": "PA9", "priority": 1, "is_default": True},
                {"pin": "PB6", "priority": 2, "is_default": False}]
        """
        pins = self.find_pins(signal)
        if not pins and signal.startswith("ADC") and "_IN" in signal:
            # ADCx_INy 从 pin_map adc 字段反推（独立格式 "ADC1_IN0"，统一到 CubeMX）
            inst = signal.split("_IN")[0].replace("ADC", "")  # ADC1_IN0 → "1"
            ch = signal.split("_IN")[1]
            pins = self.find_adc_pins(inst, ch)
        if not pins and signal.startswith("DAC_OUT"):
            # DAC_OUTx 从 pin_map dac 字段反推
            ch = signal.replace("DAC_OUT", "")  # DAC_OUT1 → "1"
            pins = self.find_dac_pins(ch)
        if not pins:
            return []
        # 外设前缀（USART1_TX → USART1；TIM1_CH1 → TIM1）
        peri_key = signal.rsplit("_", 1)[0] if "_" in signal else signal
        defaults = (self._af_map.get("default_pins") or {}).get(peri_key) or {}
        default_set = {str(v).upper() for v in defaults.values() if v}
        ordered = [p for p in pins if p.upper() in default_set] + [
            p for p in pins if p.upper() not in default_set
        ]
        return [
            {
                "pin": p.upper(),
                "priority": i + 1,
                "is_default": p.upper() in default_set,
                "remap_macros": self.get_remap_macros(signal, p),
            }
            for i, p in enumerate(ordered)
        ]

    def get_remap_macros(self, signal: str, pin: str) -> list[str]:
        """查某信号某引脚需要的 AFIO 重映射宏（f103 专属，其他芯片返回空列表）。

        空列表 = 默认映射引脚（复位即可用，无需 AFIO 配置）；
        非空 = 重映射引脚，需在 init 里调用对应 __HAL_AFIO_REMAP_XXX 宏启用。

        Example:
            get_remap_macros("SPI1_SCK", "PB3") -> ["__HAL_AFIO_REMAP_SPI1_ENABLE"]
            get_remap_macros("SPI1_SCK", "PA5") -> []  # 默认映射
        """
        remap = self._remap_map.get("remap") or {}
        sig_map = remap.get(signal) or {}
        return list(sig_map.get(pin.upper()) or sig_map.get(pin) or [])

    def needs_afio_remap(self, signal: str, pin: str) -> bool:
        """该引脚是否为重映射引脚（需 AFIO 宏）。"""
        return bool(self.get_remap_macros(signal, pin))

    def find_adc_pins(self, instance: str, channel: str) -> list[str]:
        """查 ADCx_INy 的可用引脚（从 pin_map adc 字段反推）。

        pin_map 的 adc 是独立格式 ["ADC1_IN0", "ADC2_IN0", "ADC3_IN0"]（
        统一到 CubeMX 命名，替代旧合并格式 "ADC123_IN0"）。正则 ADC(\\d+)_IN(\\d+) 兼容
        两种格式（实例号 "1" 或 "123" 都按字符展开）。

        Example:
            find_adc_pins("1", "0") -> ["PA0"]
        """
        import re

        target_inst = str(instance)
        target_ch = str(channel)
        pins = (self._pin_map or {}).get("pins", {})
        result: list[str] = []
        for pin, info in pins.items():
            for adc in info.get("adc") or []:
                m = re.match(r"ADC(\d+)_IN(\d+)", str(adc))
                if not m:
                    continue
                insts = list(m.group(1))  # "123" → ["1","2","3"]
                if target_inst in insts and m.group(2) == target_ch:
                    result.append(pin)
                    break
        return sorted(result)

    def find_dac_pins(self, channel: str) -> list[str]:
        """查 DAC_OUTx 的可用引脚（从 pin_map dac 字段反推）。

        Example:
            find_dac_pins("1") -> ["PA4"]   # DAC_OUT1
            find_dac_pins("2") -> ["PA5"]   # DAC_OUT2
        """
        target = f"DAC_OUT{channel}"
        pins = (self._pin_map or {}).get("pins", {})
        return sorted(pin for pin, info in pins.items() if target in (info.get("dac") or []))

    def get_af_for_signal(self, signal: str) -> str | None:
        """查信号的外设 AF 编号（USART1_TX → AF7）。

        规则：信号前缀（USART1）→ af_numbers 里的编号。
        Returns: "7" 或 None（无 AF，如 ADC 模拟输入）。
        """
        if "_" not in signal:
            return None
        peri_key = signal.rsplit("_", 1)[0]  # USART1_TX → USART1
        af = (self._af_map.get("af_numbers") or {}).get(peri_key)
        return str(af) if af is not None else None

    def is_analog_signal(self, signal: str) -> bool:
        """信号是否为模拟输入（ADC/DAC）——引脚复用用 GPIO_MODE_ANALOG 而非 AF。"""
        return signal.startswith("ADC") or signal.startswith("DAC") or signal.startswith("VREF")

    def find_peripheral_pins(self, peripheral: str, instance: str) -> list[str]:
        """按外设+实例查全部可用引脚（TIM1 → TIM1_CH1/CH2/...）。"""
        full = self._af_map.get("full_af_map") or {}
        prefix = f"{peripheral.upper()}{instance}_"
        result: list[str] = []
        for signal, pins in full.items():
            if signal.startswith(prefix):
                for p in str(pins).split("/"):
                    if p.strip() and p.strip() not in result:
                        result.append(p.strip())
        return result

    def get_pin_info(self, pin: str) -> dict[str, Any] | None:
        """查单个引脚完整信息（functions/adc/dac/special/ft/notes）。"""
        pins = (self._pin_map or {}).get("pins", {})
        return cast(dict[str, Any] | None, pins.get(pin.upper()))

    def check_pin_conflict(self, pin: str, signal: str) -> bool:
        """检查引脚是否已被其他信号占用（组合工程防冲突）。

        Returns: True=该引脚当前没有冲突占用（可用）；False=已被占用。
        """
        info = self.get_pin_info(pin)
        if info is None:
            return False  # 引脚不存在
        # 引脚支持该信号 → 可用（实际占用检测由 OccupancyGrid 在 S3 做）
        funcs = info.get("functions", [])
        return signal in funcs or signal in [f"{s}" for s in funcs]

    def get_chip_name(self) -> str:
        return str((self._profile.get("meta") or {}).get("chip", self._chip))

    def has_pin_data(self) -> bool:
        """芯片是否有引脚数据（pin_map/af_map 是否加载成功）。

        探索者 ZGT6 等只有 profile 无 pin_map 的芯片返回 False——
        配置校验等依赖引脚数据的检查据此跳过（失败安全，不误杀）。
        """
        pins = (self._pin_map or {}).get("pins", {})
        return bool(pins) or bool(self._af_map.get("full_af_map"))

    def get_max_clock_mhz(self) -> int:
        return int((self._profile.get("meta") or {}).get("max_clock_mhz", 0))

    def supports_peripheral(self, peripheral: str) -> bool:
        peris = (self._profile.get("capabilities") or {}).get("peripherals", [])
        return peripheral.upper() in [p.upper() for p in peris]

    def get_standard_rules(self, peripheral: str, scene: str = "init") -> list[str]:
        """取外设标准的规则 id 清单（供模板 meta 标注）。"""
        std = self._standards.get(peripheral.lower())
        if not std:
            return []
        scene_rules = (std.get("scenes") or {}).get(scene, {})
        return [str(r.get("id")) for r in scene_rules.get("rules", [])]


def adapt_params(template_id: str, params: dict[str, Any], chip: str = DEFAULT_CHIP) -> dict[str, Any]:
    """便捷入口：按芯片肖像补全模板参数。"""
    return ChipPortraitAdapter(chip=chip).fill_params(template_id, params)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    adapter = ChipPortraitAdapter()
    print("芯片:", adapter.get_chip_name(), "| 主频:", adapter.get_max_clock_mhz(), "MHz")
    print("UART1 引脚:", adapter.get_default_pins("USART", "1"))
    print("USART1 AF:", adapter.get_af_number("USART", "1"))
    print("补全 uart_print:", adapter.fill_params("uart_print", {"uart_instance": "1"}))
    print("支持 UART:", adapter.supports_peripheral("UART"))
    print("UART 规则:", adapter.get_standard_rules("uart", "init")[:3])
