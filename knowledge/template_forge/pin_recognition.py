"""引脚识别层：从需求文本抠引脚指定（念安 8-20「识别到角 → 替换默认角」）。

和 ``electrical.parse_electrical_reqs``（抠电气参数）并列，本模块抠「引脚」。
产出 {功能参数键: 引脚}，配置环节 ``PinAllocator.resolve_template_pins`` 的 preferred
机制据它替换默认角（没识别到 → 走默认角，模板本身已填默认）。

设计（念安 8-20「名字=引脚」连体绑定 + 「识别到模板→拉默认角→识别到角不一样→替换」）：
  - 对外名字不变（LED 还是 LED），内部用「名字@引脚」连体区分重名
  - 模板默认角是「兜底/冲量」，需求指定角则覆盖（替换）
  - 防冲突落在「零散芯片自定义」场景：两个都叫 LED 的，用角区分（LED@PA5 vs LED@PA3）

引脚代号（念安 8-21「把引脚画成代号」）：允许用户自定义引脚别名（LED=PA5），
需求里用别名指代引脚；不画代号则直接用物理引脚名（PA5）。别名解析在抠引脚前完成。
"""
from __future__ import annotations

import re

# 功能词 → 参数键列表（识别层把「点灯」映射到 led_blink 的 led_pin）。
# 参数键对齐 functional 模板 PIN_REQUIREMENTS 的键（配置环节按它替换默认角）。
# 多引脚（复合外设）按顺序对应：如 I2C → [scl, sda]，SPI → [sck, miso, mosi]。
_FUNC_PIN_KEYS: dict[str, list[str]] = {
    "呼吸灯": ["pwm_pin"], "呼吸": ["pwm_pin"], "pwm": ["pwm_pin"],
    "点灯": ["led_pin"], "led": ["led_pin"], "灯": ["led_pin"],
    "按键": ["btn_pin"], "按钮": ["btn_pin"], "key": ["btn_pin"], "键": ["btn_pin"],
    "串口": ["tx_pin", "rx_pin"], "uart": ["tx_pin", "rx_pin"], "usart": ["tx_pin", "rx_pin"],
    "i2c": ["i2c_scl", "i2c_sda"], "iic": ["i2c_scl", "i2c_sda"],
    "spi": ["spi_sck", "spi_miso", "spi_mosi"],
}

# 明确端口引脚：PA5 / PB3 / PF9（P + 端口字母 + 数字）
_PIN_RE = re.compile(r"\bP[A-I]\d+\b", re.IGNORECASE)
# 裸角号：5 角 / 5号角 / 5脚 / pin5（无端口，默认 A 端口 → PA5）
_BARE_PIN_RE = re.compile(r"(?:^|[\s（(])(\d{1,2})\s*(?:号?角|脚|pin)", re.IGNORECASE)

# 引脚别名定义：LED=PA5（别名 = 物理引脚）。别名用标识符（字母/下划线开头），
# 物理引脚 P + 端口字母 + 数字。只匹配「=」号连接的明确定义，不误伤「点灯 PA5」。
_ALIAS_DEF_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(P[A-I]\d{1,2})\b")

# 多功能分隔符：把「点灯 PA5，按键 PB3」这类复合需求切成单功能子句。
# 含标点（逗号/顿号/分号）与连接词（再/然后/以及/还有/并且/加上/和/另外）。
# 「和」也作功能连接词（点灯和按键）。同功能双角（「两个灯 PA5 和 PA3」）由
# _parse_multi_instance_pins 在切句前先行拦截，不会被「和」误切。
_CLAUSE_SEP_RE = re.compile(r"[,，、;；]|再|然后|以及|还有|并且|加上|另外|和")

