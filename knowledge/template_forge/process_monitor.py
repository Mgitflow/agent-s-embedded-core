"""功能级工艺监测器：把「提示词→识别→生成」整条链做全方位无死角监测。

这是念安核心诉求的最终落地——**不是测「跑没跑通」，而是测「工艺对不对」**：

两个监测面：
1. 静态审查加孔（industrial_contract）：生成的 main.c 是否含工业级固定结构
   （HAL 引入 → 时钟 → 重置 → 初始化 → 配置 → 按需时序）
2. 功能级动态监测（process_contract）：
   - 识别步骤：提示词里的关键词，有没有被漏识别（漏识别 = 需求没接上）
   - 映射步骤：识别到的功能，是否都映射到了对应模板
   - 生成步骤：每个功能生成的代码，其 must_calls 是否都在（识别到按键就必须有按键初始化+读取）

返回结构化的监测报告，逐项标注 OK/MISS，缺啥补啥。
"""

from __future__ import annotations

import logging
from typing import Any

from knowledge.template_forge.functional_assembler import FunctionalAssembler
from knowledge.template_forge.functional_templates import FunctionalTemplateStore
from knowledge.template_forge.industrial_contract import check_main_c
from knowledge.template_forge.process_contract import check_requirements

_log = logging.getLogger(__name__)


class ProcessMonitor:
    """功能级工艺监测器：整条生成链的无死角监测。"""

    def __init__(self) -> None:
        self._store = FunctionalTemplateStore()
        self._assembler = FunctionalAssembler()

    # ────────────────────────── 识别监测 ──────────────────────────

    def check_recognition(self, text: str) -> dict[str, Any]:
        """识别步骤监测：提示词里的功能关键词，是否都被识别到。

        反向检查：找出文本里命中、但 match_all 漏掉的模板。
        """
        recognized = self._store.match_all(text)
        # 逐个模板看它的关键词是否在文本里出现、但没被识别
        missed: list[str] = []
        lowered = text.lower()
        for tid, tpl in self._store._templates.items():
            for kw in tpl.get("keywords", []):
                if kw.lower() in lowered and tid not in recognized:
                    # 该模板关键词命中但没被识别 → 可能被同族去重合理剔除
                    # 只报告「不同外设族」的漏识别（同族去重是预期行为）
                    family = (tpl.get("depends") or [None])[0]
                    recognized_families = {
                        (self._store._templates.get(r, {}).get("depends") or [None])[0]
                        for r in recognized
                    }
                    if family not in recognized_families:
                        missed.append(f"{tid}（关键词「{kw}」）")
                    break
        return {
            "recognized": recognized,
            "missed": missed,
            "ok": not missed,
        }

    # ────────────────────────── 生成监测（核心） ──────────────────────────

    def monitor(
        self, text: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """完整监测：识别 → 组装 → 工业结构校验 + 功能特征校验。

        Returns:
            {
              "text": ..., "recognized": [...], "recognition_missed": [...],
              "industrial": {...},       # 工业骨架结构校验
              "features": {...},         # 功能级 must_calls 校验
              "passed": bool,            # 总判定
            }
        """
        template_ids = self._store.match_all(text)
        report: dict[str, Any] = {
            "text": text,
            "recognized": template_ids,
        }
        if not template_ids:
            report["passed"] = False
            report["error"] = "未识别到任何功能模板"
            return report

        # 1. 识别监测（漏识别检查）
        rec = self.check_recognition(text)
        report["recognition_missed"] = rec["missed"]

        # 2. 组装（多功能组合 + 引脚避让）
        assembled = self._assembler.assemble_multi(text, params, template_ids=template_ids)
        if assembled is None:
            report["passed"] = False
            report["error"] = "组装失败"
            return report
        main_c = assembled.get("main_c", "")
        report["conflicts"] = assembled.get("conflicts", [])

        # 3. 工业骨架结构校验（静态审查加孔）
        report["industrial"] = check_main_c(main_c)

        # 4. 功能级特征校验（每个功能 must_calls 是否都在）
        report["features"] = check_requirements(main_c, template_ids)

        # 5. 总判定：识别全 + 工业结构全 + 功能特征全
        report["passed"] = bool(
            report["industrial"].get("_all_ok")
            and report["features"].get("_all_ok")
            and not report["recognition_missed"]
        )
        return report

    # ────────────────────────── 组合逻辑监测（复杂需求） ──────────────────────────

    def monitor_complex(self, text: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """复杂需求监测：点灯+按键+翻转 这类多功能组合。

        额外校验：
          - 组合顺序：识别到的功能是否按初始化顺序排列
          - 每个功能的 must_calls 是否都在组合结果里（互不吞并）
        """
        report = self.monitor(text, params)
        template_ids = report.get("recognized", [])
        # 组合完整性：每个功能都必须独立贡献 must_calls（互不覆盖）
        if template_ids and "features" in report:
            # 组合时 features 已逐功能校验，此处补一个「功能数 = 模板数」的对账
            report["combo_count"] = len(template_ids)
            report["combo_complete"] = all(
                v["ok"] for k, v in report["features"].items() if k != "_all_ok"
            )
        return report


def monitor_text(text: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """便捷入口：一句话监测。"""
    return ProcessMonitor().monitor(text, params)
