"""智能层网关：「LLM 可剥离」的唯一接缝。

母项目（完整）：``build_workspace`` 可加载 → workspace 承载 code_gen 技能（LLM 完整链路），
``/api/chat`` 走 LLM 聊天、``/api/code/generate`` 走 workspace.run("code_gen")。

开源仓（剥离）：无 ``src/deps``、``src/skills``、``llm/``、``agents/`` → ``build_workspace``
导入失败 → 置 ``None``，server / ui_adapter 降级为确定性生成
（``FunctionalAssembler.assemble_routed``，不依赖任何 LLM）。

这样「确定性服务」和「LLM 增强服务」共用一套 server 骨架，智能层可插拔、可剥离。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _try_import_build_workspace() -> Callable[..., Any] | None:
    """可选加载智能层 workspace 构建器。

    母项目有 ``src.deps.assembly`` → 返回 build_workspace；
    开源仓剥离智能层 → ImportError → None（server 降级确定性模式）。
    """
    try:
        from src.deps.assembly import build_workspace

        return build_workspace
    except ImportError:
        return None


# 智能层 workspace 构建器（None = 智能层剥离，纯确定性模式）
build_workspace = _try_import_build_workspace()


def is_llm_available() -> bool:
    """智能层（LLM 指挥层）是否可用：母项目 True，开源仓 False。"""
    return build_workspace is not None


def deterministic_generate(text: str, mcu: str = "") -> dict[str, Any]:
    """确定性生成（无 LLM）：文字 → ``assemble_routed`` → E 契约。

    对齐 ``ui_adapter.code_generate`` 的返回形状
    ``{status, code, explanation, warnings, passed, logs}``，
    让 UI / 调用方在「LLM 增强」与「确定性」之间无感切换。

    mcu 无法 resolve（如开源仓只有最小肖像、传了别的芯片名）时，
    降级到纯通用路径（不贴芯片特有引脚/AF/时钟），仍尽力产出。
    """
    from knowledge.template_forge.functional_assembler import FunctionalAssembler

    def _gen(chip: str | None) -> dict[str, Any] | None:
        return FunctionalAssembler().assemble_routed(text, chip=chip)

    try:
        result = _gen(mcu or None)
    except Exception:
        # resolve 失败（芯片画像不存在）→ 纯通用降级，不因一个芯片名卡死整条生成
        try:
            result = _gen(None)
        except Exception as exc:  # noqa: BLE001 —— 兜底：确定性生成失败不抛给调用方
            return {
                "status": "error",
                "code": "",
                "passed": False,
                "explanation": f"确定性生成异常：{exc}",
                "warnings": [],
                "logs": [str(exc)],
            }

    if result is None:
        return {
            "status": "error",
            "code": "",
            "passed": False,
            "explanation": "生成未返回结果",
            "warnings": [],
            "logs": [],
        }

    files = result.get("files") or {}
    main_c = next((v for k, v in files.items() if k.endswith("/main.c")), "")
    templates = result.get("templates") or []
    conflicts = result.get("conflicts") or []
    missing = result.get("missing")

    passed = bool(files) and bool(main_c)
    if passed:
        explanation = f"确定性生成：识别到模板 {templates}，产出 {len(files)} 文件完整工程"
    elif missing:
        explanation = str(missing)
    else:
        explanation = "确定性生成：未产出完整工程（无 main.c）"

    return {
        "status": "ok" if passed else "error",
        "code": main_c,
        "passed": passed,
        "explanation": explanation,
        "warnings": [str(c) for c in conflicts],
        "logs": [],
    }
