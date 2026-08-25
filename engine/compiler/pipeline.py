"""编译调度链路：编排「工程生成→Makefile→arm-gcc 编译→产物校验→回流」四阶段，工具链缺失只 skipped 不阻塞，失败写入 error_sink。"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CompileStage(str, Enum):
    """编译调度阶段，与 docs/DESIGN_compile_pipeline.md 的四段链路一一对应。"""

    GENERATE_MAKEFILE = "generate_makefile"
    BUILD = "build"
    VERIFY_ARTIFACT = "verify_artifact"
    FEEDBACK_REFLUX = "feedback_reflux"


@dataclass
class StageResult:
    """单个阶段的执行结果。"""

    stage: CompileStage
    passed: bool = False
    skipped: bool = True
    reason: str = ""
    error: str | None = None

    @property
    def label(self) -> str:
        """阶段摘要，如 '[build] passed (2s)'。"""
        if self.skipped:
            return f"[{self.stage.value}] skipped"
        if self.passed:
            return f"[{self.stage.value}] passed"
        return f"[{self.stage.value}] failed"


@dataclass
class CompileResult:
    """整条编译链路的执行结果。"""

    output_dir: str = ""
    stages: list[StageResult] = field(default_factory=list)
    artifact_path: str | None = None

    @property
    def passed(self) -> bool:
        """真编译是否通过：BUILD 阶段必须真实执行且 passed（fail-closed）。

        2026-08-20 修复（fail-open → fail-closed）：此前逻辑「有执行阶段则 all(passed)」，
        工具链缺失时 BUILD 被 skipped、但 GENERATE_MAKEFILE 执行成功，executed 非空 →
        all([True])=True，导致「没编译却报编译通过」。现改为：BUILD 未真实执行（skipped）
        即 False——工具链缺失绝不谎报通过。
        """
        build = self.stage(CompileStage.BUILD)
        if build is None or build.skipped:
            return False
        return build.passed

    @property
    def skipped(self) -> bool:
        """所有阶段均未执行 → True。"""
        return all(s.skipped for s in self.stages)

    def stage(self, name: CompileStage) -> StageResult | None:
        """按阶段名取结果。"""
        for s in self.stages:
            if s.stage is name:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        """序列化为对外字典。"""
        return {
            "output_dir": self.output_dir,
            "passed": self.passed,
            "skipped": self.skipped,
            "artifact_path": self.artifact_path,
            "stages": [
                {
                    "stage": s.stage.value,
                    "passed": s.passed,
                    "skipped": s.skipped,
                    "reason": s.reason,
                    "error": s.error,
                }
                for s in self.stages
            ],
        }


class CompilePipeline:
    """编译调度编排器（四阶段已接线）。"""

    def __init__(
        self,
        *,
        enabled: bool = True,
        knowledge_manager: Any | None = None,
        reflux_callback: Callable[[bool, dict[str, Any], dict[str, Any]], str] | None = None,
    ) -> None:
        """编译调度编排器（四阶段已接线）。

        :param reflux_callback: 回流回调 (passed, report, context) -> 备注。
            由组装层（src.deps.assembly）注入，engine 层不直接依赖 agents 服务——
            保持分层单向（arch_guard 硬规则）。
        """
        self._enabled = enabled
        self._km = knowledge_manager
        self._reflux_callback = reflux_callback
        self._last_stages: list[StageResult] = []

    # ------------------------------------------------------------------
    # 编排
    # ------------------------------------------------------------------

    def run(self, context: dict[str, Any]) -> CompileResult:
        """执行编译链路。

        context 约定键：output_dir（必需）、chip、peripherals、source_files、
        scene、code_artifact（回流用）。
        """
        output_dir = context.get("output_dir", "")
        if not self._enabled:
            logger.info("CompilePipeline: disabled, all stages skipped")
            return CompileResult(output_dir="")
        if not output_dir or not isinstance(output_dir, str) or not os.path.isdir(output_dir):
            logger.info("CompilePipeline: output_dir 无效或不存在, skipped")
            return CompileResult(output_dir="")

        result = CompileResult(output_dir=output_dir)
        for stage in CompileStage:
            stage_result = self._run_stage(stage, context)
            result.stages.append(stage_result)
            self._last_stages = list(result.stages)
            logger.info("CompilePipeline: %s", stage_result.label)

        # 产物路径
        build = result.stage(CompileStage.VERIFY_ARTIFACT)
        if build and build.passed and build.reason:
            result.artifact_path = build.reason
        return result

    def _run_stage(self, stage: CompileStage, context: dict[str, Any]) -> StageResult:
        """按阶段分发执行。"""
        try:
            if stage is CompileStage.GENERATE_MAKEFILE:
                return self._stage_generate_makefile(context)
            if stage is CompileStage.BUILD:
                return self._stage_build(context)
            if stage is CompileStage.VERIFY_ARTIFACT:
                return self._stage_verify_artifact(context)
            if stage is CompileStage.FEEDBACK_REFLUX:
                return self._stage_feedback_reflux(context)
        except Exception as e:  # noqa: BLE001
            logger.exception("CompilePipeline 阶段 %s 异常", stage.value)
            return StageResult(stage=stage, passed=False, skipped=False, error=f"{type(e).__name__}: {e}")
        return StageResult(stage=stage, skipped=True, reason="unknown stage")

    # ------------------------------------------------------------------
    # 阶段实现
    # ------------------------------------------------------------------

    def _stage_generate_makefile(self, context: dict[str, Any]) -> StageResult:
        """Makefile 不存在则生成（peripherals 用于 HAL 源过滤）。"""
        from infrastructure.makefile_generator import generate_makefile

        output_dir = context["output_dir"]
        makefile = os.path.join(output_dir, "Makefile")
        if os.path.exists(makefile):
            return StageResult(
                stage=CompileStage.GENERATE_MAKEFILE,
                passed=True,
                skipped=False,
                reason="Makefile 已存在",
            )

        chip = context.get("chip") or ""
        if not chip:
            return StageResult(
                stage=CompileStage.GENERATE_MAKEFILE,
                passed=False,
                skipped=False,
                error="缺少 chip（无法确定编译目标架构）",
            )
        path = generate_makefile(
            output_dir,
            chip,
            peripherals=context.get("peripherals"),
            source_files=context.get("source_files"),
        )
        return StageResult(
            stage=CompileStage.GENERATE_MAKEFILE,
            passed=True,
            skipped=False,
            reason=f"Makefile 已生成: {os.path.basename(path)}",
        )

    def _stage_build(self, context: dict[str, Any]) -> StageResult:
        """调用 make -j4 真编译；工具链缺失 → skipped。"""
        from infrastructure.makefile_generator import compile_check

        output_dir = context["output_dir"]
        error = compile_check(output_dir)
        if error is None:
            return StageResult(
                stage=CompileStage.BUILD,
                passed=True,
                skipped=False,
                reason="make 编译成功",
            )
        if "not found" in error.lower():
            return StageResult(stage=CompileStage.BUILD, skipped=True, reason=error)
        return StageResult(stage=CompileStage.BUILD, passed=False, skipped=False, error=error)

    def _get_last(self, stage: CompileStage) -> StageResult | None:
        """取上一轮某阶段的执行结果。"""
        for s in reversed(self._last_stages):
            if s.stage is stage:
                return s
        return None

    def _stage_verify_artifact(self, context: dict[str, Any]) -> StageResult:
        """校验编译产物存在且非空（elf/hex/bin 任一）。"""
        build = self._get_last(CompileStage.BUILD)
        if build is not None and build.skipped:
            return StageResult(
                stage=CompileStage.VERIFY_ARTIFACT,
                skipped=True,
                reason="build 未执行（工具链缺失），跳过产物校验",
            )
        output_dir = context["output_dir"]
        for name in ("firmware.elf", "firmware.hex", "firmware.bin"):
            path = os.path.join(output_dir, name)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return StageResult(
                    stage=CompileStage.VERIFY_ARTIFACT,
                    passed=True,
                    skipped=False,
                    reason=path,
                )
        return StageResult(
            stage=CompileStage.VERIFY_ARTIFACT,
            passed=False,
            skipped=False,
            error="未找到编译产物（firmware.elf/hex/bin）",
        )

    def _stage_feedback_reflux(self, context: dict[str, Any]) -> StageResult:
        """编译结果写回流通道：失败 → error_sink（E_COMPILE_FAIL），成功 → verified_sink。"""
        build = None
        for s in self._last_stages or []:
            if s.stage is CompileStage.BUILD:
                build = s
                break
        if build is None:
            return StageResult(stage=CompileStage.FEEDBACK_REFLUX, skipped=True, reason="无 build 结果")

        if build.skipped:
            return StageResult(
                stage=CompileStage.FEEDBACK_REFLUX, skipped=True, reason="build 未执行（工具链缺失）"
            )

        try:
            if build.passed:
                # 回流回调由组装层注入（engine 不直接依赖 agents 服务）
                if self._reflux_callback is not None:
                    reflux_note = self._reflux_callback(
                        True,
                        {"scene": context.get("scene", "init"), "approved": True},
                        context,
                    )
                elif self._km is not None:
                    reflux_note = "编译通过（未注入回流回调，跳过回流）"
                else:
                    reflux_note = "编译通过（无知识管理器，回流跳过）"
                return StageResult(
                    stage=CompileStage.FEEDBACK_REFLUX, passed=True, skipped=False,
                    reason=reflux_note,
                )
            # 编译失败 → 回流回调（error 通道）
            report = {
                "scene": context.get("scene", "init"),
                "approved": False,
                "compile_check": {"passed": False, "error": build.error},
            }
            if self._reflux_callback is not None:
                reflux_note = self._reflux_callback(False, report, context)
                logger.info("CompilePipeline reflux(fail): %s", reflux_note)
            elif self._km is not None:
                logger.warning("编译失败（未注入回流回调，跳过回流）: %s", build.error)
            else:
                logger.warning("编译失败（无知识管理器，回流跳过）: %s", build.error)
            return StageResult(
                stage=CompileStage.FEEDBACK_REFLUX,
                passed=False,
                skipped=False,
                error=build.error or "编译失败",
            )
        except Exception as e:  # noqa: BLE001
            return StageResult(
                stage=CompileStage.FEEDBACK_REFLUX,
                skipped=True,
                reason=f"回流失败（不影响编译结果）: {e}",
            )
