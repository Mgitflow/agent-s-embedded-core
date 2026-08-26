"""从 CubeMX 数据库 XML 全量重建 pin_map 源数据（PIN_DATA/PF_DATA/PG_DATA）。

 「写法统一根据 MX 命名」+「数据库重建补缺失」。
CubeMX 数据库（db/mcu/STM32F407Z(E-G)Tx.xml）= 单一权威材料源，本脚本解析它，
按命名前缀分类到 functions/adc/dac/special，生成 build_pin_map.py 用的 PIN_DATA 源码。

分类规则（信号名 → pin_map 字段）：
- SYS_xxx / RCC_OSC_xxx / RCC_MCO_x → special（调试/晶振/时钟输出，映射回 pin_map special 值）
- ADCx_INy → adc（独立命名，替代旧合并格式 ADC123_INx）
- DAC_OUTy → dac
- 其他（USART/SPI/I2C/TIM/CAN/SDIO/ETH/FSMC/DCMI/USB/I2S）→ functions（CubeMX 原名）

纯函数，不落盘（dry-run 输出源码文本供审查），由调用方决定是否覆盖。
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

NS = "{http://mcd.rou.st.com/modules.php?name=mcu}"
CUBEMX_XML = "E:/Soft/STM32CubeMX/db/mcu/STM32F407Z(E-G)Tx.xml"

# SYS/RCC 信号 → special 字段值（调试/晶振/时钟输出）
SPECIAL_MAP: dict[str, str] = {
    "SYS_JTMS-SWDIO": "SWDIO",
    "SYS_JTCK-SWCLK": "SWCLK",
    "SYS_JTDO-SWO": "JTDO",
    "SYS_JTRST": "NJTRST",
    "SYS_JTDI": "JTDI",
    "SYS_TRACECLK": "TRACECLK",
    "SYS_TRACED0": "TRACED0",
    "SYS_TRACED1": "TRACED1",
    "SYS_TRACED2": "TRACED2",
    "SYS_TRACED3": "TRACED3",
    "SYS_WKUP": "WKUP",
    "RCC_OSC_IN": "OSC_IN",
    "RCC_OSC_OUT": "OSC_OUT",
    "RCC_OSC32_IN": "OSC32_IN",
    "RCC_OSC32_OUT": "OSC32_OUT",
    "RCC_MCO_1": "MCO1",
    "RCC_MCO_2": "MCO2",
    # g431（G4 系列）变体：多 WKUP 引脚、单 MCO、LSCO、PVD
    "SYS_WKUP1": "WKUP",
    "SYS_WKUP2": "WKUP",
    "SYS_WKUP4": "WKUP",
    "SYS_WKUP5": "WKUP",
    "RCC_MCO": "MCO",
    "RCC_LSCO": "LSCO",
    "SYS_PVD_IN": "PVD_IN",
}

# special 值 → 附加 notes（保留探索者/手册语义）
SPECIAL_NOTES: dict[str, str] = {
    "SWDIO": "SWD 调试数据线（默认）",
    "SWCLK": "SWD 调试时钟（默认）",
    "JTDO": "JTAG TDO（默认）",
    "NJTRST": "JTAG NRST（默认）",
    "JTDI": "JTAG TDI（默认）",
    "WKUP": "带 WKUP 唤醒功能",
    "OSC_IN": "HSE 晶振输入（可作 GPIO）",
    "OSC_OUT": "HSE 晶振输出（可作 GPIO）",
    "OSC32_IN": "32.768kHz 晶振输入（备份域）",
    "OSC32_OUT": "32.768kHz 晶振输出（备份域）",
    "MCO1": "主时钟输出 1",
    "MCO2": "主时钟输出 2",
    "TRACECLK": "跟踪时钟",
    "RTC_TAMP/TS/OUT": "RTC 闹钟/入侵/输出（备份域）",
    "BOOT1": "启动模式选择 BOOT1",
}

# CubeMX Pin Name 后缀 → special 值（PA0-WKUP / PC13-ANTI_TAMP / PH0-OSC_IN 等）
PIN_SUFFIX_SPECIAL: dict[str, str] = {
    "WKUP": "WKUP",
    "ANTI_TAMP": "RTC_TAMP/TS/OUT",
    "OSC32_IN": "OSC32_IN",
    "OSC32_OUT": "OSC32_OUT",
    "OSC_IN": "OSC_IN",
    "OSC_OUT": "OSC_OUT",
    "NRST": "RESET",
    "BOOT0": "BOOT0",
}


def parse_cubemx(xml_path: str = CUBEMX_XML) -> dict[str, tuple[str, list[str]]]:
    """解析 CubeMX 数据库，返回 {pin: (后缀 special, [信号名列表])}（GPIO 占位已排除）。

    Pin Name 形如 "PA0-WKUP"/"PC14-OSC32_IN"/"PH0-OSC_IN"（带 -后缀 表示引脚默认特殊功能），
    分离出 pin（去后缀）与 suffix（特殊功能标注）。
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    result: dict[str, tuple[str, list[str]]] = {}
    for pin in root.iter(NS + "Pin"):
        name = pin.get("Name", "")
        m = re.match(r"^(P[A-G]\d+)(?:-(.+))?$", name)
        if not m:
            continue
        pin_name = m.group(1)
        suffix = m.group(2) or ""
        sigs = []
        for sig in pin.iter(NS + "Signal"):
            sn = sig.get("Name", "")
            if sn and sn != "GPIO":
                sigs.append(sn)
        result[pin_name] = (suffix, sigs)
    return result


