"""复合提示词理解器：在功能识别之上解析控制/上报/联动等逻辑关系，把控制关系注入模板参数，搭出有逻辑的工程。"""

from __future__ import annotations

import logging
import re
from typing import Any

_log = logging.getLogger(__name__)

# 控制关系关键词（谁控制谁）——贪婪到标点/分隔符边界
_CONTROL_RE = re.compile(
    r"([^，。；、,;：:\s]+)(?:控制|触发|按下|按动|驱动|根据)([^，。；、,;：:\s]+)"
)
# 上报/反馈关键词
_REPORT_RE = re.compile(r"([^，。；、,;：:\s]+)(?:上报|反馈|打印|发送|显示)([^，。；、,;：:\s]+)")

# 功能关键词 → 模板 id（补充 match_all 没覆盖的语义别名）
_SEMANTIC_MAP = {
    "按键": "button_read",
    "按钮": "button_read",
    "点灯": "led_blink",
    "led": "led_blink",
    "串口": "uart_print",
    "打印": "uart_print",
    "舵机": "pwm_servo",
    "呼吸灯": "pwm_output",
    "adc": "adc_read",
    "采样": "adc_read",
    "看门狗": "iwdg_refresh",
    "喂狗": "iwdg_refresh",
}


class PromptComposer:
    """复合提示词理解：功能 + 逻辑关系 → 带逻辑的模板组合。"""

    def __init__(self, store: Any = None) -> None:
        if store is None:
            from knowledge.template_forge.functional_templates import FunctionalTemplateStore

            store = FunctionalTemplateStore()
        self._store = store

    # ---- 主入口 ----

    def compose(self, text: str) -> dict[str, Any] | None:
        """理解复合提示词。

        Returns:
            {"templates": [...], "relations": {...}, "logic_code": {...}}
            或 None（无功能）
        """
        if not text:
            return None
        templates = self._store.match_all(text)
        # 语义别名补齐（match_all 按 depends 去重可能漏掉按键等）
        for tid in self._semantic_match(text):
            if tid not in templates:
                templates.append(tid)
        if not templates:
            return None

        relations = self._detect_relations(text, templates)
        logic_code = self._build_logic(text, templates, relations)
        return {"templates": templates, "relations": relations, "logic_code": logic_code}

    # ---- 功能识别 ----

    def _semantic_match(self, text: str) -> list[str]:
        lowered = text.lower()
        found: list[str] = []
        for kw, tid in _SEMANTIC_MAP.items():
            if kw in lowered and tid not in found:
                found.append(tid)
        return found

    # ---- 逻辑关系识别 ----

    def _detect_relations(self, text: str, templates: list[str]) -> dict[str, Any]:
        """识别控制/上报关系。返回 {模板: {"controls": [...], "reports": [...]}}。"""
        relations: dict[str, dict[str, list[str]]] = {}
        for tid in templates:
            relations[tid] = {"controls": [], "reports": []}

        # 控制关系："按键控制点灯" → button_read.controls += led_blink
        for m in _CONTROL_RE.finditer(text):
            src_kw, dst_kw = m.group(1), m.group(2)
            src_tid = self._kw_to_template(src_kw)
            dst_tid = self._kw_to_template(dst_kw)
            if src_tid and dst_tid and src_tid != dst_tid:
                if dst_tid not in relations.get(src_tid, {}).get("controls", []):
                    relations.setdefault(src_tid, {"controls": [], "reports": []})
                    relations[src_tid]["controls"].append(dst_tid)

        # 上报关系："串口上报状态" → uart_print.reports += 其他功能
        for m in _REPORT_RE.finditer(text):
            src_kw, dst_kw = m.group(1), m.group(2)
            src_tid = self._kw_to_template(src_kw)
            dst_tid = self._kw_to_template(dst_kw)
            if src_tid:
                # 上报方是"串口/打印"类 → 把其他功能加入它的 reports
                if src_tid == "uart_print" or "print" in src_tid:
                    for tid in templates:
                        if tid != src_tid and tid not in relations[src_tid]["reports"]:
                            relations[src_tid]["reports"].append(tid)
                elif dst_tid:
                    if dst_tid not in relations.get(src_tid, {}).get("reports", []):
                        relations.setdefault(src_tid, {"controls": [], "reports": []})
                        relations[src_tid]["reports"].append(dst_tid)
        return relations

    def _kw_to_template(self, kw: str) -> str | None:
        """关键词 → 模板 id（语义映射 + store 匹配）。"""
        if not kw:
            return None
        # 语义映射优先
        if kw in _SEMANTIC_MAP:
            return _SEMANTIC_MAP[kw]
        # 子串匹配
        for key, tid in _SEMANTIC_MAP.items():
            if key in kw:
                return tid
        # store 匹配
        tmp = self._store.match(kw)
        return tmp if isinstance(tmp, str) else ""

    # ---- 逻辑代码构建 ----

    def _build_logic(self, text: str, templates: list[str], relations: dict[str, Any]) -> dict[str, str]:
        """生成**可消费**的逻辑代码段（复查修正）。

        原则：只生成已实现的逻辑（controls 真接线由 FunctionalAssembler 完成），
        **不生成占位伪代码**——reports（跨模板状态上报）未实现时返回空，
        绝不生成"/* 在 xxx 循环中发送状态 */"这种假装实现的注释壳。
        """
        # 修正：controls 真接线已在 assemble_multi 渲染循环内完成
        # （${btn_action_code} 插槽注入被控动作），这里不再生成占位注释。
        # reports 跨模板状态上报尚未实现——不生成伪代码，留待真实现。
        return {}


def compose_prompt(text: str) -> dict[str, Any] | None:
    """便捷入口：理解复合提示词。"""
    return PromptComposer().compose(text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for t in [
        "按键控制点灯，串口上报状态",
        "点灯和串口打印",
        "舵机控制",
    ]:
        r = compose_prompt(t)
        print(f"{t!r} -> {r['templates'] if r else None}")
        if r and r["relations"]:
            for k, v in r["relations"].items():
                if v["controls"] or v["reports"]:
                    print(f"    {k}: {v}")
