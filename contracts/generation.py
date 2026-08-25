"""代码生成层契约：定义 Chunk/CodeSkill 输入输出数据结构。"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """代码生成产物"""
    content: str
    status: str = "ok"
    scene: str = "init"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeSkillInput:
    plan: Any  # PlannerOutput
    user_input: str


@dataclass
class CodeSkillOutput:
    status: str
    code: str = ""
    blocks: dict[str, str] = field(default_factory=dict)
    peripheral_type: str = ""
    message: str = ""
    raw_response: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)  # 标准工程文件树 {rel_path: content}（识别套式/标准工程填充）

    # v1.3.0 backward-compat properties
    @property
    def source(self) -> str:
        return self.status

    @property
    def content(self) -> str:
        return self.blocks.get("main", self.code)

    @property
    def scene(self) -> str:
        return self.blocks.get("scene", "init")
