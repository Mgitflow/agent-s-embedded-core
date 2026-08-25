"""数据契约与抽象接口：各子模块只定义本领域的数据类型或接口，互不依赖。"""
from contracts.assessment import AssessorInput, AssessorOutput
from contracts.enums import IntentType, KnowledgeStatus, RiskLevel, RuleLevel, Scene
from contracts.exceptions import FatalError, PipelineError, RecoverableError
from contracts.generation import Chunk, CodeSkillInput, CodeSkillOutput
from contracts.interfaces import (
    IAssessor,
    ICodeSkill,
    ILLMClient,
    IReflector,
    IRuleEngine,
)
from contracts.knowledge import CompatibilityResult, KnowledgeEntry
from contracts.knowledge_source import IKnowledgeSource
from contracts.planning import PlannerInput, PlannerOutput
from contracts.reflection import ReflectorInput, ReflectorOutput, ReviewLoopResult

__all__ = [
    "IntentType", "Scene", "RiskLevel", "RuleLevel", "KnowledgeStatus",
    "PlannerInput", "PlannerOutput",
    "CodeSkillInput", "CodeSkillOutput", "Chunk",
    "AssessorInput", "AssessorOutput",
    "ReflectorInput", "ReflectorOutput", "ReviewLoopResult",
    "KnowledgeEntry", "CompatibilityResult", "IKnowledgeSource",
    "PipelineError", "RecoverableError", "FatalError",
    # 抽象接口（有实现类的存活接口；死接口已于 2026-08-22 摘除）
    "IAssessor",
    "ICodeSkill",
    "IReflector",
    "IRuleEngine",
    "ILLMClient",
]
