"""审查层契约：定义 Reflector 输入输出与审查循环结果数据结构。"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReflectorInput:
    code: str
    user_input: str
    peripheral_type: str = ""
    blocks: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReflectorOutput:
    passed: bool
    level: str = "PASS"
    issues: list[dict[str, str]] = field(default_factory=list)
    feedback: str = ""
    suggestions: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class ReviewLoopResult:
    """R1 反馈循环的最终结果"""
    accepted: bool
    score: int
    iterations: int
    code: str
