"""事件总线：把硬流水线改为可观测的事件驱动，各环节 emit 事件供订阅者旁路观察，订阅者异常不影响主链路。"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    """轻量事件总线（进程级单例，通过 get_bus() 获取）。"""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

    def on(self, event: str, handler: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """订阅事件，返回退订函数。"""
        self._listeners.setdefault(event, []).append(handler)

        def unsubscribe() -> None:
            hs = self._listeners.get(event)
            if hs and handler in hs:
                hs.remove(handler)

        return unsubscribe

    def off(self, event: str, handler: Callable[[dict[str, Any]], None]) -> None:
        """退订事件。"""
        hs = self._listeners.get(event)
        if hs and handler in hs:
            hs.remove(handler)

    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """发布事件。失败安全：单个订阅者异常不阻断其余（也不阻断主链）。"""
        handlers = list(self._listeners.get(event, []))
        payload = data or {}
        for h in handlers:
            try:
                h(payload)
            except Exception:  # noqa: BLE001 —— 订阅者是旁路观察，绝不能拖垮主链
                logger.warning("event_bus: %s 事件处理失败（已跳过）", event, exc_info=True)

    def listeners_count(self, event: str = "") -> int:
        """统计订阅数（event 为空 = 全部）。"""
        if event:
            return len(self._listeners.get(event, []))
        return sum(len(hs) for hs in self._listeners.values())

    def clear(self) -> None:
        """清空全部订阅（测试用）。"""
        self._listeners.clear()


_bus: EventBus | None = None


def get_bus() -> EventBus:
    """进程级事件总线单例。"""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


# ── 标准事件名（流水线环节，供订阅方统一引用）──
EVT_PLAN_DONE = "pipeline:plan_done"            # {intent, scene, chip}
EVT_ASSESS_DONE = "pipeline:assessment_done"    # {level, need_confirm, reason}
EVT_CODE_GENERATED = "pipeline:code_generated"  # {peripheral, status, has_code}
EVT_REFLECT_DONE = "pipeline:reflect_done"      # {approved, must_passed, violations}
EVT_REWRITE_ROUND = "pipeline:rewrite_round"    # {round, reason, retry}
