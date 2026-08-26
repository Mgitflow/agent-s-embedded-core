"""从 CubeMX GPIO IP 定义提取 f103 的 AFIO 重映射表（remap_map.json 材料源）。

「F103 AFIO 重映射」遗漏：F1 系列没有每个引脚的 AF 编号（AF0-AF15），
外设引脚复用靠 AFIO_MAPR 寄存器做「重映射（remap）」——外设有默认映射引脚组，
通过重映射位切换到另一组引脚。CubeMX 的 mcu 引脚数据库（db/mcu/STM32F103C(8-B)Tx.xml）
只列「哪些引脚有某信号」，不区分默认/重映射；真正的重映射语义在 GPIO IP 定义
（db/mcu/IP/GPIO-STM32F103x8_gpio_v1_0_Modes.xml）的 RemapBlock 里：

    GPIO_Pin(引脚) → PinSignal(信号) → RemapBlock(Name/DefaultRemap)
                                        └── SpecificParameter → PossibleValue(__HAL_AFIO_REMAP_XXX 宏)

本脚本解析它，生成 {信号: {引脚: [重映射宏列表]}}：
  - 宏列表为空 []  = 默认映射（引脚复位即可用，无需 AFIO 配置）
  - 宏列表非空     = 重映射引脚（需调用对应 __HAL_AFIO_REMAP_XXX 宏启用）
按芯片 pin_map 过滤掉封装上不存在的引脚（f103c8t6 LQFP48 无 PD2+，只留 PA/PB/PC13-15/PD0-1）。

纯函数 + 落盘生成 remap_map.json；材料驱动，供 chip_portrait_adapter / default_pins 自动提炼复用。
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# f103c8t6（中容量 64KB）对应的 CubeMX GPIO IP 定义
CUBEMX_GPIO_IP = "E:/Soft/STM32CubeMX/db/mcu/IP/GPIO-STM32F103x8_gpio_v1_0_Modes.xml"

# 宏影响面排序（PARTIAL < ENABLE）：生成器选宏时优先影响面小的（不连带重映射其他通道）
_MACRO_RANK = {
    "PARTIAL_1": 0, "PARTIAL_2": 1, "PARTIAL": 2, "ENABLE": 3,
}


def _strip(tag: str) -> str:
    return tag.split("}")[-1]


def _sort_macros(macros: list[str]) -> list[str]:
    """宏按影响面排序（PARTIAL 优先），稳定去重。"""
    def key(m: str) -> tuple[int, str]:
        rank = 99
        for kw, r in _MACRO_RANK.items():
            if kw in m:
                rank = r
                break
        return (rank, m)
    return sorted(set(macros), key=key)


def parse_afio_remap(xml_path: str = CUBEMX_GPIO_IP) -> dict[str, dict[str, list[str]]]:
    """解析 CubeMX GPIO IP，返回 {信号: {引脚: [重映射宏列表]}}（空列表=默认映射）。"""
    root = ET.parse(xml_path).getroot()
    remap: dict[str, dict[str, list[str]]] = {}
    for pin in root.iter():
        if _strip(pin.tag) != "GPIO_Pin":
            continue
        pname = pin.get("Name", "")
        m = re.match(r"^(P[A-G]\d+)", pname)  # 去 -WKUP 等后缀，Name 已含端口前缀
        if not m:
            continue
        fullpin = m.group(1)
        for sig in pin.findall("*"):
            if _strip(sig.tag) != "PinSignal":
                continue
            sname = sig.get("Name", "")
            blocks: list[tuple[bool, list[str]]] = []  # (是否默认块, 宏列表)
            for rb in sig.findall("*"):
                if _strip(rb.tag) != "RemapBlock":
                    continue
                is_default = rb.get("DefaultRemap") == "true"
                macros: list[str] = []
                for sp in rb.findall("*"):
                    if _strip(sp.tag) != "SpecificParameter":
                        continue
                    for pv in sp.findall("*"):
                        if _strip(pv.tag) == "PossibleValue" and pv.text:
                            macros.append(pv.text.strip())
                blocks.append((is_default, macros))
            # 关键语义（TIM1 PARTIAL 只移部分通道，CH1-CH4 不动）：
            # 引脚若属于任一「默认映射块」→ 默认引脚（复位即可用，无需 AFIO），
            # 即使它同时也出现在某 PARTIAL 块（该块不改变它的通道）也仍是默认。
            # 只有「不属于任何默认块」的引脚才是真正的重映射引脚。
            has_default = any(d for d, _ in blocks)
            if has_default:
                remap.setdefault(sname, {})[fullpin] = []
            else:
                all_macros = [m for _, ms in blocks for m in ms]
                remap.setdefault(sname, {})[fullpin] = _sort_macros(all_macros)
    return remap


def filter_by_pin_map(
    remap: dict[str, dict[str, list[str]]], pin_map: dict[str, Any]
) -> dict[str, dict[str, list[str]]]:
    """按芯片 pin_map 过滤掉封装上不存在的引脚（f103c8t6 LQFP48 无 PD2+）。"""
    valid = {p.upper() for p in (pin_map.get("pins") or {})}
    out: dict[str, dict[str, list[str]]] = {}
    for sig, pins in remap.items():
        kept = {p: m for p, m in pins.items() if p.upper() in valid}
        if kept:
            out[sig] = kept
    return out


def build_remap_map(
    chip: str, pin_map_path: Path, xml_path: str = CUBEMX_GPIO_IP
) -> dict[str, Any]:
    """构建完整 remap_map 材料（含 schema/来源注解）。"""
    remap = parse_afio_remap(xml_path)
    pm = json.loads(pin_map_path.read_text(encoding="utf-8"))
    filtered = filter_by_pin_map(remap, pm)
    return {
        "schema_version": "1.0.0",
        "chip": chip,
        "source": Path(xml_path).name,
        "note": "AFIO 重映射表：宏列表为空=默认映射（无需 AFIO 配置）；非空=需调用对应 __HAL_AFIO_REMAP_XXX 宏",
        "remap": {k: filtered[k] for k in sorted(filtered)},
    }


def derive_default_pins(
    remap: dict[str, dict[str, list[str]]], full_af_map: dict[str, str]
) -> dict[str, dict[str, str]]:
    """从 remap_map + full_af_map 提炼 default_pins（外设 → {role: 默认引脚}）。

    「default_pins 手工维护 → 自动提炼」：f103 的默认引脚是硬件决定的
    （AFIO 默认映射），remap_map 里有权威数据，可完全自动提炼，不再手工维护（手写照搬
    易错，如 g431 I2C 照搬 f407）。

    规则：
      - 有重映射的信号（在 remap 里）→ 默认 = 宏列表为空的引脚（硬件默认映射）
      - 无重映射的信号（不在 remap 里）→ 默认 = full_af_map 的唯一引脚（f103 无 remap
        的外设信号都是单引脚，如 SPI2/I2C2）
      - 过滤 RTC/USB 等非外设信号（不进 default_pins）
    """
    result: dict[str, dict[str, str]] = {}
    for sig, pins_str in full_af_map.items():
        pins = [p for p in pins_str.split("/") if p]
        if "_" not in sig:
            continue
        peri, role = sig.rsplit("_", 1)  # USART1_TX → USART1 + TX
        if peri.startswith("RTC") or peri.startswith("USB"):
            continue
        if sig in remap:
            defaults = [p for p, m in remap[sig].items() if not m]
            if not defaults:
                continue
            default_pin = sorted(defaults)[0]
        else:
            default_pin = pins[0]
        result.setdefault(peri, {})[role.lower()] = default_pin
    return result


def write_remap_map(chip_dir: Path, chip: str, xml_path: str = CUBEMX_GPIO_IP) -> Path:
    """落盘 remap_map.json 到芯片画像目录。"""
    pin_map_path = chip_dir / "pin_map.json"
    data = build_remap_map(chip, pin_map_path, xml_path)
    out = chip_dir / "remap_map.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def update_af_map_default_pins(chip_dir: Path) -> dict[str, dict[str, str]]:
    """用 remap_map + full_af_map 自动提炼 default_pins，写回 af_map.json（替代手工维护）。"""
    remap = json.loads((chip_dir / "remap_map.json").read_text(encoding="utf-8"))["remap"]
    af_path = chip_dir / "af_map.json"
    af = json.loads(af_path.read_text(encoding="utf-8"))
    full_af_map = af.get("full_af_map") or {}
    default_pins = derive_default_pins(remap, full_af_map)
    af["default_pins"] = default_pins
    af_path.write_text(json.dumps(af, ensure_ascii=False, indent=2), encoding="utf-8")
    return default_pins


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    chip_dir = Path("skills/chips/stm32f103c8t6")
    out = write_remap_map(chip_dir, "STM32F103C8T6")
    data = json.loads(out.read_text(encoding="utf-8"))
    remap = data["remap"]
    n_default = sum(1 for pins in remap.values() for m in pins.values() if not m)
    n_remap = sum(1 for pins in remap.values() for m in pins.values() if m)
    print(f"remap_map.json 已生成: {out}")
    print(f"信号数: {len(remap)} | 默认映射引脚: {n_default} | 重映射引脚: {n_remap}")
    # 提炼 default_pins 写回 af_map.json
    dp = update_af_map_default_pins(chip_dir)
    print(f"default_pins 自动提炼: {len(dp)} 外设 → af_map.json 已更新")
    for peri in sorted(dp):
        print(f"  {peri}: {dp[peri]}")
    # 打印重映射引脚（非默认）
    print("重映射引脚（需 AFIO 宏）:")
    for sig, pins in sorted(remap.items()):
        for p, macros in sorted(pins.items()):
            if macros:
                print(f"  {sig:14s} {p:5s} -> {', '.join(macros)}")
