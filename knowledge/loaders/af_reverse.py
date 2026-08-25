"""af_map 自动反推工具：从 pin_map 生成信号→引脚反向映射，避免手写遗漏；纯函数无副作用，供 FcntModule/profile_manager 复用。"""
from typing import Any

# 非外设功能黑名单：这些是引脚的非 AF 复用功能，不收录到 af_map。
# 2026-08-25 重建后分两类：
# ① f407/apm32 重建后：调试/时钟/晶振已移到 pin_map special 字段，functions 里残留的非 AF
#   信号只有 EVENTOUT / RTC_AF1 / RTC_REFIN；
# ② f103/g431 未重建（旧格式）：调试/时钟信号仍在 functions，需沿用旧黑名单排除。
# 故黑名单 = 两类并集。I2S_CKIN/I2S2_MCK/I2S3_MCK 是真外设信号（I2S 主时钟），已移除不再排除。
NON_PERIPHERAL = {
    # 新格式（f407 重建后）：functions 里残留的非 AF 信号
    "EVENTOUT",     # Cortex 事件输出（所有 GPIO 的通用能力，非外设 AF）
    "RTC_AF1",      # RTC 闹钟/入侵/输出（备份域，不走 AF 复用）
    "RTC_REFIN",    # RTC 参考时钟输入（备份域，不走 AF 复用）
    # 旧格式（f103/g431 未重建）：调试/时钟信号仍在 functions
    "GPIO", "BOOT1", "OSC32_IN", "OSC32_OUT", "WKUP", "MCO1", "MCO2",
    "TRACECLK", "TRACED0", "TRACED1", "JTDI", "JTDO", "JTMS", "JTCK",
    "NJTRST", "TRACESWO",
}


def reverse_af_map(pin_map: dict[str, dict[str, Any]]) -> dict[str, str]:
    """从 pin_map 反推 af_map（信号 -> 引脚 反向映射）。

    遍历每个引脚的 functions，跳过非外设功能（NON_PERIPHERAL），
    生成 信号 -> 引脚 反向映射。多引脚信号用 "/" 分隔。

    Args:
        pin_map: {pin: {"functions": [sig, ...]}} 正向引脚映射

    Returns:
        {signal: "pin" 或 "pin1/pin2"} 反向信号映射，按信号名字典序排序

    Example:
        >>> pin_map = {"PA9": {"functions": ["GPIO", "USART1_TX"]},
        ...            "PB6": {"functions": ["GPIO", "USART1_TX", "I2C1_SCL"]}}
        >>> reverse_af_map(pin_map)
        {'I2C1_SCL': 'PB6', 'USART1_TX': 'PA9/PB6'}
    """
    af_map: dict[str, str] = {}
    for pin, info in pin_map.items():
        for func in info.get("functions", []):
            if func in NON_PERIPHERAL:
                continue
            if func in af_map:
                if pin not in af_map[func]:
                    af_map[func] = af_map[func] + "/" + pin
            else:
                af_map[func] = pin
    return dict(sorted(af_map.items()))


def diff_af_map(pin_map: dict[str, dict[str, Any]], current_af_map: dict[str, str]) -> dict[str, Any]:
    """对比现有 af_map 与从 pin_map 反推的 af_map，找出差异。

    用于校验 af_map 是否与 pin_map 一致，发现遗漏或错误。

    Returns:
        {"missing": [...], "extra": [...], "multi_pin": {...}}
        missing: pin_map 有但 af_map 漏的信号
        extra: af_map 有但 pin_map 没有的信号（可能过时）
        multi_pin: 多引脚信号的完整映射
    """
    reversed_map = reverse_af_map(pin_map)
    missing = [k for k in reversed_map if k not in current_af_map]
    extra = [k for k in current_af_map if k not in reversed_map]
    multi_pin = {k: v for k, v in reversed_map.items() if "/" in v}
    return {"missing": sorted(missing), "extra": sorted(extra), "multi_pin": multi_pin}
