"""通用级联（连接效果）渲染：两个阵营（开发板 / 芯片）共用同一套机制。

念安 2026-08-25 定调：项目核心 = 芯片阵营 + 开发板阵营，两者内部都有「级联 / 连接功能」。
级联 = 阵营内部多个原子的逻辑连接（A 读 B 的输出变量，按相对基准触发动作）。
cascade 配置是「连接效果」的单一权威源（材料），本模块是渲染（骨架），两阵营复用。

cascade 语义配置：
  camp    = board（开发板级联）/ chip（芯片级联），标识阵营
  reads   = 读宿主的哪个输出变量（如 g_lsens_value / g_adc_value）
  trigger = below(低于基准触发) / above(高于基准触发)
  offset  = 相对基准的偏移量（上电采样作基准，环境相关阈值不能写死——2026-08-25）
  pin     = 动作引脚（如 "PF9"）
  active  = low(低电平有效=点亮) / high(高电平有效)
"""
from __future__ import annotations

import re
from string import Template as StrTemplate
from typing import Any

# 阵营标记：board = 开发板级联（板载资源配合），chip = 芯片级联（通用外设配合）
CAMP_BOARD = "board"
CAMP_CHIP = "chip"


def derive_cascade_params(cascade: dict[str, Any]) -> dict[str, str]:
    """级联配置 → 渲染参数（引脚/电平/比较符的语义 → C 代码映射）。

    派生为 C 渲染参数：camp/pin_port/pin_no/on_level/off_level/reads/cmp/cmp_base/offset。
      camp     = 阵营（board / chip）
      cmp      = 比较符（above→">" / below→"<"）
      cmp_base = 基准偏移符（above→"+" / below→"-"），判断 reads vs (baseline ± offset)
    """
    pin = str(cascade.get("pin", "PF9"))
    m = re.match(r"^P([A-IK])(\d+)$", pin)
    port = m.group(1) if m else "F"
    pin_no = m.group(2) if m else "9"
    trigger = str(cascade.get("trigger", "below"))
    active = str(cascade.get("active", "low"))
    cmp_op = "<" if trigger == "below" else ">"
    cmp_base = "-" if trigger == "below" else "+"
    on_level = "GPIO_PIN_RESET" if active == "low" else "GPIO_PIN_SET"
    off_level = "GPIO_PIN_SET" if active == "low" else "GPIO_PIN_RESET"
    # offset 优先；旧配置的 threshold（绝对阈值）兼容读入，但新配置一律用 offset
    offset = str(cascade.get("offset", cascade.get("threshold", "")) or "")
    camp = str(cascade.get("camp", CAMP_BOARD) or CAMP_BOARD)
    return {
        "camp": camp,
        "pin_port": port,
        "pin_no": pin_no,
        "on_level": on_level,
        "off_level": off_level,
        "reads": str(cascade.get("reads", "") or ""),
        "cmp": cmp_op,
        "cmp_base": cmp_base,
        "offset": offset,
    }


def render_cascade_section(code: str, params: dict[str, str]) -> str:
    """用级联渲染参数填充 ${...} 占位符（safe_substitute 保留未知占位符不报错）。"""
    if not code:
        return code
    try:
        return StrTemplate(code).substitute(params)
    except KeyError:
        return StrTemplate(code).safe_substitute(params)


def render_cascade(
    init: str, loop: str, off: str, cascade: dict[str, Any]
) -> tuple[str, str, str]:
    """级联配置 → 渲染三段（init / loop / off）。两阵营（board/chip）通用入口。"""
    params = derive_cascade_params(cascade)
    return (
        render_cascade_section(init, params),
        render_cascade_section(loop, params),
        render_cascade_section(off, params),
    )
