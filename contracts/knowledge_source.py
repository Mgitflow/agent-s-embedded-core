"""知识源插件接口：定义 KnowledgeManager 可插拔数据源的契约。"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IKnowledgeSource(Protocol):
    """知识源插件接口：为 KnowledgeManager 提供可扩展的数据查询能力。"""

    def name(self) -> str:
        """返回知识源名称（用于日志与调试）。"""
        ...

    def can_handle(self, topic: str, target_type: str | None = None) -> bool:
        """判断当前知识源是否能处理给定查询主题。"""
        ...

    def fetch(self, topic: str, target_type: str | None = None) -> dict[str, Any] | None:
        """查询知识并返回标准化结果；无法处理时返回 None。

        返回格式建议为：
        {
            "status": "ok" | "missing" | "error",
            "source": "source_name",
            "data": {...},
        }
        """
        ...
