"""F407VGT6 LQFP100 引脚库构建器：按数据手册 Table 6 逐引脚交叉验证，产出 pin_map.json 全功能表，再用 af_reverse.py 反推 af_map。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── F407VGT6 LQFP100 引脚数据（数据手册 Table 6）──
# functions = 该引脚所有复用功能（AF + 特殊）
# adc/dac = 模拟通道；special = 特殊功能（复位/时钟/调试/电源）
PIN_DATA: dict[str, dict[str, Any]] = {
    # ═══ GPIO A ═══
    "PA0": {"functions": ["ETH_CRS", "TIM2_CH1", "TIM2_ETR", "TIM5_CH1", "TIM8_ETR", "UART4_TX", "USART2_CTS", "EVENTOUT"], "adc": ["ADC1_IN0", "ADC2_IN0", "ADC3_IN0"], "special": "WKUP", "ft": True, "notes": "带 WKUP 唤醒功能"},
    "PA1": {"functions": ["ETH_REF_CLK", "ETH_RX_CLK", "TIM2_CH2", "TIM5_CH2", "UART4_RX", "USART2_RTS", "EVENTOUT"], "adc": ["ADC1_IN1", "ADC2_IN1", "ADC3_IN1"], "ft": True},
    "PA10": {"functions": ["DCMI_D1", "TIM1_CH3", "USART1_RX", "USB_OTG_FS_ID", "EVENTOUT"], "ft": True},
    "PA11": {"functions": ["CAN1_RX", "TIM1_CH4", "USART1_CTS", "USB_OTG_FS_DM", "EVENTOUT"], "adc": ["ADC1_EXTI11", "ADC2_EXTI11", "ADC3_EXTI11"], "ft": True},
    "PA12": {"functions": ["CAN1_TX", "TIM1_ETR", "USART1_RTS", "USB_OTG_FS_DP", "EVENTOUT"], "ft": True},
    "PA13": {"functions": [], "special": "SWDIO", "ft": True, "notes": "SWD 调试数据线（默认）"},
    "PA14": {"functions": [], "special": "SWCLK", "ft": True, "notes": "SWD 调试时钟（默认）"},
    "PA15": {"functions": ["I2S3_WS", "SPI1_NSS", "SPI3_NSS", "TIM2_CH1", "TIM2_ETR", "EVENTOUT"], "adc": ["ADC1_EXTI15", "ADC2_EXTI15", "ADC3_EXTI15"], "special": "JTDI", "ft": True, "notes": "JTAG TDI（默认）"},
    "PA2": {"functions": ["ETH_MDIO", "TIM2_CH3", "TIM5_CH3", "TIM9_CH1", "USART2_TX", "EVENTOUT"], "adc": ["ADC1_IN2", "ADC2_IN2", "ADC3_IN2"], "ft": True},
    "PA3": {"functions": ["ETH_COL", "TIM2_CH4", "TIM5_CH4", "TIM9_CH2", "USART2_RX", "USB_OTG_HS_ULPI_D0", "EVENTOUT"], "adc": ["ADC1_IN3", "ADC2_IN3", "ADC3_IN3"], "ft": True},
    "PA4": {"functions": ["DCMI_HSYNC", "I2S3_WS", "SPI1_NSS", "SPI3_NSS", "USART2_CK", "USB_OTG_HS_SOF", "EVENTOUT"], "adc": ["ADC1_IN4", "ADC2_IN4"], "dac": ["DAC_OUT1"], "ft": True},
    "PA5": {"functions": ["SPI1_SCK", "TIM2_CH1", "TIM2_ETR", "TIM8_CH1N", "USB_OTG_HS_ULPI_CK", "EVENTOUT"], "adc": ["ADC1_IN5", "ADC2_IN5"], "dac": ["DAC_OUT2"], "ft": True},
    "PA6": {"functions": ["DCMI_PIXCLK", "SPI1_MISO", "TIM13_CH1", "TIM1_BKIN", "TIM3_CH1", "TIM8_BKIN", "EVENTOUT"], "adc": ["ADC1_IN6", "ADC2_IN6"], "ft": True},
    "PA7": {"functions": ["ETH_CRS_DV", "ETH_RX_DV", "SPI1_MOSI", "TIM14_CH1", "TIM1_CH1N", "TIM3_CH2", "TIM8_CH1N", "EVENTOUT"], "adc": ["ADC1_IN7", "ADC2_IN7"], "ft": True},
    "PA8": {"functions": ["I2C3_SCL", "TIM1_CH1", "USART1_CK", "USB_OTG_FS_SOF", "EVENTOUT"], "special": "MCO1", "ft": True, "notes": "主时钟输出 1"},
    "PA9": {"functions": ["DCMI_D0", "I2C3_SMBA", "TIM1_CH2", "USART1_TX", "USB_OTG_FS_VBUS", "EVENTOUT"], "dac": ["DAC_EXTI9"], "ft": True},

    # ═══ GPIO B ═══
    "PB0": {"functions": ["ETH_RXD2", "TIM1_CH2N", "TIM3_CH3", "TIM8_CH2N", "USB_OTG_HS_ULPI_D1", "EVENTOUT"], "adc": ["ADC1_IN8", "ADC2_IN8"], "ft": True},
    "PB1": {"functions": ["ETH_RXD3", "TIM1_CH3N", "TIM3_CH4", "TIM8_CH3N", "USB_OTG_HS_ULPI_D2", "EVENTOUT"], "adc": ["ADC1_IN9", "ADC2_IN9"], "ft": True},
    "PB10": {"functions": ["ETH_RX_ER", "I2C2_SCL", "I2S2_CK", "SPI2_SCK", "TIM2_CH3", "USART3_TX", "USB_OTG_HS_ULPI_D3", "EVENTOUT"], "ft": True},
    "PB11": {"functions": ["ETH_TX_EN", "I2C2_SDA", "TIM2_CH4", "USART3_RX", "USB_OTG_HS_ULPI_D4", "EVENTOUT"], "adc": ["ADC1_EXTI11", "ADC2_EXTI11", "ADC3_EXTI11"], "ft": True},
    "PB12": {"functions": ["CAN2_RX", "ETH_TXD0", "I2C2_SMBA", "I2S2_WS", "SPI2_NSS", "TIM1_BKIN", "USART3_CK", "USB_OTG_HS_ID", "USB_OTG_HS_ULPI_D5", "EVENTOUT"], "ft": True},
    "PB13": {"functions": ["CAN2_TX", "ETH_TXD1", "I2S2_CK", "SPI2_SCK", "TIM1_CH1N", "USART3_CTS", "USB_OTG_HS_ULPI_D6", "USB_OTG_HS_VBUS", "EVENTOUT"], "ft": True},
    "PB14": {"functions": ["I2S2_ext_SD", "SPI2_MISO", "TIM12_CH1", "TIM1_CH2N", "TIM8_CH2N", "USART3_RTS", "USB_OTG_HS_DM", "EVENTOUT"], "ft": True},
    "PB15": {"functions": ["I2S2_SD", "RTC_REFIN", "SPI2_MOSI", "TIM12_CH2", "TIM1_CH3N", "TIM8_CH3N", "USB_OTG_HS_DP", "EVENTOUT"], "adc": ["ADC1_EXTI15", "ADC2_EXTI15", "ADC3_EXTI15"], "ft": True},
    "PB2": {"functions": ["EVENTOUT"], "special": "BOOT1", "ft": True, "notes": "启动模式选择 BOOT1"},
    "PB3": {"functions": ["I2S3_CK", "SPI1_SCK", "SPI3_SCK", "TIM2_CH2", "EVENTOUT"], "special": "JTDO", "ft": True, "notes": "JTAG TDO（默认）"},
    "PB4": {"functions": ["I2S3_ext_SD", "SPI1_MISO", "SPI3_MISO", "TIM3_CH1", "EVENTOUT"], "special": "NJTRST", "ft": True, "notes": "JTAG NRST（默认）"},
    "PB5": {"functions": ["CAN2_RX", "DCMI_D10", "ETH_PPS_OUT", "I2C1_SMBA", "I2S3_SD", "SPI1_MOSI", "SPI3_MOSI", "TIM3_CH2", "USB_OTG_HS_ULPI_D7", "EVENTOUT"], "ft": True},
    "PB6": {"functions": ["CAN2_TX", "DCMI_D5", "I2C1_SCL", "TIM4_CH1", "USART1_TX", "EVENTOUT"], "ft": True},
    "PB7": {"functions": ["DCMI_VSYNC", "FSMC_NL", "I2C1_SDA", "TIM4_CH2", "USART1_RX", "EVENTOUT"], "ft": True},
    "PB8": {"functions": ["CAN1_RX", "DCMI_D6", "ETH_TXD3", "I2C1_SCL", "SDIO_D4", "TIM10_CH1", "TIM4_CH3", "EVENTOUT"], "ft": True},
    "PB9": {"functions": ["CAN1_TX", "DCMI_D7", "I2C1_SDA", "I2S2_WS", "SDIO_D5", "SPI2_NSS", "TIM11_CH1", "TIM4_CH4", "EVENTOUT"], "dac": ["DAC_EXTI9"], "ft": True},

    # ═══ GPIO C ═══
    "PC0": {"functions": ["USB_OTG_HS_ULPI_STP", "EVENTOUT"], "adc": ["ADC1_IN10", "ADC2_IN10", "ADC3_IN10"], "ft": True},
    "PC1": {"functions": ["ETH_MDC", "EVENTOUT"], "adc": ["ADC1_IN11", "ADC2_IN11", "ADC3_IN11"], "ft": True},
    "PC10": {"functions": ["DCMI_D8", "I2S3_CK", "SDIO_D2", "SPI3_SCK", "UART4_TX", "USART3_TX", "EVENTOUT"], "ft": True},
    "PC11": {"functions": ["DCMI_D4", "I2S3_ext_SD", "SDIO_D3", "SPI3_MISO", "UART4_RX", "USART3_RX", "EVENTOUT"], "adc": ["ADC1_EXTI11", "ADC2_EXTI11", "ADC3_EXTI11"], "ft": True},
    "PC12": {"functions": ["DCMI_D9", "I2S3_SD", "SDIO_CK", "SPI3_MOSI", "UART5_TX", "USART3_CK", "EVENTOUT"], "ft": True},
    "PC13": {"functions": ["RTC_AF1", "EVENTOUT"], "special": "RTC_TAMP/TS/OUT", "ft": True, "notes": "RTC 闹钟/入侵/输出（备份域）"},
    "PC14": {"functions": [], "special": "OSC32_IN", "ft": True, "notes": "32.768kHz 晶振输入（备份域）"},
    "PC15": {"functions": [], "adc": ["ADC1_EXTI15", "ADC2_EXTI15", "ADC3_EXTI15"], "special": "OSC32_OUT", "ft": True, "notes": "32.768kHz 晶振输出（备份域）"},
    "PC2": {"functions": ["ETH_TXD2", "I2S2_ext_SD", "SPI2_MISO", "USB_OTG_HS_ULPI_DIR", "EVENTOUT"], "adc": ["ADC1_IN12", "ADC2_IN12", "ADC3_IN12"], "ft": True},
    "PC3": {"functions": ["ETH_TX_CLK", "I2S2_SD", "SPI2_MOSI", "USB_OTG_HS_ULPI_NXT", "EVENTOUT"], "adc": ["ADC1_IN13", "ADC2_IN13", "ADC3_IN13"], "ft": True},
    "PC4": {"functions": ["ETH_RXD0", "EVENTOUT"], "adc": ["ADC1_IN14", "ADC2_IN14"], "ft": True},
    "PC5": {"functions": ["ETH_RXD1", "EVENTOUT"], "adc": ["ADC1_IN15", "ADC2_IN15"], "ft": True},
    "PC6": {"functions": ["DCMI_D0", "I2S2_MCK", "SDIO_D6", "TIM3_CH1", "TIM8_CH1", "USART6_TX", "EVENTOUT"], "ft": True},
    "PC7": {"functions": ["DCMI_D1", "I2S3_MCK", "SDIO_D7", "TIM3_CH2", "TIM8_CH2", "USART6_RX", "EVENTOUT"], "ft": True},
    "PC8": {"functions": ["DCMI_D2", "SDIO_D0", "TIM3_CH3", "TIM8_CH3", "USART6_CK", "EVENTOUT"], "ft": True},
    "PC9": {"functions": ["DCMI_D3", "I2C3_SDA", "I2S_CKIN", "SDIO_D1", "TIM3_CH4", "TIM8_CH4", "EVENTOUT"], "dac": ["DAC_EXTI9"], "special": "MCO2", "ft": True, "notes": "主时钟输出 2"},

    # ═══ GPIO D ═══
    "PD0": {"functions": ["CAN1_RX", "FSMC_D2", "FSMC_DA2", "EVENTOUT"], "ft": True},
    "PD1": {"functions": ["CAN1_TX", "FSMC_D3", "FSMC_DA3", "EVENTOUT"], "ft": True},
    "PD10": {"functions": ["FSMC_D15", "FSMC_DA15", "USART3_CK", "EVENTOUT"], "ft": True},
    "PD11": {"functions": ["FSMC_A16", "FSMC_CLE", "USART3_CTS", "EVENTOUT"], "adc": ["ADC1_EXTI11", "ADC2_EXTI11", "ADC3_EXTI11"], "ft": True},
    "PD12": {"functions": ["FSMC_A17", "FSMC_ALE", "TIM4_CH1", "USART3_RTS", "EVENTOUT"], "ft": True},
    "PD13": {"functions": ["FSMC_A18", "TIM4_CH2", "EVENTOUT"], "ft": True},
    "PD14": {"functions": ["FSMC_D0", "FSMC_DA0", "TIM4_CH3", "EVENTOUT"], "ft": True},
    "PD15": {"functions": ["FSMC_D1", "FSMC_DA1", "TIM4_CH4", "EVENTOUT"], "adc": ["ADC1_EXTI15", "ADC2_EXTI15", "ADC3_EXTI15"], "ft": True},
    "PD2": {"functions": ["DCMI_D11", "SDIO_CMD", "TIM3_ETR", "UART5_RX", "EVENTOUT"], "ft": True},
    "PD3": {"functions": ["FSMC_CLK", "USART2_CTS", "EVENTOUT"], "ft": True},
    "PD4": {"functions": ["FSMC_NOE", "USART2_RTS", "EVENTOUT"], "ft": True},
    "PD5": {"functions": ["FSMC_NWE", "USART2_TX", "EVENTOUT"], "ft": True},
    "PD6": {"functions": ["FSMC_NWAIT", "USART2_RX", "EVENTOUT"], "ft": True},
    "PD7": {"functions": ["FSMC_NCE2", "FSMC_NE1", "USART2_CK", "EVENTOUT"], "ft": True},
    "PD8": {"functions": ["FSMC_D13", "FSMC_DA13", "USART3_TX", "EVENTOUT"], "ft": True},
    "PD9": {"functions": ["FSMC_D14", "FSMC_DA14", "USART3_RX", "EVENTOUT"], "dac": ["DAC_EXTI9"], "ft": True},

    # ═══ GPIO E ═══
    "PE0": {"functions": ["DCMI_D2", "FSMC_NBL0", "TIM4_ETR", "EVENTOUT"], "ft": True},
    "PE1": {"functions": ["DCMI_D3", "FSMC_NBL1", "EVENTOUT"], "ft": True},
    "PE10": {"functions": ["FSMC_D7", "FSMC_DA7", "TIM1_CH2N", "EVENTOUT"], "ft": True},
    "PE11": {"functions": ["FSMC_D8", "FSMC_DA8", "TIM1_CH2", "EVENTOUT"], "adc": ["ADC1_EXTI11", "ADC2_EXTI11", "ADC3_EXTI11"], "ft": True},
    "PE12": {"functions": ["FSMC_D9", "FSMC_DA9", "TIM1_CH3N", "EVENTOUT"], "ft": True},
    "PE13": {"functions": ["FSMC_D10", "FSMC_DA10", "TIM1_CH3", "EVENTOUT"], "ft": True},
    "PE14": {"functions": ["FSMC_D11", "FSMC_DA11", "TIM1_CH4", "EVENTOUT"], "ft": True},
    "PE15": {"functions": ["FSMC_D12", "FSMC_DA12", "TIM1_BKIN", "EVENTOUT"], "adc": ["ADC1_EXTI15", "ADC2_EXTI15", "ADC3_EXTI15"], "ft": True},
    "PE2": {"functions": ["ETH_TXD3", "FSMC_A23", "EVENTOUT"], "special": "TRACECLK", "ft": True, "notes": "跟踪时钟"},
    "PE3": {"functions": ["FSMC_A19", "EVENTOUT"], "special": "TRACED0", "ft": True},
    "PE4": {"functions": ["DCMI_D4", "FSMC_A20", "EVENTOUT"], "special": "TRACED1", "ft": True},
    "PE5": {"functions": ["DCMI_D6", "FSMC_A21", "TIM9_CH1", "EVENTOUT"], "special": "TRACED2", "ft": True},
    "PE6": {"functions": ["DCMI_D7", "FSMC_A22", "TIM9_CH2", "EVENTOUT"], "special": "TRACED3", "ft": True},
    "PE7": {"functions": ["FSMC_D4", "FSMC_DA4", "TIM1_ETR", "EVENTOUT"], "ft": True},
    "PE8": {"functions": ["FSMC_D5", "FSMC_DA5", "TIM1_CH1N", "EVENTOUT"], "ft": True},
    "PE9": {"functions": ["FSMC_D6", "FSMC_DA6", "TIM1_CH1", "EVENTOUT"], "dac": ["DAC_EXTI9"], "ft": True},
    # ═══ 非 GPIO 引脚（电源/时钟/调试）═══
    # 官方 LQFP100（DS8626 Table 5）：100 引脚 = 82 GPIO + 18 非 GPIO。
    # 82 GPIO = PA-PE 各 16（80）+ PH0-OSC_IN + PH1-OSC_OUT（2，可作 GPIO）。
    # 18 非 GPIO = VDD×5 + VSS×4 + VDDA + VSSA + VREF+ + VREF- + VBAT +
    #              NRST + BOOT0 + VCAP1 + VCAP2。多路电源合并为单键 + notes 标注。
    # PH0/PH1 与 OSC_IN/OSC_OUT 是同一物理引脚（合并，2026-08-09 复查修正）。
    "VDD": {"functions": [], "special": "POWER", "notes": "数字电源 3.3V（LQFP100 共 5 路 VDD，合并标注）"},
    "VSS": {"functions": [], "special": "GROUND", "notes": "数字地（LQFP100 共 4 路 VSS，合并标注）"},
    "VDDA": {"functions": [], "special": "POWER", "notes": "模拟电源 3.3V"},
    "VSSA": {"functions": [], "special": "GROUND", "notes": "模拟地"},
    "VREF+": {"functions": [], "special": "POWER", "notes": "ADC 参考电压正端"},
    "VREF-": {"functions": [], "special": "POWER", "notes": "ADC 参考电压负端"},
    "VBAT": {"functions": [], "special": "POWER", "notes": "备份电池电源"},
    "NRST": {"functions": [], "special": "RESET", "notes": "复位（低有效）"},
    "BOOT0": {"functions": [], "special": "BOOT0", "notes": "启动模式选择"},
    "VCAP1": {"functions": [], "special": "POWER", "notes": "内核稳压器电容 1"},
    "VCAP2": {"functions": [], "special": "POWER", "notes": "内核稳压器电容 2"},
    # PH0/PH1 = OSC_IN/OSC_OUT（F407 同一引脚双名，保留 PH 名，功能以 OSC 标注）
    "PH0": {"functions": [], "special": "OSC_IN", "ft": False, "notes": "HSE 晶振输入（= OSC_IN，可作 GPIO）"},
    "PH1": {"functions": [], "special": "OSC_OUT", "ft": False, "notes": "HSE 晶振输出（= OSC_OUT，可作 GPIO）"},
}


def build_pin_map(out_path: Path | None = None) -> dict[str, Any]:
    """构建完整 pin_map.json。"""
    pin_map = {}
    for pin, info in PIN_DATA.items():
        entry = {
            "functions": info.get("functions", []),
            "special": info.get("special", ""),
            "adc": info.get("adc", []),
            "dac": info.get("dac", []),
            "ft": info.get("ft", False),
            "notes": info.get("notes", ""),
        }
        pin_map[pin] = entry

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({"schema_version": "1.1.0", "chip": "APM32F407VGT6", "package": "LQFP100", "pins": pin_map},
                       ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return pin_map


def generate_af_map(pin_map: dict[str, Any]) -> dict[str, str]:
    """用 af_reverse 反推完整 af_map（信号 → 引脚）。"""
    from knowledge.loaders.af_reverse import reverse_af_map

    # 只保留 GPIO 引脚（去掉电源/特殊引脚）
    gpio_only = {}
    for pin, info in pin_map.items():
        if pin.startswith("P") and pin[1] in "ABCDE" and not pin.startswith("PH"):
            gpio_only[pin] = info
    return reverse_af_map(gpio_only)


def _load_af_numbers() -> dict[str, Any]:
    import json as _j
    p = Path("skills/chips/apm32f407vgt6/af_map.json")
    if p.exists():
        tmp = _j.loads(p.read_text(encoding="utf-8")).get("af_numbers", {})
        return tmp if isinstance(tmp, dict) else {}
    return {}


def _load_default_pins() -> dict[str, Any]:
    import json as _j
    p = Path("skills/chips/apm32f407vgt6/af_map.json")
    if p.exists():
        tmp = _j.loads(p.read_text(encoding="utf-8")).get("default_pins", {})
        return tmp if isinstance(tmp, dict) else {}
    return {}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    out = Path("skills/chips/apm32f407vgt6/pin_map.json")
    pin_map = build_pin_map(out)
    af = generate_af_map(pin_map)
    af_out = Path("skills/chips/apm32f407vgt6/af_map.json")
    af_out.write_text(json.dumps({"comment": "完整 AF 映射（pin_map 自动反推，2026-08-09 铺平）", "af_numbers": _load_af_numbers(), "default_pins": _load_default_pins(), "full_af_map": af}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"pin_map: {len(pin_map)} 引脚")
    print(f"af_map 反推: {len(af)} 个信号")
    gpio_count = sum(1 for p in pin_map if p.startswith('P') and p[1] in 'ABCDE' and not p.startswith('PH'))
    print(f"GPIO 引脚: {gpio_count}")
