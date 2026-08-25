"""校验器注册表：自动扫描本目录并调用各模块的 register() 完成注册，新增外设无需改本文件。"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

from engine.validators.base import ValidatorRegistry

logger = logging.getLogger(__name__)


def register_all(registry: ValidatorRegistry) -> None:
    """自动扫描 engine/validators/ 目录并注册所有外设校验器。"""
    package_dir = Path(__file__).resolve().parent
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        name = module_info.name
        if name in ("base", "__init__"):
            continue
        try:
            module = importlib.import_module(f"engine.validators.{name}")
            register_func = getattr(module, "register", None)
            if callable(register_func):
                register_func(registry)
                logger.debug(f"Validator module registered: {name}")
            else:
                logger.warning(f"Validator module {name} has no register() function")
        except (ImportError, AttributeError, TypeError) as e:
            logger.warning(f"Failed to load validator module {name}: {e}")
