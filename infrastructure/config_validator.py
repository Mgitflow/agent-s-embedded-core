"""启动配置验证：启动时校验所有 AGENT_S_* 环境变量与必需资源就绪。"""
from __future__ import annotations

import dataclasses
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from contracts.exceptions import ConfigError
from infrastructure.config import ACTIVE_CHIP, DEFAULT_CHIP_NAME

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class AgentSConfig:
    """Agent-S 全量环境变量配置。

    所有字段均对应一个 AGENT_S_* 环境变量，默认值与 infrastructure.config 保持一致。
    """

    chip: str = ACTIVE_CHIP  # 与 infrastructure.config 保持一致（当前板子 apm32f407vgt6）
    chip_name: str = DEFAULT_CHIP_NAME
    workspace: str = ""
    llm_url: str = "http://127.0.0.1:1234/v1/chat/completions"
    llm_timeout: int = 300
    stream_timeout: int = 120
    model_r1: str = "oreal-deepseek-r1-distill-qwen-7b"
    model_code: str = "qwen2.5-coder-7b-instruct"
    model_vl: str = "qwen2.5-vl-7b-q4_0/qwen2.5-vl-7b-instruct"

    @classmethod
    def from_env(cls) -> AgentSConfig:
        """从环境变量加载配置，遇到非法值立即抛出 ConfigError。"""
        return cls(
            chip=os.environ.get("AGENT_S_CHIP", cls.chip),
            chip_name=os.environ.get("AGENT_S_CHIP_NAME", cls.chip_name),
            workspace=os.environ.get("AGENT_S_WORKSPACE", cls.workspace),
            llm_url=os.environ.get("AGENT_S_LLM_URL", cls.llm_url),
            llm_timeout=_parse_positive_int("AGENT_S_LLM_TIMEOUT", cls.llm_timeout),
            stream_timeout=_parse_positive_int("AGENT_S_STREAM_TIMEOUT", cls.stream_timeout),
            model_r1=os.environ.get("AGENT_S_MODEL_R1", cls.model_r1),
            model_code=os.environ.get("AGENT_S_MODEL_CODE", cls.model_code),
            model_vl=os.environ.get("AGENT_S_MODEL_VL", cls.model_vl),
        )

    def validate(self) -> list[str]:
        """校验配置语义，返回警告列表（空列表表示无警告）。"""
        warnings: list[str] = []

        if not self.chip:
            raise ConfigError("AGENT_S_CHIP 不能为空")

        if not self.chip_name:
            raise ConfigError("AGENT_S_CHIP_NAME 不能为空")

        parsed = urlparse(self.llm_url)
        if not parsed.scheme or not parsed.netloc:
            raise ConfigError(f"AGENT_S_LLM_URL 格式非法: {self.llm_url}")

        if self.llm_timeout < 1:
            warnings.append(f"AGENT_S_LLM_TIMEOUT 过小: {self.llm_timeout}s，建议 >= 1")
        if self.stream_timeout < 1:
            warnings.append(f"AGENT_S_STREAM_TIMEOUT 过小: {self.stream_timeout}s，建议 >= 1")

        return warnings


def _parse_positive_int(name: str, default: int) -> int:
    """解析正整数环境变量，失败时抛出 ConfigError。"""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是整数: {raw}") from exc
    if value <= 0:
        raise ConfigError(f"{name} 必须是正整数: {value}")
    return value


def validate_startup(config: dict[str, Any]) -> tuple[bool, list[str]]:
    """验证启动配置，返回 (是否通过, 警告列表)。

    该函数保留旧的 dict 接口以兼容现有调用方；内部优先使用 AgentSConfig.from_env()。
    """
    warnings: list[str] = []
    ok = True

    # 0. 环境变量语义校验
    try:
        cfg = AgentSConfig.from_env()
        env_warnings = cfg.validate()
        warnings.extend(env_warnings)
    except ConfigError as e:
        warnings.append(f"环境变量校验失败: {e}")
        return False, warnings

    # 1. 标准文件检查
    std_paths = config.get("standard_paths", {})
    for periph, path in std_paths.items():
        if not os.path.exists(path):
            warnings.append(f"标准文件缺失: [{periph}] {path}")
            ok = False

    # 2. Knowledge 目录检查
    kb_dirs = config.get("knowledge_dirs", {})
    for name, dir_path in kb_dirs.items():
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"已创建 knowledge 目录: {name}")
            except OSError as e:
                warnings.append(f"无法创建目录 {name}: {dir_path} ({e})")
                ok = False

    # 3. LLM 连接检查（可选，不阻塞启动）
    if config.get("check_llm", True):
        try:
            import requests

            url = config.get("llm_url", cfg.llm_url)
            if url:
                resp = requests.get(url.removesuffix("/chat/completions") + "/models", timeout=5)
                if resp.status_code == 200:
                    logger.info("LLM (LM Studio) 连接正常")
                else:
                    warnings.append(f"LLM 返回异常状态码: {resp.status_code}")
        except requests.exceptions.ConnectionError:
            warnings.append("LLM (LM Studio) 未连接 — 将使用模板兜底")
        except ImportError:
            warnings.append("requests 库未安装，跳过 LLM 连接检查")
        except ConfigError as e:
            warnings.append(f"LLM 连接检查失败: {e}")

    # 4. 工作区目录检查
    workspace = config.get("workspace_root", cfg.workspace)
    if workspace:
        try:
            os.makedirs(workspace, exist_ok=True)
        except OSError as e:
            warnings.append(f"工作区目录不可写: {workspace} ({e})")
            ok = False

    # 5. 芯片 Skill 包检查（拔插式：从 config.CHIPS_DIR 取）
    from infrastructure.config import CHIPS_DIR

    chip_skill_dir = Path(CHIPS_DIR) / cfg.chip
    if not chip_skill_dir.exists():
        warnings.append(f"芯片 Skill 包不存在: {chip_skill_dir}")
        ok = False
    else:
        manifest = chip_skill_dir / "manifest.yaml"
        if not manifest.exists():
            warnings.append(f"芯片 Skill manifest 缺失: {manifest}")
            ok = False

    return ok, warnings
