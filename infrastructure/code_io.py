"""代码文件 I/O 工具：将生成的代码保存到工作区，只依赖 infrastructure 层。"""
import os
import re
from datetime import datetime
from typing import cast

from infrastructure.config import SAVE, WORKSPACE_ROOT


def save_code(code: str, requirement: str, peripheral: str, workspace_root: str | None = None) -> str:
    """保存代码到工作区，返回文件路径。

    Args:
        code: 生成的 C 代码内容。
        requirement: 原始需求文本，用于生成文件名。
        peripheral: 外设名称，如 "GPIO"。
        workspace_root: 可选，自定义保存目录；默认使用配置中的 WORKSPACE_ROOT。

    Returns:
        保存后的文件绝对路径。
    """
    root = workspace_root or WORKSPACE_ROOT
    os.makedirs(root, exist_ok=True)

    safe_name = re.sub(r'[<>:"/\\|?*]', '', requirement[:cast(int, SAVE["max_name_length"])].replace(" ", "_"))
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{peripheral.lower()}_{safe_name}_{timestamp}{SAVE['extension']}"
    path = os.path.join(root, filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(code)

    return path
