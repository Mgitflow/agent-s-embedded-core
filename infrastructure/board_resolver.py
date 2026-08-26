"""板卡画像解析器：board.json 从板卡层（skills/boards/）优先解析，芯片层回退。

板卡层独立（板子是板，芯片是芯片）：board.json 迁到 skills/boards/ 下，
按 board.json 的 meta.mcu 匹配芯片。旧路径 skills/chips/{chip}/board.json 保留作回退
（未迁移芯片仍可用）。code_skill 与 context_loader 统一走本模块，避免两处重复。
"""
from __future__ import annotations

import json
from pathlib import Path


def resolve_board_json(root: Path, active_chip: str) -> Path | None:
    """解析板载 board.json：板卡层 skills/boards/ 优先，芯片层 skills/chips/ 回退。

    返回 board.json 路径；未找到返回 None（调用方降级处理）。
    """
    if not active_chip:
        return None

    # ① 板卡层（权威）：扫描 skills/boards/*/board.json，匹配 meta.mcu
    boards_root = root / "skills" / "boards"
    if boards_root.exists():
        for board_dir in sorted(boards_root.iterdir()):
            bj = board_dir / "board.json"
            if not bj.is_file():
                continue
            try:
                data = json.loads(bj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if str(data.get("meta", {}).get("mcu", "")).lower() == active_chip.lower():
                return bj

    # ② 芯片层回退（旧兼容，拔插式：chips 目录从 config 取）
    try:
        from infrastructure.config import CHIPS_DIR

        chips_root = Path(CHIPS_DIR)
    except Exception:  # noqa: BLE001
        chips_root = root / "skills" / "chips"
    legacy = chips_root / active_chip / "board.json"
    return legacy if legacy.is_file() else None