def classify(signal: str) -> tuple[str, str] | None:
    """把 CubeMX 信号名分类到 (field, value)；返回 None 表示跳过（未知系统信号）。"""
    if signal in SPECIAL_MAP:
        return ("special", SPECIAL_MAP[signal])
    if re.match(r"^ADC\d+_(?:IN|EXTI)\d+$", signal):
        return ("adc", signal)  # ADC1_IN0 / ADC1_EXTI15 独立命名
    if signal.startswith("DAC_OUT") or signal.startswith("DAC_EXTI"):
        return ("dac", signal)  # DAC_OUT1 / DAC_EXTI9
    if signal.startswith("SYS_") or signal.startswith("RCC_"):
        return None  # 其他系统信号（不应出现在 GPIO 引脚）
    return ("functions", signal)  # 外设 AF，CubeMX 原名


def build_pin_map(cubemx: dict[str, tuple[str, list[str]]]) -> dict[str, dict[str, Any]]:
    """把 CubeMX 信号列表整理成 pin_map 数据模型。

    special 优先级：Pin Name 后缀（PIN_SUFFIX_SPECIAL）> 信号 SYS_/RCC_ 映射。
    PB2（BOOT1）CubeMX 无外设信号，手动补 special=BOOT1。
    """
    pin_map: dict[str, dict[str, Any]] = {}
    for pin, (suffix, sigs) in cubemx.items():
        functions: list[str] = []
        adc: list[str] = []
        dac: list[str] = []
        special = PIN_SUFFIX_SPECIAL.get(suffix, "")
        for sig in sigs:
            cls = classify(sig)
            if cls is None:
                continue
            field, value = cls
            if field == "functions":
                functions.append(value)
            elif field == "adc":
                adc.append(value)
            elif field == "dac":
                dac.append(value)
            elif field == "special":
                if not special:
                    special = value  # 信号里的 special 只在后缀没给时才用
        # 排序保证输出稳定（functions 按名字，adc/dac 按通道号）
        functions = sorted(set(functions))
        adc = sorted(adc, key=lambda x: int(m.group()) if (m := re.search(r"\d+", x)) else 0)
        dac = sorted(dac)
        # EVENTOUT 是所有 GPIO 都有的（CubeMX 里作为 GPIO 的 IOMode 存在，这里补回与旧版一致）
        if functions and "EVENTOUT" not in functions:
            functions.append("EVENTOUT")
        pin_map[pin] = {
            "functions": functions,
            "special": special,
            "adc": adc,
            "dac": dac,
            "ft": True,  # FT 值需另从 datasheet 核对，此处默认 True，后续可细化
            "notes": SPECIAL_NOTES.get(special, ""),
        }
    # PB2 = BOOT1（CubeMX 仅 GPIO，无外设信号，手动补启动模式）
    pin_map["PB2"] = {
        "functions": ["EVENTOUT"],
        "special": "BOOT1",
        "adc": [],
        "dac": [],
        "ft": True,
        "notes": SPECIAL_NOTES.get("BOOT1", ""),
    }
    return pin_map


def render_pin_data(pin_map: dict[str, dict[str, Any]], ports: str) -> str:
    """把 pin_map 渲染成 Python dict 源码（按端口分组，格式与 build_pin_map.py 现有 PIN_DATA 一致）。"""
    import json as _json

    lines = []
    for port in ports:
        lines.append(f"    # ═══ GPIO {port} ═══")
        for pin in sorted(pin_map):
            if pin[1] != port:
                continue
            info = pin_map[pin]
            # 字段顺序与现有 PIN_DATA 一致：functions/adc/dac/special/ft/notes
            parts = [f'"functions": {_json.dumps(info["functions"], ensure_ascii=False)}']
            if info["adc"]:
                parts.append(f'"adc": {_json.dumps(info["adc"], ensure_ascii=False)}')
            if info["dac"]:
                parts.append(f'"dac": {_json.dumps(info["dac"], ensure_ascii=False)}')
            if info["special"]:
                parts.append(f'"special": {_json.dumps(info["special"], ensure_ascii=False)}')
            parts.append(f'"ft": {info["ft"]}')
            if info["notes"]:
                parts.append(f'"notes": {_json.dumps(info["notes"], ensure_ascii=False)}')
            lines.append(f'    "{pin}": {{{", ".join(parts)}}},')
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    cubemx = parse_cubemx()
    pin_map = build_pin_map(cubemx)
    print(f"CubeMX 引脚数: {len(cubemx)}")
    print(f"重建 pin_map 引脚数: {len(pin_map)}")
    # 统计
    n_func = sum(1 for p in pin_map.values() if p["functions"])
    n_adc = sum(len(p["adc"]) for p in pin_map.values())
    n_dac = sum(len(p["dac"]) for p in pin_map.values())
    n_special = sum(1 for p in pin_map.values() if p["special"])
    print(f"含 functions: {n_func} | adc 信号: {n_adc} | dac 信号: {n_dac} | special: {n_special}")
    # 输出 A-E 端口（供 build_pin_map.py PIN_DATA）
    print("\n" + "=" * 60)
    print("A-E 端口源码（PIN_DATA）:")
    print("=" * 60)
    print(render_pin_data(pin_map, "ABCDE"))
    print("=" * 60)
    print("F-G 端口源码（PF_DATA/PG_DATA）:")
    print("=" * 60)
    print(render_pin_data(pin_map, "FG"))
