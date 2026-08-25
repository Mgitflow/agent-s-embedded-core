"""SkillContext 依赖注入容器：作为外部引入物的集中入口，按 key 分发通用能力与领域依赖。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillContext:
    """Skill 执行上下文：工作室向 Skill 注入的共享依赖。"""

    agent_name: str = "agent"

    # --- 通用能力（所有 Agent 都有，可空） ---
    transport: Any = None       # AgentTransport：跨 Agent 消息管道
    cache: Any = None           # 缓存（感知/执行记录）
    kb: Any = None              # 共享知识库

    # --- 领域扩展（外部引入物集中排列） ---
    deps: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """按名取领域依赖。"""
        return self.deps.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """注入领域依赖（组装区使用）。"""
        self.deps[key] = value

    def health(self) -> dict[str, Any]:
        """返回依赖可用性快照（供工作室状态上报）。"""
        return {
            "transport": self.transport is not None,
            "cache": self.cache is not None,
            "kb": self.kb is not None,
            "deps": {k: v is not None for k, v in self.deps.items()},
        }
