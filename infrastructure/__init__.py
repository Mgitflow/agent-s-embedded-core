"""基础设施：配置、路径、日志、启动。"""
from infrastructure.config import PROJECT_ROOT, WORKSPACE_ROOT
from infrastructure.logger import setup_logging

__all__ = ["PROJECT_ROOT", "WORKSPACE_ROOT", "setup_logging"]
