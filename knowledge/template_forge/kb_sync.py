"""共享知识库同步器：把 S 侧芯片肖像细化产物（pin_map/af_map/profile/功能模板/参考范本）归入 shared_knowledge 并登记 index.jsonl 索引。"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# 共享知识库根（集中化：AGENT_SHARED_KB > config 统一默认，不再写死 E:/Code）
try:
    from infrastructure.config import SHARED_KB_ROOT as _CFG_KB_ROOT

    KB_ROOT = Path(_CFG_KB_ROOT)
except Exception:  # noqa: BLE001
    KB_ROOT = Path(os.environ.get("AGENT_SHARED_KB", "shared_knowledge"))
# S 侧源（项目根 parents[2]）
S_ROOT = Path(__file__).resolve().parents[2]


class KnowledgeSync:
    """共享知识库同步器：S 细化产物 → 图书馆。"""

    def __init__(self, kb_root: Path | str | None = None) -> None:
        self._kb = Path(kb_root or KB_ROOT)
        self._portraits = self._kb / "chip_portraits"

    # ---- 同步入口 ----

    def sync_chip(self, chip: str = "apm32f407vgt6") -> dict[str, Any]:
        """同步单个芯片的肖像 + 模板 + 套式到共享库。"""
        chip_dir = self._portraits / chip
        chip_dir.mkdir(parents=True, exist_ok=True)
        src_chip = S_ROOT / "skills" / "chips" / chip
        result: dict[str, Any] = {"files": [], "index_entries": 0}

        # 1. 核心肖像文件（pin_map/af_map/profile + f103 的 remap_map）
        for fname in ("pin_map.json", "af_map.json", "profile.json", "remap_map.json"):
            src = src_chip / fname
            if src.exists():
                dst = chip_dir / fname
                shutil.copy2(src, dst)
                result["files"].append(f"chip_portraits/{chip}/{fname}")

        # 2. 功能模板归档
        tpl_dst = chip_dir / "templates"
        tpl_src = S_ROOT / "knowledge" / "template_forge" / "forge_templates" / "functional"
        if tpl_src.exists():
            tpl_dst.mkdir(parents=True, exist_ok=True)
            for f in tpl_src.glob("*.json"):
                shutil.copy2(f, tpl_dst / f.name)
                result["files"].append(f"chip_portraits/{chip}/templates/{f.name}")

        # 3. 参考范本归档（一举两用：模板库一员 + 核验标尺，补断点）
        ref_dst = chip_dir / "reference"
        ref_src = S_ROOT / "knowledge" / "template_forge" / "forge_templates" / "reference"
        if ref_src.exists():
            ref_dst.mkdir(parents=True, exist_ok=True)
            for f in ref_src.glob("*.json"):
                shutil.copy2(f, ref_dst / f.name)
                result["files"].append(f"chip_portraits/{chip}/reference/{f.name}")

        # 4. 芯片肖像注解 README
        readme = self._build_readme(chip, src_chip)
        (chip_dir / "README.md").write_text(readme, encoding="utf-8")
        result["files"].append(f"chip_portraits/{chip}/README.md")

        # 5. 索引登记
        result["index_entries"] = self._index_chip(chip)
        return result

    def sync_all(self) -> dict[str, Any]:
        """同步全部芯片。"""
        chips_dir = S_ROOT / "skills" / "chips"
        result: dict[str, Any] = {"chips": {}}
        for chip in chips_dir.iterdir():
            if chip.is_dir() and not chip.name.startswith("_"):
                result["chips"][chip.name] = self.sync_chip(chip.name)
        return result

    # ---- 索引 ----

    def _index_chip(self, chip: str) -> int:
        """登记芯片肖像到 index.jsonl（图书馆目录，只增不减）。"""
        index_path = self._kb / "index.jsonl"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        entries = [
            {"entry_id": f"chip-{uuid.uuid4().hex[:12]}", "category": "chip_portrait",
             "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "title": f"芯片肖像: {chip}",
             "tags": ["chip_portrait", "agent-s", chip], "source": "agent-s",
             "shared": True, "confidence": 1.0},
        ]
        with open(index_path, "a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return len(entries)

    # ---- README 注解 ----

    def _build_readme(self, chip: str, src_chip: Path) -> str:
        """芯片肖像注解（给 LLM 看：这块是什么、怎么用）。"""
        try:
            profile = json.loads((src_chip / "profile.json").read_text(encoding="utf-8"))
            meta = profile.get("meta", {})
        except Exception:  # noqa: BLE001
            meta = {}
        try:
            pin_map = json.loads((src_chip / "pin_map.json").read_text(encoding="utf-8"))
            pin_count = len(pin_map.get("pins", {}))
        except Exception:  # noqa: BLE001
            pin_count = 0
        try:
            af_map = json.loads((src_chip / "af_map.json").read_text(encoding="utf-8"))
            af_count = len(af_map.get("full_af_map", {}))
        except Exception:  # noqa: BLE001
            af_count = 0

        return f"""# 芯片肖像：{chip}

> 共享知识库芯片肖像区（知识库融合，）
> 来源：Agent-S 模板锻造线细化产物，归入图书馆共享。

## 这是什么

{meta.get('chip', chip)} 的完整芯片画像——**精确到每一个引脚**：
  - pin_map.json：{pin_count} 引脚全功能（每引脚 AF 功能/ADC/DAC/特殊功能/注解）
  - af_map.json：{af_count} 个 AF 信号（信号 → 全部可用引脚反推表）
  - profile.json：芯片档案（内核/主频/Flash/RAM/外设清单）
  - templates/：功能模板归档（{chip} 适用的 26 个功能模板）
  - reference/：参考范本（系列级「完美模板」核验标尺）

## 怎么用（给 LLM）

1. **查引脚**：读 pin_map.json，按引脚名找功能
2. **选引脚**：读 af_map.json，按信号找可用引脚（如 SPI1_SCK → PA5/PB3）
3. **识别套式**：开发板简单逻辑模板优先（board_simple）+ 功能模板补缺（functional）
4. **拼接**：templates/ + 识别套式（assemble_routed）→ 功能模板组合成完整工程

## 数据来源

- STM32F407 数据手册 Table 6（引脚定义）+ AF 复用表
- Agent-S HAL 解析器（26 万行库 API 骨架）
- 正点原子探索者/野火指南者开发板对标

*共享库芯片肖像，Agent-S 同步，{time.strftime('%Y-%m-%d')}。*
"""


def sync_to_kb(chip: str = "apm32f407vgt6") -> dict[str, Any]:
    """便捷入口：同步芯片肖像到共享知识库。"""
    return KnowledgeSync().sync_chip(chip)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = sync_to_kb()
    print(f"同步 {len(r['files'])} 个文件，登记 {r['index_entries']} 条索引")
    for f in r["files"][:5]:
        print(" ", f)
