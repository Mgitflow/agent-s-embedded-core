"""知识层契约：定义知识条目与兼容性结果等数据结构。"""
from dataclasses import dataclass, field
from typing import Any

from contracts.enums import KnowledgeStatus


@dataclass
class KnowledgeEntry:
    id: str
    topic: str
    peripheral_type: str
    content: Any
    source: str
    status: KnowledgeStatus
    type: list[str] = field(default_factory=lambda: ["plan", "code"])
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    created_at: str = ""
    updated_at: str = ""
    expire_ts: str | None = None
    verified: bool = False


@dataclass
class CompatibilityResult:
    decision: str
    target_entry: KnowledgeEntry | None = None
    violations: list[dict[str, Any]] = field(default_factory=list)
    mismatch_reason: str = ""
    adaptation: dict[str, Any] = field(default_factory=dict)
