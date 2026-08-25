"""引脚分区视图：board.json → 端口（PA/PB/…）→ 引脚 → 外设/信号 汇总。

roadmap 三期第 3 条「显式引脚分区视图」（念安 8-20 定为三期第一步，上下级底座）。

职责定位（底座，不产生副作用）：
- 二次开发依赖它：在模板上插新逻辑前，判断哪些引脚被占（不可用）、哪些空闲（可用）
- 识别套式依赖它：拽模板时，检查模板引脚与已分配引脚是否冲突（复用/跳线）

数据源：board.json（板卡层唯一真相源）的 leds / keys / debug.swd / oscillator /
onboard_peripherals，统一解析成「端口 → 引脚 → 占用者列表」。

引脚值支持多种格式（board.json 真实存在的）：
- 单引脚："PF9"、"PB14"
- 带信号："PA9(TX)"、"PC14(OSC32_IN)"
- 复合："PA2(TX)/PA3(RX)"
- 范围："PE7-PE15"（FSMC 数据线连续引脚）
"""

from __future__ import annotations

import re
from typing import Any

# 匹配 GPIO 引脚：P[A-G] + 数字，可选 -范围（-15 简写或 -PE15 完整），可选 (信号)
_PIN_PATTERN = re.compile(r"P([A-G])(\d{1,2})(?:-P?[A-G]?(\d{1,2}))?(?:\(([^)]*)\))?")

# 外设 key → 中文（渲染用）
_OWNER_CN: dict[str, str] = {
    "leds": "LED",
    "keys": "按键",
    "debug": "SWD 调试",
    "oscillator": "晶振",
    "usart": "串口",
    "spi_flash": "SPI Flash",
    "sram": "SRAM",
    "eeprom": "EEPROM",
    "imu": "六轴 IMU",
    "audio": "音频",
    "can": "CAN",
    "rs485": "RS485",
    "rs232": "RS232",
    "eth": "以太网",
    "sdio": "SD 卡",
    "lcd": "LCD",
    "camera": "摄像头",
    "buzzer": "蜂鸣器",
}

# 引脚号排序键：端口字母 + 数字（PA0 < PA1 < … < PB0 < …）
_PORT_ORDER = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]


def extract_pins(value: str) -> list[tuple[str, str | None]]:
    """从引脚字符串提取 [(pin, signal)]。

    支持：PF9 / PA9(TX) / PA9(TX)/PA10(RX) / PE7-PE15（范围展开）/
    PC14(OSC32_IN)/PC15(OSC32_OUT)。
    非 GPIO 内容（如 OSC_IN/OSC_OUT、D0-D15 前缀）自动忽略。
    """
    tokens: list[tuple[str, str | None]] = []
    for m in _PIN_PATTERN.finditer(value):
        port = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        signal = m.group(4)
        for num in range(start, end + 1):
            tokens.append((f"P{port}{num}", signal))
    return tokens


def _add_entry(
    zones: dict[str, dict[str, list[dict[str, str]]]],
    pin: str,
    owner: str,
    signal: str,
    note: str = "",
) -> None:
    """把一个 (pin → owner/signal) 写入分区表，按端口 + 引脚号归档。"""
    port = pin[1]  # "PA9" → "A"
    num = pin[2:]  # "PA9" → "9"
    zones.setdefault(port, {}).setdefault(num, []).append(
        {"owner": owner, "signal": signal, "note": note}
    )


