"""外设统一注册表（薄包装）：只导出常量，数据由 bootstrap 注入，避免 contracts 直接读 data/registry/。"""
from __future__ import annotations

import threading

from contracts.interfaces import IPeripheralRegistry

# 注册表常量，由 bootstrap 调用 load_from_registry() 初始化。
PERIPHERAL_KEYWORDS: dict[str, list[str]] = {}
SCENE_KEYWORDS: dict[str, list[str]] = {}
CHIP_KEYWORDS: dict[str, str] = {}
PERIPHERAL_STRUCTURE: dict[str, list[str]] = {}
PERIPHERAL_STANDARDS: dict[str, str] = {}

# 并发安全：模块级可变全局 dict 的写入统一加锁（多线程并发组装时的竞态防护）
_load_lock = threading.RLock()


def load_from_registry(registry: IPeripheralRegistry) -> None:
    """从 IPeripheralRegistry 实现加载注册表数据到模块级常量（原地更新，保持引用稳定）。"""
    with _load_lock:
        PERIPHERAL_KEYWORDS.clear()
        PERIPHERAL_KEYWORDS.update(registry.get_peripheral_keywords())
        SCENE_KEYWORDS.clear()
        SCENE_KEYWORDS.update(registry.get_scene_keywords())
        CHIP_KEYWORDS.clear()
        CHIP_KEYWORDS.update(registry.get_chip_keywords())
        PERIPHERAL_STRUCTURE.clear()
        PERIPHERAL_STRUCTURE.update(registry.get_peripheral_structure())
        PERIPHERAL_STANDARDS.clear()
        PERIPHERAL_STANDARDS.update(registry.get_peripheral_standards())
