"""骨架自检（self_check）——验证「空车能开」的骨架部分。

开源仓库不夹带血肉（芯片肖像/功能模板/手册数据），本自检只测**不依赖血肉**的骨架：
  1. 契约结构完整（CodeSkillOutput 字段）
  2. 校验规则数（确定性骨架的工艺标准，应为 106 条）
  3. 编排层核心模块可 import（识别 / 模板 / 校验 / 引脚分配 / 组装）
  4. 接口契约存在（抽象接口，血肉由此接入）

「完整文字 → 生成 → 编译」验证需要血肉数据，见 docs/VERIFICATION.md。

用法：python scripts/self_check.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_results: list[tuple[str, bool, str]] = []


def _check(name: str, fn) -> None:
    try:
        ok, detail = fn()
        _results.append((name, bool(ok), str(detail)))
    except Exception as exc:  # noqa: BLE001
        _results.append((name, False, f"{type(exc).__name__}: {str(exc)[:120]}"))


def _contract() -> tuple[bool, str]:
    from contracts.generation import CodeSkillOutput

    fields = set(getattr(CodeSkillOutput, "__dataclass_fields__", {}).keys())
    required = {"status", "code", "blocks", "peripheral_type", "files"}
    missing = required - fields
    if missing:
        return False, f"契约字段缺失 {sorted(missing)}"
    return True, f"契约字段 {sorted(required)} 齐全"


def _rules() -> tuple[bool, str]:
    from engine.validators import register_all
    from engine.validators.base import ValidatorRegistry

    registry = ValidatorRegistry()
    register_all(registry)
    n = len(getattr(registry, "_validators", {}))
    return n == 106, f"{n} 条校验规则"


def _imports() -> tuple[bool, str]:
    modules = [
        "contracts.generation",
        "contracts.interfaces",
        "engine.rule_engine",
        "engine.validators",
        "engine.compiler.pipeline",
        "knowledge.template_forge.pin_allocator",
        "knowledge.template_forge.block_assembler",
        "knowledge.template_forge.project_slicer",
        "knowledge.template_forge.chip_portrait_adapter",
        "knowledge.template_forge.industrial_contract",
        "knowledge.template_forge.defense_injector",
        "knowledge.template_forge.param_filler",
        "knowledge.template_forge.functional_templates",
        "knowledge.template_forge.pin_recognition",
    ]
    failed: list[str] = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{mod} ({type(exc).__name__})")
    if failed:
        return False, "导入失败: " + "; ".join(failed)
    return True, f"{len(modules)} 个编排模块可 import"


def _interfaces() -> tuple[bool, str]:
    import contracts.interfaces as iface

    names = [n for n in dir(iface) if not n.startswith("_") and n[0].isupper()]
    return bool(names), f"抽象接口 {len(names)} 个"


def main() -> int:
    _check("契约结构", _contract)
    _check("校验规则", _rules)
    _check("编排层 import", _imports)
    _check("接口契约", _interfaces)

    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"=== 骨架自检：{passed}/{len(_results)} 通过 ===")
    for name, ok, detail in _results:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}: {detail}")
    if passed == len(_results):
        print("\n骨架自检通过。完整生成验证需填入真实芯片包 + 功能模板（见 docs/VERIFICATION.md）。")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
