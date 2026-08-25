"""评估层契约：定义 Assessor 的输入输出数据结构。"""
from dataclasses import dataclass, field
from typing import Any

from contracts.enums import RiskLevel


@dataclass
class AssessorInput:
    plan: Any
    user_input: str = ""


@dataclass
class AssessorOutput:
    need_confirm: bool
    level: RiskLevel = RiskLevel.LOW
    reason: str = ""
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
