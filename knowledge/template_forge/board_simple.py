"""开发板简单逻辑模板渲染器：读 boards/<board>/simple_templates.json，匹配需求，渲染定型代码。

「简单逻辑模板」= 开发板肖像的代码化：探索者每个资源一套最简逻辑
（照开发板手册填的定型代码，引脚/有效电平固定，非参数化）。区别于 functional
通用模板（参数化/GPIO 池，管零散芯片自研场景）——本模板是「快速出活」的定型
代码，对应「开发板规矩被开发商定死了、照手册填」的分层。

触发（「复用 chip、不加 board」）：chip 参数 → board.json（按
meta.mcu 匹配）→ simple_templates.json → 匹配需求 → 渲染定型代码。有模板则用，
无模板（或非开发板芯片）回落 functional 通用。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from infrastructure.board_resolver import resolve_board_json

# 项目根（knowledge/template_forge → knowledge → 项目根）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_simple_templates(board_dir: Path) -> dict[str, Any]:
    """读 boards/<board>/ 的 simple_templates.json + advanced_templates.json 的 templates 段。

    简单逻辑模板（simple，点灯/按键/串口等）与进阶复杂外设（advanced，LCD/音频/
    SDIO/以太网/摄像头等）合并返回；缺失/损坏返回空 dict。
    """
    templates: dict[str, Any] = {}
    for fname in ("simple_templates.json", "advanced_templates.json"):
        st_path = board_dir / fname
        if not st_path.is_file():
            continue
        try:
            data = json.loads(st_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tpls = data.get("templates", {})
        if isinstance(tpls, dict):
            templates.update(tpls)
    return templates


def match_simple_template(text: str, templates: dict[str, Any]) -> str | None:
    """按需求文本匹配简单逻辑模板 id（更长关键词优先，同 functional.match 策略）。"""
    if not text:
        return None
    lowered = text.lower()
    best: str | None = None
    best_len = 0
    for tid, tpl in templates.items():
        for kw in tpl.get("match", []):
            if kw.lower() in lowered and len(kw) > best_len:
                best = tid
                best_len = len(kw)
    return best


def match_all_simple(text: str, templates: dict[str, Any]) -> list[str]:
    """多需求 → 模板 id 列表（更长关键词优先，避免短关键词误匹配）。

    二次开发（「插新逻辑 + 冲突重查」）的多需求识别：文本里提到几个
    功能就匹配几个模板（"点灯+按键" → [led_blink, key_press]）。

    去重规则：
    - 一个模板最多匹配一次（多关键词命中取最长）
    - 短关键词被更长关键词「包含」时跳过（"灯" 被 "呼吸灯" 覆盖 → 不误匹配
      led_blink；"串口" 被 "串口3" 覆盖 → 不误匹配 uart_print）
    """
    if not text:
        return []
    lowered = text.lower()
    hits: list[tuple[int, str, str]] = []  # (关键词长度, 关键词, 模板 id)
    for tid, tpl in templates.items():
        for kw in tpl.get("match", []):
            if kw.lower() in lowered:
                hits.append((len(kw), kw, tid))
    hits.sort(key=lambda h: -h[0])  # 长关键词优先
    matched: list[str] = []
    matched_kws: list[str] = []
    seen: set[str] = set()
    for _length, kw, tid in hits:
        if tid in seen:
            continue
        # 短关键词被已匹配的更长关键词包含 → 跳过（避免 "灯" 被 "呼吸灯" 覆盖时误匹配）
        if any(kw.lower() in mk.lower() and kw.lower() != mk.lower() for mk in matched_kws):
            continue
        matched.append(tid)
        matched_kws.append(kw)
        seen.add(tid)
    # 自动带串口（深化测试「外设无回传」修复）：
    # 命中「有结果要回传」的外设模板（requires_uart），自动附加 uart_print，
    # 让读到的结果能串口打出来、上板能看见——不靠用户手动组合「+ 串口打印」。
    if "uart_print" in templates and "uart_print" not in matched:
        for tid in matched:
            if templates.get(tid, {}).get("requires_uart"):
                matched.append("uart_print")
                break
    return matched


def extract_template_pins(init_code: str) -> set[str]:
    """从模板 init 代码提取定型引脚（如 {"PF9", "PE4"}），用于组合冲突重查。

    扫描 GPIO_InitStruct.Pin = ... 与 HAL_GPIO_Init(GPIOx, ...) 的顺序配对，
    把 Pin 组关联到最近的 GPIO 端口（模板 init 都是「设 Pin → Init」结构）。
    """
    pins: set[str] = set()
    pending: list[int] = []
    for line in init_code.splitlines():
        m_init = re.search(r"HAL_GPIO_Init\(\s*(GPIO[A-G])", line)
        if m_init:
            port = m_init.group(1)[-1]  # GPIOF → F
            for pin in pending:
                pins.add(f"P{port}{pin}")
            pending = []
        else:
            m_pin = re.search(r"GPIO_InitStruct\.Pin\s*=\s*(GPIO_PIN_\d+(?:\s*\|\s*GPIO_PIN_\d+)*)", line)
            if m_pin:
                pending = [int(x) for x in re.findall(r"GPIO_PIN_(\d+)", m_pin.group(1))]
    return pins


def render_simple_template(tid: str, templates: dict[str, Any]) -> dict[str, Any] | None:
    """渲染定型代码（init/loop/deinit + globals/init_func），无参数化（引脚已定型）。

    级联模板（cascade 字段）例外：cascade 配置是「连接效果」的单一权威源，
    init/loop 用 ${pin_port}/${offset} 等占位符，此处按 cascade 配置派生参数渲染
    （级联层 = 开发板定型 ↔ 单一模块之间的过渡，）。
    """
    tpl = templates.get(tid)
    if not tpl:
        return None
    init = tpl.get("init", "")
    loop = tpl.get("loop", "")
    off = tpl.get("off", "")
    cascade = tpl.get("cascade")
    if cascade:
        # 级联配置 → 渲染参数（材料驱动，加连接效果=加配置，不改骨架）
        params = _derive_cascade_params(cascade)
        init = _render_cascade_section(init, params)
        loop = _render_cascade_section(loop, params)
        off = _render_cascade_section(off, params)
    return {
        "id": tid,
        "peripheral": tpl.get("peripheral", "GPIO"),
        "defense": tpl.get("defense", ""),
        "init_func": tpl.get("init_func", ""),
        "deinit_func": tpl.get("deinit_func", ""),
        "globals": tpl.get("globals", ""),
        "helpers": tpl.get("helpers", ""),
        "description": tpl.get("description", ""),
        "cascade": cascade,
        "init": init,
        "loop": loop,
        "deinit": tpl.get("deinit", ""),
        # 关闭动作（有源器件的「关」）：启动门 toggle 到关闭时执行（蜂鸣器停/灯灭），
        # 「」——「按键调试能开能关，不是一次性置位」。
        "off": off,
    }


# 级联渲染已抽到通用模块 cascade.py（两阵营共用，）
from knowledge.template_forge.cascade import (  # noqa: E402
    derive_cascade_params as _derive_cascade_params,
    render_cascade_section as _render_cascade_section,
)


def resolve_board_simple(chip: str, root: Path | None = None) -> dict[str, Any]:
    """chip → board.json → simple_templates（返回模板 dict，未找到返回空 dict）。

    开发板场景（chip 匹配到 board.json 且有 simple_templates.json）返回定型模板；
    否则返回空 dict（调用方回落 functional 通用）。
    """
    root = root or _PROJECT_ROOT
    board_path = resolve_board_json(root, chip)
    if board_path is None:
        return {}
    return load_simple_templates(board_path.parent)


def render_board_simple(text: str, chip: str, root: Path | None = None) -> dict[str, Any] | None:
    """高层入口：chip + 需求文本 → 匹配 + 渲染简单逻辑模板；无命中返回 None。

    返回 {id, description, init, loop, deinit} 或 None（非开发板场景 / 无匹配）。
    """
    templates = resolve_board_simple(chip, root)
    if not templates:
        return None
    tid = match_simple_template(text, templates)
    if tid is None:
        return None
    return render_simple_template(tid, templates)


__all__ = [
    "load_simple_templates",
    "match_simple_template",
    "match_all_simple",
    "extract_template_pins",
    "render_simple_template",
    "resolve_board_simple",
    "render_board_simple",
]
