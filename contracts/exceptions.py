"""统一业务异常层次：替代裸 Exception 与隐式 None 传播，上层统一捕获并降级。"""


class AgentSError(Exception):
    """Agent-S 所有业务异常的基类。"""


# ── 模型层 ──
class ModelError(AgentSError):
    """AI 模型调用失败（超时/断网/模型未加载）。"""


# ── 代码生成层 ──
class CodeGenError(AgentSError):
    """代码生成失败（LLM 返回空/模板兜底也失败）。"""


class CompileError(AgentSError):
    """编译验证失败。"""


# ── 知识库层 ──
class KnowledgeError(AgentSError):
    """知识库操作失败。"""


class KnowledgeIOError(KnowledgeError):
    """知识库文件读写失败（路径不存在/权限不足）。"""


# ── 外设层 ──
class PeripheralError(AgentSError):
    """外设操作失败（不支持的外设/参数无效）。"""


class ValidatorError(AgentSError):
    """代码校验失败。"""


# ── 存储层 ──
class StorageError(AgentSError):
    """Beaker/数据库存储失败。"""


# ── 桥接层 ──
class BridgeError(AgentSError):
    """Agent-E 通信失败。"""


# ── 配置层 ──
class ConfigError(AgentSError):
    """配置文件读取或校验失败。"""


# ── 芯片解析层 ──
class ChipResolutionError(AgentSError):
    """芯片解析失败（未知型号/系列，或材料缺失）。切换机制 fail-closed 专用。"""


# ── 流水线调度层 ──
class PipelineError(AgentSError):
    """流水线调度异常基类。"""


class RecoverableError(PipelineError):
    """阶段执行失败但可重试/降级。"""


class FatalError(PipelineError):
    """阶段执行失败且无法恢复，整条流水线失败。"""
