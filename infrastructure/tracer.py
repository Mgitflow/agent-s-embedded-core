"""轻量流程跟踪器：按流程记录各阶段/分支的工作去向到 trace.jsonl，便于反查断链/超时/失败节点。"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

# 环境变量开关：AGENT_S_TRACE=0 关闭
_TRACE_ENABLED = os.environ.get("AGENT_S_TRACE", "1") != "0"
_lock = threading.Lock()
_file: Path | None = None
_buffer: list[dict[str, Any]] = []
_started_at = time.time()


def init_tracer(log_dir: str | Path | None = None) -> None:
    """启动时初始化 trace 输出文件（幂等，可重复调用）。"""
    global _file
    if not _TRACE_ENABLED:
        return
    if _file is not None:
        return
    if log_dir is None:
        # tracer.py 位于 <项目根>/infrastructure/ 下，parent×2 = 项目根
        log_dir = Path(__file__).resolve().parent.parent / "data" / "logs"
    log_dir = Path(log_dir)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        _file = log_dir / "trace.jsonl"
    except OSError:
        _file = None  # 不可写时静默降级（内存 buffer 仍记录）


def trace(stage: str, status: str = "ok", detail: str = "", **extra: Any) -> None:
    """打点：记录一个流程节点。

    Args:
        stage: 阶段名（如 planner/assessor/generator/reflector/rewrite_loop）
        status: ok / start / fail / timeout / skip
        detail: 简短说明（如 intent=GPIO / approved=False）
        extra: 附加字段（如 elapsed_ms）
    """
    if not _TRACE_ENABLED:
        return
    global _buffer
    entry: dict[str, Any] = {
        "ts": round(time.time(), 3),
        "t": round((time.time() - _started_at) * 1000, 1),  # 启动后毫秒
        "stage": stage,
        "status": status,
        "detail": detail[:300],
    }
    if extra:
        entry.update(extra)
    with _lock:
        _buffer.append(entry)
        if len(_buffer) > 2000:
            _buffer = _buffer[-1000:]  # 内存只留最近 1000
        if _file is not None:
            try:
                with open(_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                pass


def recent(limit: int = 50) -> list[dict[str, Any]]:
    """返回最近 N 条事件（内存 buffer）。"""
    with _lock:
        return list(_buffer[-limit:])


def _read_file() -> list[dict[str, Any]]:
    """读取 trace.jsonl 全部事件（用于分析）。"""
    if _file is None or not _file.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with open(_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return events


def analyze(window_s: float = 3600.0, top: int = 10) -> dict[str, Any]:
    """分析卡点：最近 window_s 内 status in (fail/timeout) 的节点，按 stage 聚合。

    Returns:
        {"abnormal": [...], "by_stage": {stage: count}, "total": N}
    """
    events = [e for e in _read_file() if time.time() - e.get("ts", 0) <= window_s]
    abnormal = [e for e in events if e.get("status") in ("fail", "timeout")]
    by_stage: dict[str, int] = {}
    for e in abnormal:
        by_stage[e.get("stage", "?")] = by_stage.get(e.get("stage", "?"), 0) + 1
    return {
        "total_events": len(events),
        "abnormal_count": len(abnormal),
        "by_stage": dict(sorted(by_stage.items(), key=lambda x: -x[1])[:top]),
        "recent_abnormal": abnormal[-top:],
        "trace_file": str(_file) if _file else None,
    }


__all__ = ["init_tracer", "trace", "recent", "analyze"]
