"""全局一致性检查器：对当前决策节点做教训关联/芯片边界/站位冲突三项连通性检查，纯规则图遍历、确定性分级。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from infrastructure.chip_knowledge import ResourcePlanner
from infrastructure.knowledge_retrieval import ChunkRetriever, get_retriever

# 教训命中级别：外设标签命中（有历史踩坑）→ WARN；参数级强相关由调用方传入明确规则
_LESSON_LEVEL = "WARN"


class GlobalConsistencyChecker:
    """全局关联一致性检查器（规则引擎版自注意力）。"""

    def __init__(
        self,
        retriever: ChunkRetriever | None = None,
        planner_factory: Callable[[str], ResourcePlanner] | None = None,
    ) -> None:
        self._retriever = retriever or get_retriever()
        self._planner_factory = planner_factory or (lambda chip: ResourcePlanner(chip))

    # ---------- 检查维度 ----------
    def _check_lessons(self, peripherals: list[str]) -> list[dict[str, Any]]:
        """教训关联：外设是否命中 NOTEBOOK 危险标签。"""
        issues: list[dict[str, Any]] = []
        for p in peripherals:
            for le in self._retriever.search_lessons(peripheral=p):
                issues.append(
                    {
                        "level": _LESSON_LEVEL,
                        "dimension": "lesson",
                        "peripheral": p,
                        "rule": f"教训 {le.get('id')}: {str(le.get('title'))[:30]}",
                        "detail": f"{p} 有历史踩坑记录（{le.get('id')}），生成时对照规避",
                    }
                )
        return issues

    def _check_chip_boundary(self, chip: str, peripherals: list[str]) -> list[dict[str, Any]]:
        """芯片边界：需求外设是否超出芯片 pin_map 能力（能力图遍历）。"""
        issues: list[dict[str, Any]] = []
        try:
            planner = self._planner_factory(chip)
        except FileNotFoundError:
            return [{"level": "WARN", "dimension": "chip", "rule": "芯片包未知",
                     "detail": f"无法校验芯片能力边界: {chip}"}]
        for p in peripherals:
            if not planner.supports_peripheral(p):
                issues.append(
                    {
                        "level": "WARN",
                        "dimension": "chip",
                        "peripheral": p,
                        "rule": "外设超能力边界",
                        "detail": f"{chip} 的 pin_map 未发现 {p} 信号",
                    }
                )
        return issues

    def _check_pin_conflicts(self, chip: str, signals: list[str], pins_used: list[str]) -> list[dict[str, Any]]:
        """站位冲突：需求信号 vs 已占用引脚（ResourcePlanner）。"""
        issues: list[dict[str, Any]] = []
        try:
            planner = self._planner_factory(chip)
        except FileNotFoundError:
            return issues
        plan = planner.plan(pins_used=pins_used, signals=signals)
        for c in plan.get("conflicts", []):
            issues.append(
                {
                    "level": "BLOCK",
                    "dimension": "pin",
                    "peripheral": c["signal"],
                    "rule": "引脚冲突",
                    "detail": f"{c['signal']} 候选引脚 {c['pin']} 已被占用",
                }
            )
        for sig in plan.get("missing", []):
            issues.append(
                {
                    "level": "WARN",
                    "dimension": "pin",
                    "peripheral": sig,
                    "rule": "信号未收录",
                    "detail": f"{sig} 在 af_map 未找到候选引脚",
                }
            )
        return issues

    # ---------- 入口 ----------
    def check(
        self,
        chip: str,
        peripherals: list[str] | None = None,
        signals: list[str] | None = None,
        pins_used: list[str] | None = None,
    ) -> dict[str, Any]:
        """全局一致性检查：决策 vs 教训/芯片边界/站位。

        返回：
          ok:     是否全部通过（无 BLOCK）
          issues: [{level, dimension, rule, detail}]（BLOCK 阻断 / WARN 降级参考）
        """
        peripherals = peripherals or []
        signals = signals or []
        pins_used = pins_used or []
        issues: list[dict[str, Any]] = []
        issues += self._check_lessons(peripherals)
        issues += self._check_chip_boundary(chip, peripherals)
        issues += self._check_pin_conflicts(chip, signals, pins_used)
        blocks = [i for i in issues if i["level"] == "BLOCK"]
        return {
            "chip": chip,
            "ok": not blocks,
            "issue_count": len(issues),
            "block_count": len(blocks),
            "issues": issues,
        }
