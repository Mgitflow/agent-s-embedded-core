"""请求 ID 贯穿工具（thread-local）：为结构化日志关联同一请求的全部日志行。"""
from __future__ import annotations

import threading

_local = threading.local()


def set_request_id(rid: str) -> None:
    """设置当前线程的请求 ID。"""
    _local.rid = rid


def get_request_id() -> str:
    """读取当前线程请求 ID（未设置返回 "-"）。"""
    return getattr(_local, "rid", "-")
