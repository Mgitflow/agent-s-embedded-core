"""模板渲染工具：meta 默认值补齐 + $ 模板渲染（单区块拼装用）。

从 code_skill/forge_tools.py 迁来（forge_tools 随 forge_engine 归档为旧套）：
derive_params / fill 是单区块拼装（block_assembler）的活依赖，其余
（infer_template_id / apply_fixed_pins / forge_code）已随 forge_engine 归档。
迁到 knowledge 层，消除 knowledge → src 的跨层 import。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# 锻造模板库目录（knowledge/template_forge/forge_templates/）
FORGE_DIR = Path(__file__).resolve().parent / "forge_templates"


def _find_meta(template_id: str) -> Path | None:
    """定位模板 meta 文件（兼容平铺/分目录两种形态）。"""
    for candidate in (
        Path(FORGE_DIR) / f"{template_id}.meta.json",
        Path(FORGE_DIR) / template_id.split("_")[0] / f"{template_id}.meta.json",
    ):
        if candidate.exists():
            return candidate
    return None


def derive_params(template_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """meta 默认值补齐（overrides 优先，default 兜底）。"""
    params: dict[str, Any] = dict(overrides)
    meta_path = _find_meta(template_id)
    if meta_path is None or not meta_path.exists():
        return params
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for key, info in (meta.get("params") or {}).items():
            if key in params:
                continue
            default = info.get("default")
            if default is not None:
                params[key] = default
    except (OSError, json.JSONDecodeError):
        pass
    return params


def fill(template: str, params: dict[str, Any]) -> str | None:
    """$ 模板渲染（string.Template）。缺参数安全降级。"""
    from string import Template as StrTemplate

    try:
        return StrTemplate(template).substitute(params)
    except KeyError:
        return StrTemplate(template).safe_substitute(params)
    except ValueError as exc:
        _log.debug("模板渲染失败: %s", exc)
        return None