# 数量词（与 functional_templates._QUANT_RE 同源：念安 8-20「两个灯」多实例）。
# 识别层数量词权威源，避免两处各写一份正则。
_CN_NUM = {"两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_QUANT_RE = re.compile(r"([两二三四五六七八九十\d]+)\s*(?:个|盏|颗|路|组|只)")


def _split_clauses(text: str) -> list[str]:
    """按分隔符切分多功能需求，每子句 = 单功能 + 引脚。"""
    return [c.strip() for c in _CLAUSE_SEP_RE.split(text) if c.strip()]


def _parse_multi_instance_pins(text: str) -> dict[str, str | list[str]]:
    """同功能多实例显式引脚：两个灯 PA5 和 PA3 → {led_pin: ['PA5', 'PA3']}。

    触发：数量词（两个/2个/三盏…）+ 单引脚功能（keys 长度 1）+ 多个引脚。
    与 functional_templates._expand_quantifiers 同源（数量词），但职责不同：
    那边「数量词 → 重复模板 N 次」，这边「数量词 + 多引脚 → N 个引脚列表」；
    assemble_multi 按实例序号把引脚分发到各实例（第 0 个实例取第 0 个角）。
    """
    if not _QUANT_RE.search(text):
        return {}
    lowered = text.lower()
    for word, keys in _FUNC_PIN_KEYS.items():
        if len(keys) == 1 and word in lowered:
            pins = [m.upper() for m in _PIN_RE.findall(text)]
            if len(pins) >= 2:
                result: dict[str, str | list[str]] = {keys[0]: pins}
                return result
            break
    return {}


def _parse_single_clause(clause: str) -> dict[str, str]:
    """单子句内抠引脚 + 命中功能词 → {参数键: 引脚}（单功能 + 多引脚按顺序）。

    '点灯 PA5'       → {'led_pin': 'PA5'}
    '串口 PA9 PA10'  → {'tx_pin': 'PA9', 'rx_pin': 'PA10'}
    'I2C PB8 PB9'    → {'i2c_scl': 'PB8', 'i2c_sda': 'PB9'}
    无引脚 → 空 dict（走模板默认角）。
    """
    reqs: dict[str, str] = {}
    if not clause:
        return reqs

    # 抠引脚：明确端口优先（PA5/PB3...），裸角号兜底（5 角 → PA5）
    pins = [m.upper() for m in _PIN_RE.findall(clause)]
    if not pins:
        m = _BARE_PIN_RE.search(clause)
        if m:
            pins = [f"PA{m.group(1)}"]  # 裸角号默认 A 端口（GPIO 池首选 PA5）

    if not pins:
        return reqs

    # 找功能词（映射表按「更具体优先」排序：呼吸灯 > 灯），命中第一个；多引脚按顺序对应
    lowered = clause.lower()
    for word, keys in _FUNC_PIN_KEYS.items():
        if word in lowered:
            for i, key in enumerate(keys):
                if i < len(pins):
                    reqs[key] = pins[i]
            break
    return reqs


def parse_pin_aliases(text: str) -> tuple[dict[str, str], str]:
    """从需求文本抠「别名=物理引脚」定义，返回 (别名映射, 去除定义后的文本)。

    例：'LED=PA5 点灯 LED' → ({'LED': 'PA5'}, ' 点灯 LED')
    无定义 → ({}, 原文本)。别名用大写存储，物理引脚统一大写。
    """
    if not text:
        return {}, text
    aliases: dict[str, str] = {}

    def _sub(m: re.Match[str]) -> str:
        aliases[m.group(1).upper()] = m.group(2).upper()
        return ""

    cleaned = _ALIAS_DEF_RE.sub(_sub, text)
    return aliases, cleaned


def apply_pin_aliases(text: str, aliases: dict[str, str]) -> str:
    """把文本里的别名引用替换成物理引脚（词边界精确匹配，不误伤子串）。"""
    if not aliases or not text:
        return text
    for alias, pin in aliases.items():
        text = re.sub(rf"\b{re.escape(alias)}\b", pin, text, flags=re.IGNORECASE)
    return text


def parse_pin_reqs(text: str) -> dict[str, str | list[str]]:
    """从需求文本抠引脚指定，映射到功能参数键（多功能精准关联 + 同功能多实例）。

    念安 8-20「识别到模板 → 拉默认角 → 识别到角不一样 → 替换」；本函数负责
    「识别角」这一步，产出 {参数键: 引脚 | 引脚列表}；配置环节据它替换默认角。

    多功能精准关联（念安 8-20）：按分隔符切子句 → 逐句「单功能 + 引脚」识别 →
    合并，让每个功能各带各的角。
    同功能多实例（念安 8-20「两个灯 PA5 和 PA3」）：数量词 + 单功能 + 多引脚 →
    {参数键: [角1, 角2, ...]}，assemble_multi 按实例序号分发。

    例：
      '点灯用 PA5'        → {'led_pin': 'PA5'}
      '点灯 PA5，按键 PB3' → {'led_pin': 'PA5', 'btn_pin': 'PB3'}   ← 多功能精准关联
      '两个灯 PA5 和 PA3'  → {'led_pin': ['PA5', 'PA3']}             ← 同功能多实例
      '点灯 PA5，串口 PA9 PA10' → {'led_pin': 'PA5', 'tx_pin': 'PA9', 'rx_pin': 'PA10'}
    未识别到引脚 → 空 dict（走模板默认角）。
    """
    if not text:
        return {}
    # 引脚代号（念安 8-21「把引脚画成代号」）：先抠「别名=引脚」定义，再把引用替换成物理引脚
    aliases, text = parse_pin_aliases(text)
    text = apply_pin_aliases(text, aliases)
    # 1. 同功能多实例显式引脚：数量词 + 单功能 + 多引脚 → {key: [角1, 角2, ...]}
    multi = _parse_multi_instance_pins(text)
    if multi:
        return multi
    # 2. 多功能精准关联：有分隔符 → 逐子句识别并合并
    reqs: dict[str, str | list[str]] = {}
    for clause in _split_clauses(text):
        reqs.update(_parse_single_clause(clause))
    # 3. 无分隔符（或切分后无功能词命中）→ 回退整句单功能识别
    if not reqs:
        reqs.update(_parse_single_clause(text))
    return reqs


__all__ = ["parse_pin_reqs", "parse_pin_aliases", "apply_pin_aliases"]
