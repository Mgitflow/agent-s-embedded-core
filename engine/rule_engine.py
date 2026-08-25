"""规则引擎：加载外设标准 JSON 并按 error_code 绑定到 validators 校验函数，执行 MUST/SHOULD/MAY 分级校验。"""
import json
import logging
from typing import Any

from contracts.enums import RuleLevel
from contracts.exceptions import ValidatorError
from contracts.interfaces import IRuleEngine
from contracts.rule_result import RuleResult  # noqa: F401  (re-export 兼容旧引用)
from engine.validators import register_all
from engine.validators.base import ValidatorRegistry

logger = logging.getLogger(__name__)


class RuleEngine(IRuleEngine):
    def __init__(self, standard_paths: dict[str, str] | str | None = None) -> None:
        """v2.0.0: 接受 {外设名: 标准文件路径} 字典
        向后兼容：传入字符串时自动包装为 {"GPIO": path}"""
        self._registry = ValidatorRegistry()
        register_all(self._registry)
        self._standards: dict[str, dict[str, Any]] = {}
        self._static_rules: dict[str, list[dict[str, Any]]] = {}

        if standard_paths is None:
            pass
        elif isinstance(standard_paths, str):
            # 向后兼容：单路径字符串
            self._standards["GPIO"] = self._load_standard(standard_paths)
        else:
            for peripheral, path in standard_paths.items():
                self._standards[peripheral] = self._load_standard(path)

        loaded = list(self._standards.keys())
        logger.info(f"RuleEngine: loaded standards for {loaded}")

    def _load_standard(self, path: str) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            tmp = data
            return tmp if isinstance(tmp, dict) else {}
        except (ValidatorError, OSError) as e:
            logger.warning(f"Failed to load standard '{path}': {e}")
            return {"scenes": {}}

    def validate(self, scene: str, context: dict[str, Any]) -> list[RuleResult]:
        """v2.0.0: 按 peripheral 自动选择对应标准；未指定时遍历所有标准"""
        peripheral = context.get("peripheral", "").upper()

        # 优先使用指定外设的标准
        standard = self._standards.get(peripheral)
        if standard:
            return self._validate_with_standard(scene, context, standard)

        # 回退：遍历所有标准
        all_results = []
        for std in self._standards.values():
            all_results.extend(self._validate_with_standard(scene, context, std))
        if all_results:
            return all_results

        logger.info(f"Scene '{scene}' not found in any standard, skipping validation")
        return []

    def _validate_with_standard(self, scene: str, context: dict[str, Any], standard: Any) -> list[RuleResult]:
        # 2026-08-14 防御：standard 可能是 list（某些标准文件顶层是列表而非 dict）
        # 此前直接 .get 抛 unhashable TypeError，多外设用例（combo）炸 GoldenBench
        if not isinstance(standard, dict):
            return []
        scenes = standard.get("scenes")
        if not isinstance(scenes, dict):
            return []
        scene_rules = scenes.get(scene)
        if not scene_rules:
            return []

        rules = scene_rules.get("rules", [])
        results = []

        for rule in rules:
            rule_id = rule.get("id", "unknown")
            level_str = rule.get("level", "MUST")
            level = RuleLevel(level_str) if level_str in RuleLevel.__members__ else RuleLevel.MUST
            error_code = rule.get("error_code", "")
            description = rule.get("description", "")

            validator = self._registry.get(error_code)
            if validator:
                try:
                    passed = validator(context)
                except (ValidatorError, OSError) as e:
                    logger.error(f"Validator '{error_code}' failed: {e}")
                    passed = False
            else:
                passed = self._check_violation_list(context, error_code)

            if not passed:
                msg = f"[{rule_id}] HARD FAIL: {description}"
                if error_code:
                    msg += f" (code: {error_code})"
                logger.warning(msg)
            else:
                msg = f"[{rule_id}] PASS"

            results.append(RuleResult(
                rule_id=rule_id, level=level,
                passed=passed, message=msg, error_code=error_code
            ))

        return results

    def _check_violation_list(self, context: dict[str, Any], error_code: str) -> bool:
        violations = context.get("violation_list", [])
        return error_code not in violations

    def is_scene_clean(self, scene: str, context: dict[str, Any]) -> bool:
        results = self.validate(scene, context)
        return all(r.passed for r in results if r.level == RuleLevel.MUST)
