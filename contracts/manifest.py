"""Agent 能力注册契约：框架据此发现/调用/监控 Agent，不直接 import 其内部模块。"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    """Agent 在五层架构中的角色。"""

    LEFT_BRAIN = "left_brain"      # Agent-S，技术中枢
    RIGHT_BRAIN = "right_brain"    # Agent-E，体验中枢
    NERVE = "nerve"                # Agent-C，神经中枢/群聊空间
    EYE = "eye"                    # Agent-T，感知/翻译中枢
    HAND = "hand"                  # Agent-O，执行中枢
    FRAMEWORK = "framework"        # Agent-SE 自身


@dataclass
class SkillSchema:
    """单个技能的输入输出契约。"""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    async_only: bool = False
    dangerous: bool = False  # 是否需要人类确认


@dataclass
class Capability:
    """Agent 暴露的能力项。"""

    name: str
    description: str = ""
    skills: list[SkillSchema] = field(default_factory=list)


@dataclass
class MemoryAssetRef:
    """组织记忆资产声明（ORG_MEMORY_DESIGN 落地）。

    对齐 TencentDB Agent Memory 四类资产：chat / skill / wiki / codegraph。
    各项目在 manifest 声明自有记忆资产，SE 治理层据此做注册/权限/审计。
    """

    asset_type: str = "chat"          # chat | skill | wiki | codegraph
    asset_id: str = ""                # 所有者/资产名（如 agent-s/template_forge）
    summary: str = ""
    visibility: str = "team"          # private | team | restricted（默认 team 可被组织引用）
    version: str = ""
    trust: str = "reviewed"           # verified | reviewed | tentative
    lifecycle: str = "active"         # active | archived | deprecated


@dataclass
class AgentManifest:
    """
    Agent 注册清单。

    每个 Agent 启动时向 registry 提交此清单，框架据此进行路由与健康检查。
    """

    name: str
    role: AgentRole
    version: str = "0.1.0"
    description: str = ""
    endpoint: str = "http://localhost:8000"
    health_endpoint: str = "/health"
    capabilities: list[Capability] = field(default_factory=list)
    max_concurrent: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    memory_assets: list[MemoryAssetRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "version": self.version,
            "description": self.description,
            "endpoint": self.endpoint,
            "health_endpoint": self.health_endpoint,
            "capabilities": [
                {
                    "name": c.name,
                    "description": c.description,
                    "skills": [
                        {
                            "name": s.name,
                            "description": s.description,
                            "input_schema": s.input_schema,
                            "output_schema": s.output_schema,
                            "async_only": s.async_only,
                            "dangerous": s.dangerous,
                        }
                        for s in c.skills
                    ],
                }
                for c in self.capabilities
            ],
            "max_concurrent": self.max_concurrent,
            "metadata": self.metadata,
            "memory_assets": [
                {
                    "asset_type": a.asset_type,
                    "asset_id": a.asset_id,
                    "summary": a.summary,
                    "visibility": a.visibility,
                    "version": a.version,
                    "trust": a.trust,
                    "lifecycle": a.lifecycle,
                }
                for a in self.memory_assets
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentManifest":
        capabilities = []
        for c in data.get("capabilities", []):
            skills = [SkillSchema(**s) for s in c.get("skills", [])]
            capabilities.append(Capability(
                name=c["name"],
                description=c.get("description", ""),
                skills=skills,
            ))
        try:
            role = AgentRole(data.get("role", "left_brain"))
        except ValueError:
            role = AgentRole.LEFT_BRAIN
        memory_assets = [MemoryAssetRef(**a) for a in data.get("memory_assets", [])]
        return cls(
            name=data["name"],
            role=role,
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            endpoint=data.get("endpoint", "http://localhost:8000"),
            health_endpoint=data.get("health_endpoint", "/health"),
            capabilities=capabilities,
            max_concurrent=data.get("max_concurrent", 1),
            metadata=data.get("metadata", {}),
            memory_assets=memory_assets,
        )
