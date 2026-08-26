"""规则校验结果（契约层）：单条规则的校验结论。

下沉：RuleResult 从 engine/rule_engine.py 迁至 contracts，
使 IRuleEngine.validate 能声明返回 list[RuleResult]（契约强类型）。
engine 层通过 re-export 兼容旧引用。
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.enums import RuleLevel


@dataclass
class RuleResult:
    """单条规则的校验结果。"""

    rule_id: str
    level: RuleLevel
    passed: bool
    message: str
    error_code: str = ""
