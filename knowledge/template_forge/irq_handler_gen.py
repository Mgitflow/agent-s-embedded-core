"""中断 handler 生成器（编辑线路：默认无 → 用了中断就按标准材料生成）。

「配套文件的编辑线路」：配套文件可变点统一「默认值 + 需求驱动覆盖」，
中断 handler 是最关键的编辑线路——功能模板 init 里已 `HAL_NVIC_EnableIRQ(XXX_IRQn)`，
但对应的 `XXX_IRQHandler` 从没生成，中断来了跳 Default_Handler 死循环。

本模块从渲染后的 slot（init_bodies/extra_code 已替换占位符）自动提取：
  ① 使能了哪些中断（HAL_NVIC_EnableIRQ(XXX_IRQn)）
  ② 各外设的 handle 名（HAL_xxx_Init(&handle)）
再按 `irq_handler_standards.json`（范式级材料）生成：
  - 中断 handler 定义（进 it.c 的 {peripheral_irq_handlers}）
  - 中断 handler 原型（进 it.h 的 {peripheral_irq_protos}）
  - handle 的 extern 声明（进 it.c 的 {extern_handles}）

零 LLM 依赖，全确定性。加新外设中断 = 在材料里加一条，不改本模块。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_STANDARDS_PATH = Path(__file__).resolve().parent / "irq_handler_standards.json"


def _load_standards(path: Path | None = None) -> dict[str, Any]:
    """读中断 handler 标准材料（可传 path 便于测试注入）。"""
    p = path or _STANDARDS_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _slot_text(slot: dict[str, Any]) -> str:
    """拼接 slot 里所有含代码的字段（渲染后，占位符已替换）。"""
    parts: list[str] = []
    for bodies in (slot.get("init_bodies") or {}).values():
        parts.append("\n".join(str(b) for b in bodies))
    parts.append("\n".join(str(g) for g in slot.get("globals") or []))
    parts.append("\n".join(str(c) for c in slot.get("extra_code") or []))
    parts.append("\n".join(str(c) for c in slot.get("msp_code") or []))
    return "\n".join(parts)


def extract_irq_handlers(slices: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """从工程切片提取中断 handler（定义/原型/extern 声明）。

    Returns:
        (handlers, protos, externs)
          handlers: 完整 handler 定义字符串列表（进 it.c）
          protos:   `void XXX_IRQHandler(void);` 声明列表（进 it.h）
          externs:  `extern <Type> <handle>;` 声明列表（进 it.c 外部变量区）
    """
    standards = _load_standards()
    handlers_map = standards.get("handlers", {}) or {}
    if not handlers_map:
        return [], [], []

    # 类型匹配顺序：长的前缀优先（避免短前缀误吞），按材料 key 长度降序
    types = sorted(handlers_map.keys(), key=len, reverse=True)

    handlers: list[str] = []
    protos: list[str] = []
    externs: list[str] = []
    seen_irq: set[str] = set()
    seen_extern: set[str] = set()

    for slot in (slices.get("peripherals") or {}).values():
        text = _slot_text(slot)
        irq_names = re.findall(r"HAL_NVIC_EnableIRQ\((\w+)_IRQn\)", text)
        for irq in irq_names:
            if irq in seen_irq:
                continue
            seen_irq.add(irq)
            typ = next((t for t in types if irq.startswith(t)), None)
            if not typ:
                continue
            rule = handlers_map[typ]
            handler_name = f"{irq}_IRQHandler"

            if typ == "EXTI":
                m = re.search(rule.get("line_re", ""), irq + "_IRQn")
                if not m:
                    continue
                body = str(rule["hal_call"]).replace("{line}", m.group(1))
            else:
                m = re.search(rule.get("handle_re", ""), text)
                if not m:
                    continue
                handle = m.group(1)
                body = str(rule["hal_call"]).replace("{handle}", handle)
                ext = f"extern {rule.get('handle_type', 'void')} {handle};"
                if ext not in seen_extern:
                    seen_extern.add(ext)
                    externs.append(ext)

            handlers.append(f"void {handler_name}(void)\n{{\n  {body}\n}}")
            protos.append(f"void {handler_name}(void);")

    return handlers, protos, externs


if __name__ == "__main__":  # pragma: no cover —— 调试入口
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from knowledge.template_forge.functional_assembler import FunctionalAssembler
    from knowledge.template_forge.project_slicer import bundles_to_project_slices

    text = sys.argv[1] if len(sys.argv) > 1 else "串口中断接收"
    chip = sys.argv[2] if len(sys.argv) > 2 else "apm32f407vgt6"
    r = FunctionalAssembler().assemble_multi(text, chip=chip)
    slices = bundles_to_project_slices(r.get("bundles", []) if r else [])
    h, p, e = extract_irq_handlers(slices)
    print("=== 中断 handler ===")
    for x in h:
        print(x)
        print()
    print("=== 原型 ===")
    for x in p:
        print(x)
    print("=== extern ===")
    for x in e:
        print(x)