def build_pin_zones(board: dict[str, Any]) -> dict[str, dict[str, list[dict[str, str]]]]:
    """构建分区表 {port: {pin_num: [{owner, signal, note}]}}。

    一个引脚被多个外设占用 → 列表多个元素（复用冲突，靠跳线/分时切换）。
    """
    zones: dict[str, dict[str, list[dict[str, str]]]] = {}

    # 1. 板载 LED
    for led in board.get("leds", []):
        pin = str(led.get("pin", ""))
        if pin.startswith("P") and led.get("confirmed"):
            lvl = "低电平亮" if led.get("active_level") == "low" else "高电平亮"
            _add_entry(zones, pin, "leds", str(led.get("id", "LED")), lvl)

    # 2. 板载按键（排除 NRST 复位 / BOOT0 启动选择，非可编程 GPIO）
    for key in board.get("keys", []):
        pin = str(key.get("pin", ""))
        if not pin.startswith("P"):
            continue  # NRST / BOOT0
        if key.get("confirmed"):
            lvl = "按下为低" if key.get("active_level") == "low" else "按下为高"
            _add_entry(zones, pin, "keys", str(key.get("id", "KEY")), lvl)

    # 3. SWD 调试口
    for p in board.get("debug", {}).get("swd", {}).get("pins", []):
        for pin, signal in extract_pins(str(p)):
            _add_entry(zones, pin, "debug", signal or "SWD")

    # 4. 晶振
    for osc_key in ("hse", "lse"):
        osc = board.get("oscillator", {}).get(osc_key, {})
        for pin, signal in extract_pins(str(osc.get("pins", ""))):
            _add_entry(zones, pin, "oscillator", signal or osc_key.upper())

    # 5. 板载外设（onboard_peripherals）
    for name, periph in board.get("onboard_peripherals", {}).items():
        if not isinstance(periph, dict):
            continue  # led_count / key_count / other 等非外设项
        pins = periph.get("pins")
        if isinstance(pins, dict):
            for sig, val in pins.items():
                for pin, signal in extract_pins(str(val)):
                    _add_entry(zones, pin, name, signal or sig)
        elif isinstance(pins, list):
            for val in pins:
                for pin, signal in extract_pins(str(val)):
                    _add_entry(zones, pin, name, signal or name)
        elif isinstance(periph.get("pin"), str):
            for pin, signal in extract_pins(str(periph["pin"])):
                _add_entry(zones, pin, name, signal or name)

    return zones


def occupied_pins(board: dict[str, Any]) -> set[str]:
    """所有被占引脚集合（二次开发判断空闲引脚的输入）。"""
    pins: set[str] = set()
    for port, port_pins in build_pin_zones(board).items():
        for num in port_pins:
            pins.add(f"P{port}{num}")
    return pins


def pin_owners(board: dict[str, Any]) -> dict[str, list[str]]:
    """引脚 → 占用者列表（识别套式查冲突的输入），返回 {pin: [owner,...]}。"""
    owners: dict[str, list[str]] = {}
    for port, port_pins in build_pin_zones(board).items():
        for num, entries in port_pins.items():
            owners[f"P{port}{num}"] = [e["owner"] for e in entries]
    return owners


def render_pin_zones(board: dict[str, Any]) -> str:
    """渲染成分区表文本（端口 → 引脚 → 外设:信号）。"""
    zones = build_pin_zones(board)
    lines: list[str] = []
    board_name = board.get("meta", {}).get("board_name", "未知开发板")
    lines.append(f"# 引脚分区视图：{board_name}")
    lines.append("")

    for port in _PORT_ORDER:
        port_pins = zones.get(port)
        if not port_pins:
            continue
        lines.append(f"## P{port} 区（Port {port}）")
        for num in sorted(port_pins, key=lambda n: int(n) if n.isdigit() else 999):
            entries = port_pins[num]
            pin = f"P{port}{num}"
            if len(entries) == 1:
                e = entries[0]
                owner_cn = _OWNER_CN.get(e["owner"], e["owner"])
                note = f"（{e['note']}）" if e.get("note") else ""
                lines.append(f"  {pin:<5} : {owner_cn} {e['signal']}{note}")
            else:
                # 复用冲突（跳线/分时切换）
                parts = []
                for e in entries:
                    owner_cn = _OWNER_CN.get(e["owner"], e["owner"])
                    parts.append(f"{owner_cn} {e['signal']}")
                lines.append(f"  {pin:<5} : ⚠️ 复用——{' / '.join(parts)}（跳线/分时切换）")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
