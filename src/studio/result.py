"""SkillResult 统一结果契约：同时支持 RPC 语义（ok/data/error）与流水线语义（status/artifacts/next_skills）。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    """Skill 执行的统一结果。"""

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    elapsed_ms: float = 0.0

    # --- 流水线扩展（可选，供 code_gen 这类编排技能使用） ---
    status: str = "success"             # success / partial / failed
    artifacts: dict[str, Any] = field(default_factory=dict)   # 技能产物（source_code/plan/...）
    next_skills: list[str] = field(default_factory=list)  # 建议下游技能

    def to_dict(self) -> dict[str, Any]:
        """序列化为对外字典（供 API / 消息管道 / SE 框架消费）。"""
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "status": self.status,
            "artifacts": self.artifacts,
            "next_skills": self.next_skills,
        }

    @classmethod
    def fail(cls, message: str, status: str = "failed") -> SkillResult:
        """快捷构造失败结果。

        注意：命名 fail 而非 error——避免与 dataclass 字段 error 同名冲突
        （修复：同名时字段默认值不生效，result.error 会访问到 classmethod）。
        """
        return cls(ok=False, error=message, status=status)

    @classmethod
    def ok_result(cls, data: dict[str, Any] | None = None, **kw: Any) -> SkillResult:
        """快捷构造成功结果。"""
        return cls(ok=True, data=data or {}, **kw)


def now_ms() -> float:
    return time.perf_counter() * 1000
