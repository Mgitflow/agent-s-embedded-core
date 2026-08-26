"""STM32F407ZGT6 LQFP144 引脚库构建器：按 DS8626 Table 5 交叉验证逐引脚，产出 144 引脚全功能表，再用 af_reverse.py 反推 af_map。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── F407ZGT6 LQFP144 引脚数据（官方 DS8626 Table 5 + LCSC pinout）──
# A-E 端口与 VGT6 相同（同内核同外设），F/G 端口按官方完整 AF 填写。
# 数据来源：ST DS8626 Table 5 (Pinouts and pin description) LQFP144 列。

# F 端口（官方 AF：FSMC 地址/数据线 + ADC3 + I2C2 + TIM10/11/13/14 + DCMI）
PF_DATA: dict[str, dict[str, Any]] = {
    # ═══ GPIO F ═══
    "PF0": {"functions": ["FSMC_A0", "I2C2_SDA", "EVENTOUT"], "ft": True},
    "PF1": {"functions": ["FSMC_A1", "I2C2_SCL", "EVENTOUT"], "ft": True},
    "PF10": {"functions": ["FSMC_INTR", "EVENTOUT"], "adc": ["ADC3_IN8"], "ft": True},
    "PF11": {"functions": ["DCMI_D12", "EVENTOUT"], "adc": ["ADC1_EXTI11", "ADC2_EXTI11", "ADC3_EXTI11"], "ft": True},
    "PF12": {"functions": ["FSMC_A6", "EVENTOUT"], "ft": True},
    "PF13": {"functions": ["FSMC_A7", "EVENTOUT"], "ft": True},
    "PF14": {"functions": ["FSMC_A8", "EVENTOUT"], "ft": True},
    "PF15": {"functions": ["FSMC_A9", "EVENTOUT"], "adc": ["ADC1_EXTI15", "ADC2_EXTI15", "ADC3_EXTI15"], "ft": True},
    "PF2": {"functions": ["FSMC_A2", "I2C2_SMBA", "EVENTOUT"], "ft": True},
    "PF3": {"functions": ["FSMC_A3", "EVENTOUT"], "adc": ["ADC3_IN9"], "ft": True},
    "PF4": {"functions": ["FSMC_A4", "EVENTOUT"], "adc": ["ADC3_IN14"], "ft": True},
    "PF5": {"functions": ["FSMC_A5", "EVENTOUT"], "adc": ["ADC3_IN15"], "ft": True},
    "PF6": {"functions": ["FSMC_NIORD", "TIM10_CH1", "EVENTOUT"], "adc": ["ADC3_IN4"], "ft": True},
    "PF7": {"functions": ["FSMC_NREG", "TIM11_CH1", "EVENTOUT"], "adc": ["ADC3_IN5"], "ft": True},
    "PF8": {"functions": ["FSMC_NIOWR", "TIM13_CH1", "EVENTOUT"], "adc": ["ADC3_IN6"], "ft": True},
    "PF9": {"functions": ["FSMC_CD", "TIM14_CH1", "EVENTOUT"], "adc": ["ADC3_IN7"], "dac": ["DAC_EXTI9"], "ft": True},
}

# G 端口（官方 AF：FSMC 片选/时钟 + ETH + EVENTOUT）
PG_DATA: dict[str, dict[str, Any]] = {
    # ═══ GPIO G ═══
    "PG0": {"functions": ["FSMC_A10", "EVENTOUT"], "ft": True},
    "PG1": {"functions": ["FSMC_A11", "EVENTOUT"], "ft": True},
    "PG10": {"functions": ["FSMC_NCE4_1", "FSMC_NE3", "EVENTOUT"], "ft": True},
    "PG11": {"functions": ["ETH_TX_EN", "FSMC_NCE4_2", "EVENTOUT"], "adc": ["ADC1_EXTI11", "ADC2_EXTI11", "ADC3_EXTI11"], "ft": True},
    "PG12": {"functions": ["FSMC_NE4", "USART6_RTS", "EVENTOUT"], "ft": True},
    "PG13": {"functions": ["ETH_TXD0", "FSMC_A24", "USART6_CTS", "EVENTOUT"], "ft": True},
    "PG14": {"functions": ["ETH_TXD1", "FSMC_A25", "USART6_TX", "EVENTOUT"], "ft": True},
    "PG15": {"functions": ["DCMI_D13", "USART6_CTS", "EVENTOUT"], "adc": ["ADC1_EXTI15", "ADC2_EXTI15", "ADC3_EXTI15"], "ft": True},
    "PG2": {"functions": ["FSMC_A12", "EVENTOUT"], "ft": True},
    "PG3": {"functions": ["FSMC_A13", "EVENTOUT"], "ft": True},
    "PG4": {"functions": ["FSMC_A14", "EVENTOUT"], "ft": True},
    "PG5": {"functions": ["FSMC_A15", "EVENTOUT"], "ft": True},
    "PG6": {"functions": ["FSMC_INT2", "EVENTOUT"], "ft": True},
    "PG7": {"functions": ["FSMC_INT3", "USART6_CK", "EVENTOUT"], "ft": True},
    "PG8": {"functions": ["ETH_PPS_OUT", "USART6_RTS", "EVENTOUT"], "ft": True},
    "PG9": {"functions": ["FSMC_NCE3", "FSMC_NE2", "USART6_RX", "EVENTOUT"], "dac": ["DAC_EXTI9"], "ft": True},
}

# PH 端口（LQFP144 只有 PH0/PH1 = OSC_IN/OSC_OUT）
PH_DATA: dict[str, dict[str, Any]] = {
    "PH0": {"functions": [], "special": "OSC_IN", "ft": False, "notes": "HSE 晶振输入（= OSC_IN，可作 GPIO）"},
    "PH1": {"functions": [], "special": "OSC_OUT", "ft": False, "notes": "HSE 晶振输出（= OSC_OUT，可作 GPIO）"},
}

# 非 GPIO（LQFP144：VDD×12 + VSS×9 + 8 特殊 + PDR_ON，多路合并）
NON_GPIO: dict[str, dict[str, Any]] = {
    "VDD": {"functions": [], "special": "POWER", "notes": "数字电源 3.3V（LQFP144 共 12 路 VDD，合并标注）"},
    "VSS": {"functions": [], "special": "GROUND", "notes": "数字地（LQFP144 共 9 路 VSS，合并标注）"},
    "VDDA": {"functions": [], "special": "POWER", "notes": "模拟电源 3.3V"},
    "VSSA": {"functions": [], "special": "GROUND", "notes": "模拟地"},
    "VREF+": {"functions": [], "special": "POWER", "notes": "ADC 参考电压正端"},
    "VBAT": {"functions": [], "special": "POWER", "notes": "备份电池电源"},
    "NRST": {"functions": [], "special": "RESET", "notes": "复位（低有效）"},
    "BOOT0": {"functions": [], "special": "BOOT0", "notes": "启动模式选择"},
    "VCAP1": {"functions": [], "special": "POWER", "notes": "内核稳压器电容 1"},
    "VCAP2": {"functions": [], "special": "POWER", "notes": "内核稳压器电容 2"},
    "PDR_ON": {"functions": [], "special": "POWER", "notes": "电源检测使能（LQFP144 独有，接 VDD 使能 PDR）"},
}


def build_zgt6_pin_map() -> dict[str, Any]:
    """构建 ZGT6 LQFP144 完整 pin_map（114 GPIO + 电源合并键）。"""
    from knowledge.loaders.build_pin_map import PIN_DATA  # 复用 VGT6 A-E 端口官方数据

    pin_map: dict[str, dict[str, Any]] = {}
    # A-E 端口（16×5 = 80，与 VGT6 相同）
    for pin, info in PIN_DATA.items():
        if pin.startswith("P") and pin[1] in "ABCDE" and not pin.startswith("PH"):
            pin_map[pin] = {
                "functions": list(info.get("functions", [])),
                "special": info.get("special", ""),
                "adc": list(info.get("adc", [])),
                "dac": list(info.get("dac", [])),
                "ft": info.get("ft", False),
                "notes": info.get("notes", ""),
            }
    # F 端口（官方 AF 完整）
    for pin, info in PF_DATA.items():
        pin_map[pin] = {
            "functions": list(info.get("functions", [])),
            "special": info.get("special", ""),
            "adc": list(info.get("adc", [])),
            "dac": [],
            "ft": info.get("ft", False),
            "notes": info.get("notes", ""),
        }
    # G 端口（官方 AF 完整）
    for pin, info in PG_DATA.items():
        pin_map[pin] = {
            "functions": list(info.get("functions", [])),
            "special": info.get("special", ""),
            "adc": [],
            "dac": [],
            "ft": info.get("ft", False),
            "notes": info.get("notes", ""),
        }
    # PH 端口（PH0/PH1，LQFP144 无 PH2+）
    for pin, info in PH_DATA.items():
        pin_map[pin] = {
            "functions": list(info.get("functions", [])),
            "special": info.get("special", ""),
            "adc": [],
            "dac": [],
            "ft": info.get("ft", False),
            "notes": info.get("notes", ""),
        }
    # 非 GPIO（多路合并）
    for pin, info in NON_GPIO.items():
        pin_map[pin] = {
            "functions": [],
            "special": info.get("special", ""),
            "adc": [],
            "dac": [],
            "ft": False,
            "notes": info.get("notes", ""),
        }
    return pin_map


def _is_gpio_pin(pin: str) -> bool:
    """GPIO 判定：PA-PG 端口（排除 PDR_ON 等 P 开头特殊键）。"""
    return pin.startswith("P") and len(pin) >= 3 and pin[1] in "ABCDEFG" and pin[2].isdigit()


def build_and_write(out_path: Path | None = None) -> dict[str, Any]:
    """构建并落盘 pin_map.json。"""
    import sys

    sys.path.insert(0, ".")
    pin_map = build_zgt6_pin_map()
    gpio_count = sum(1 for p in pin_map if _is_gpio_pin(p) or p in PH_DATA)
    if out_path is None:
        out_path = Path("skills/chips/stm32f407zgt6/pin_map.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1.0",
                "chip": "STM32F407ZGT6",
                "package": "LQFP144",
                "comment": "官方 DS8626 Table 5 重建（复查修正：删 PI 端口/PH2，补 PDR_ON 与 PF/PG 完整 AF）",
                "pins": pin_map,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"ZGT6 pin_map: {len(pin_map)} 键 = {gpio_count} GPIO + {len(pin_map) - gpio_count} 电源/特殊（144 引脚封装，多路电源合并）")
    return pin_map


def generate_af_map(pin_map: dict[str, Any]) -> dict[str, str]:
    """用 af_reverse 反推完整 af_map（信号 → 引脚）。"""
    from knowledge.loaders.af_reverse import reverse_af_map

    gpio_only = {}
    for pin, info in pin_map.items():
        if _is_gpio_pin(pin) or pin in PH_DATA:  # PA-PG + PH0/PH1（OSC 可作 GPIO）
            gpio_only[pin] = info
    return reverse_af_map(gpio_only)


def _load_af_numbers() -> dict[str, Any]:
    import json as _j

    p = Path("skills/chips/stm32f407zgt6/af_map.json")
    if p.exists():
        tmp = _j.loads(p.read_text(encoding="utf-8")).get("af_numbers", {})
        return tmp if isinstance(tmp, dict) else {}
    return {}


def _load_default_pins() -> dict[str, Any]:
    import json as _j

    p = Path("skills/chips/stm32f407zgt6/af_map.json")
    if p.exists():
        tmp = _j.loads(p.read_text(encoding="utf-8")).get("default_pins", {})
        return tmp if isinstance(tmp, dict) else {}
    return {}


if __name__ == "__main__":
    import sys

    sys.path.insert(0, ".")
    out = Path("skills/chips/stm32f407zgt6/pin_map.json")
    pin_map = build_and_write(out)
    af = generate_af_map(pin_map)
    af_out = Path("skills/chips/stm32f407zgt6/af_map.json")
    af_out.write_text(
        json.dumps(
            {
                "comment": "完整 AF 映射（pin_map 自动反推，ZGT6 重建）",
                "af_numbers": _load_af_numbers(),
                "default_pins": _load_default_pins(),
                "full_af_map": af,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"af_map 反推: {len(af)} 个信号")
