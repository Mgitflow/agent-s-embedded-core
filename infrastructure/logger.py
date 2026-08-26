"""日志配置：控制台人类可读 + 文件 JSON 结构化（带 request_id），便于链路追踪。"""
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Any

from infrastructure.config import PROJECT_ROOT
from infrastructure.request_id import get_request_id

# 单个日志文件最大 10 MB，保留 5 个备份
MAX_LOG_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

# 全局 logger，供 ui_print 使用
_ui_logger = None


class JsonFormatter(logging.Formatter):
    """文件日志 JSON 结构化格式（含 request_id 贯穿）。"""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": get_request_id(),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure application logging."""
    global _ui_logger

    # Windows 默认终端多为 GBK，遇到 emoji 会抛 UnicodeEncodeError；
    # 这里让 stdout/stderr 用替换字符，保证程序不崩。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加 handler（多入口重复 setup_logging）
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        # 控制台：人类可读
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        root.addHandler(console)

        # 文件：JSON 结构化（request_id 贯穿）
        # ：文件被占用（IDE/索引服务锁）时降级为仅控制台，
        # 避免 setup_logging 崩溃导致整个服务/测试导入失败。
        try:
            file_handler = RotatingFileHandler(
                PROJECT_ROOT / "agent_s.log",
                maxBytes=MAX_LOG_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(JsonFormatter())
            root.addHandler(file_handler)
        except OSError:
            logging.getLogger("agent_s").warning(
                "agent_s.log 无法写入（文件被占用），降级为仅控制台输出"
            )

    _ui_logger = logging.getLogger("agent_s.ui")
    return logging.getLogger("agent_s")


def ui_print(*args: Any, **kwargs: Any) -> None:
    """
    统一 UI 输出：同时 print 到控制台 + 写入日志文件
    用于替换项目中的裸 print() 调用
    在 GBK 等非 UTF-8 终端上自动忽略无法编码的 emoji，避免程序崩溃。
    """
    msg = " ".join(str(a) for a in args)
    end = kwargs.get("end", "\n")
    file = kwargs.get("file", sys.stdout)
    flush = kwargs.get("flush", False)

    try:
        print(msg, end=end, file=file, flush=flush)
    except UnicodeEncodeError:
        enc = getattr(file, "encoding", None) or "ascii"
        safe = msg.encode(enc, errors="ignore").decode(enc)
        print(safe, end=end, file=file, flush=flush)
    if _ui_logger:
        _ui_logger.info(msg.rstrip("\n"))
