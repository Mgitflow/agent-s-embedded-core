"""规划层契约：定义 Planner 输入输出与 plan 序列化。"""
from dataclasses import dataclass, field
from typing import Any

from contracts.enums import IntentType


def plan_to_dict(plan: Any) -> dict[str, Any]:
    """统一 plan 序列化（PlannerOutput/dict/其他均安全转 dict）。

    供 code_skill / assessor 等所有消费 plan 的位置复用，避免各自实现一份。
    """
    if hasattr(plan, "to_dict"):
        try:
            tmp = plan.to_dict()
            return tmp if isinstance(tmp, dict) else {}
        except Exception:
            pass
    if isinstance(plan, dict):
        return plan
    return {"raw": str(plan)}


@dataclass
class PlannerInput:
    user_input: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerOutput:
    action: str
    reason: str
    peripheral: str = "GPIO"
    intent: str = IntentType.UNKNOWN.value
    scene: str = "init"
    confidence: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    structure_items: list[str] = field(default_factory=list)
    format_warning: str = ""
    complexity: str = "simple"
    hardware: str = "APM32F407"
    raw_plan: dict[str, Any] = field(default_factory=dict)

    @property
    def chip(self) -> str:
        """v1.3.0: chip 别名，向后兼容"""
        return self.hardware

    @chip.setter
    def chip(self, value: str) -> None:
        self.hardware = value

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 安全 dict（上层/SE 框架消费 plan 的标准格式）。"""
        return {
            "action": self.action,
            "reason": self.reason,
            "peripheral": self.peripheral,
            "intent": self.intent,
            "scene": self.scene,
            "confidence": self.confidence,
            "params": self.params,
            "structure_items": list(self.structure_items),
            "format_warning": self.format_warning,
            "complexity": self.complexity,
            "hardware": self.hardware,
            "chip": self.hardware,
            "raw_plan": self.raw_plan,
        }
