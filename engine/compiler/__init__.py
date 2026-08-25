"""编译调度链路契约：定义 CompilePipeline/CompileStage/StageResult，四阶段为生成→Makefile→编译→校验→回流。"""
from engine.compiler.pipeline import CompilePipeline, CompileResult, CompileStage, StageResult

__all__ = ["CompilePipeline", "CompileResult", "CompileStage", "StageResult"]
