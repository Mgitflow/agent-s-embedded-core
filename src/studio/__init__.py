"""标准工作室骨架（空壳契约）：只定义 Skill/SkillResult/SkillContext 契约，具体实现由外部引入。"""

from .context import SkillContext
from .registry import SkillRegistry, create_registry, register_skill, registered_names
from .result import SkillResult
from .skill import Skill
from .workspace import IDLE_MODE, StudioWorkspace

__all__ = [
    "Skill",
    "SkillContext",
    "SkillResult",
    "SkillRegistry",
    "create_registry",
    "register_skill",
    "registered_names",
    "StudioWorkspace",
    "IDLE_MODE",
]
