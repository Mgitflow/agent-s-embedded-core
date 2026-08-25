"""StudioWorkspace 工作室：统一骨架的执行中枢，管三态/mode 与执行记录，对外只与 workspace 打交道。"""

from __future__ import annotations

import logging
import time
from typing import Any

from .context import SkillContext
from .registry import SkillRegistry, create_registry
from .result import SkillResult
from .skill import Skill

logger = logging.getLogger(__name__)

IDLE_MODE = "idle"


class StudioWorkspace:
    """工作室：技能发现 + 模式切换 + 执行编排 + 衔接广播。"""

    def __init__(
        self,
        ctx: SkillContext,
        registry: SkillRegistry | None = None,
    ) -> None:
        self.ctx = ctx
        self.registry: SkillRegistry = registry or create_registry()
        self.current_mode: str = IDLE_MODE
        self._history: list[dict[str, Any]] = []
        self._history_limit = 50

    # --- 状态 ---

    @property
    def available_modes(self) -> list[str]:
        """可切换的工作区间 = 已实例化的技能名。"""
        return self.registry.names

    def get_status(self) -> dict[str, Any]:
        """工作室状态快照。"""
        return {
            "agent": self.ctx.agent_name,
            "current_mode": self.current_mode,
            "available_modes": self.available_modes,
            "skill_count": len(self.registry.names),
            "deps": self.ctx.health(),
            "recent_runs": list(reversed(self._history[-10:])),
        }

    # --- 模式切换 ---

    def set_mode(self, mode: str) -> dict[str, Any]:
        """切换当前工作区间（只在已实例化的技能里选）。"""
        if mode == IDLE_MODE:
            self.current_mode = IDLE_MODE
            return {"ok": True, "mode": mode}
        if not self.registry.has(mode):
            return {
                "ok": False,
                "mode": mode,
                "error": f"未实例化的技能: {mode}，可用: {self.available_modes}",
            }
        self.current_mode = mode
        logger.info("工作室切换到模式: %s", mode)
        return {"ok": True, "mode": mode}

    def get_skill(self, name: str) -> Skill | None:
        return self.registry.get(name)

    # --- 执行 ---

    async def run(self, skill: str, params: dict[str, Any] | None = None) -> SkillResult:
        """执行指定技能（统一契约：run(ctx, **params) -> SkillResult）。"""
        target = self.registry.get(skill)
        if target is None:
            return SkillResult.fail(f"未实例化的技能: {skill}")

        t0 = time.perf_counter()
        try:
            result = await target.run(self.ctx, **(params or {}))
        except Exception as e:  # noqa: BLE001
            logger.exception("技能 %s 执行异常", skill)
            result = SkillResult.fail(f"{type(e).__name__}: {e}")
        result.elapsed_ms = (time.perf_counter() - t0) * 1000

        self._record(skill, result)
        # 2026-08-06：衔接广播仅在 transport 注入时触发（当前 SE 未接，零空转开销）
        if self.ctx.transport is not None:
            await self._announce(skill, result)
        return result

    async def run_current(self, params: dict[str, Any] | None = None) -> SkillResult:
        """执行当前工作区间对应的技能。"""
        if self.current_mode == IDLE_MODE:
            return SkillResult.fail("当前为空闲模式，请先 set_mode 或指定 run(skill=...)")
        return await self.run(self.current_mode, params)

    # --- 衔接 ---

    def _record(self, skill: str, result: SkillResult) -> None:
        self._history.append({
            "ts": time.time(),
            "skill": skill,
            "ok": result.ok,
            "status": result.status,
            "elapsed_ms": round(result.elapsed_ms, 1),
            "error": result.error,
        })
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit:]

    async def _announce(self, skill: str, result: SkillResult) -> None:
        """技能执行完成后广播衔接事件（SE 在线时通知，离线静默）。"""
        transport = self.ctx.transport
        if transport is None or not result.ok:
            return
        topic = "skill_done"
        try:
            await transport.broadcast({
                "type": "event",
                "topic": topic,
                "sender": self.ctx.agent_name,
                "payload": {
                    "skill": skill,
                    "ok": result.ok,
                    "status": result.status,
                    "summary": result.data.get("summary", ""),
                    "artifacts_summary": {k: str(v)[:120] for k, v in result.artifacts.items()},
                },
            })
        except Exception as e:  # noqa: BLE001
            logger.debug("衔接广播失败（SE 可能离线）: %s", e)
