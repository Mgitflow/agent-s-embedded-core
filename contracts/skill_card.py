"""Skill Card 标准：技能的可注册「身份证」（name/能力清单/输入输出契约/入口/MCP 映射），格式与 manifest.capabilities 对齐。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillCard:
    """技能身份证——组织契约接入的最小单元。"""

    name: str                          # 技能名（如 code_gen / 析微）
    description: str                   # 一句话说明
    version: str = "1.0.0"
    capabilities: list[str] = field(default_factory=list)   # 能力清单（如 ["代码生成", "编译检查"]）
    inputs: dict[str, str] = field(default_factory=dict)    # 输入契约 {参数名: 说明}
    outputs: dict[str, str] = field(default_factory=dict)   # 输出契约 {字段: 说明}
    entrypoint: str = ""               # 调用入口（HTTP 端点 / 函数名）
    mcp_tools: list[str] = field(default_factory=list)      # 映射的 MCP 工具名（若有）

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": self.capabilities,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "entrypoint": self.entrypoint,
            "mcp_tools": self.mcp_tools,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillCard:
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            capabilities=list(data.get("capabilities", [])),
            inputs=dict(data.get("inputs", {})),
            outputs=dict(data.get("outputs", {})),
            entrypoint=data.get("entrypoint", ""),
            mcp_tools=list(data.get("mcp_tools", [])),
        )

    def validate(self) -> list[str]:
        """返回缺失必填字段（空列表=合法 Card）。"""
        missing = []
        if not self.name:
            missing.append("name")
        if not self.description:
            missing.append("description")
        if not self.capabilities:
            missing.append("capabilities")
        return missing
