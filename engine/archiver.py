"""产物归档调度层：把「一次生成+一次编译」收敛为 source/build/firmware 分级的归档单元，只由本模块写入 output/archive/。"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 归档根：WORKSPACE_ROOT/archive（念安 8-21「编译产物放项目外」——
# WORKSPACE_ROOT 默认项目外 <parent>/agent-s-output/，AGENT_S_WORKSPACE 可覆盖）。
# 修复：此前硬编码 output/archive，注释声称支持 AGENT_S_WORKSPACE 但代码没实现（孤岛）。
from infrastructure.config import WORKSPACE_ROOT as _WORKSPACE_ROOT  # noqa: E402

_ARCHIVE_ROOT = Path(_WORKSPACE_ROOT) / "archive"

# 源码扩展名（HAL 库 Drivers/ 不进归档——驱动按版本引用，避免每工程复制 12MB）
_SOURCE_EXTS = {".c", ".h", ".ld", ".txt", ".md", ".s", ".S"}
_BUILD_EXTS = {".elf", ".hex", ".bin", ".map", ".lst"}
# 单一烧录文件优先序：hex（烧录标准）→ bin（裸固件）→ elf（含调试符号）
_FIRMWARE_ORDER = (".hex", ".bin", ".elf")

# 归档保留上限：按修改时间保留最近 N 个归档单元，超出自动裁剪（防 output/ 无限膨胀）。
# 2026-08-17 念安拍板：归档必须带保留策略，不能只进不出（此前 1.2GB 失控）。
MAX_ARCHIVE_UNITS = 100


def archive_project(
    project_dir: str | Path,
    *,
    compiled_ok: bool = False,
    meta: dict[str, Any] | None = None,
    archive_root: str | Path | None = None,
    branch: str = "auto",
) -> dict[str, Any]:
    """归档一次生成/编译产物，返回归档结果（不抛异常，失败安全）。

    Args:
        project_dir: 生成器产出的工程目录（output/work 下的中间产物）。
        compiled_ok: 编译是否通过（决定 verified / draft 分级）。
        meta: 附加元数据（chip/peripherals/version 等，缺省时尝试解析 project_info.md）。
        archive_root: 归档根（默认 output/archive；测试可注入临时目录）。
        branch: 产出分支（a=老版LLM/b=模板直出/c=LLM自主/auto=默认），归档按分支分子目录。

    Returns:
        dict: {archived, project_id, path, compiled, error?, ...} 失败时 archived=False。
    """
    result: dict[str, Any] = {"archived": False}
    try:
        proj = Path(project_dir)
        if not proj.is_dir():
            result["error"] = f"工程目录不存在: {proj}"
            return result

        root = Path(archive_root) if archive_root else _ARCHIVE_ROOT
        name = proj.name.strip("_-") or "stm32_project"
        # 2026-08-17 产出分支分类：按 a/b/c 分支分子目录，默认 auto
        branch = (branch or "auto").strip() or "auto"
        # 时间戳含微秒：同一秒多次归档也不冲突
        project_id = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        unit = root / branch / project_id

        # ① 分级收集
        sources = _collect_source_files(proj)
        builds = _collect_build_artifacts(proj)
        firmware = _pick_firmware(builds)
        info = _build_project_info(proj, project_id, compiled_ok, meta, sources, builds, firmware)
        info["branch"] = branch

        # ② 写入归档单元（source/ + build/ + firmware + info）
        (unit / "source").mkdir(parents=True, exist_ok=True)
        (unit / "build").mkdir(parents=True, exist_ok=True)
        for src in sources:
            _copy_relative(proj, src, unit / "source")
        for art in builds:
            # 编译产物平铺到 build/（elf/hex/bin/map 文件名唯一，保留相对路径会嵌套）
            shutil.copy2(art, unit / "build" / art.name)
        if firmware is not None:
            shutil.copy2(firmware, unit / firmware.name)
        (unit / "project_info.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ③ 原形分层存放（2026-08-16 念安拍板：不打包 zip——原形直接烧录/查看，避免解压；
        #    HAL 库 Drivers/ 已在上游排除，不进归档，故散文件原形本身不大）

        # ④ 更新索引
        _update_index(root, info)
        result.update(
            archived=True, project_id=project_id, path=str(unit),
            compiled=compiled_ok, info=info,
        )
        logger.info("已归档 %s → %s (%s)", name, unit, "verified" if compiled_ok else "draft")
        # ⑤ 保留策略：默认根（生产路径）归档后自动裁剪，防无限膨胀；测试注入根不裁剪
        if archive_root is None:
            pruned = prune_archive(max_units=MAX_ARCHIVE_UNITS, archive_root=root)
            if pruned.get("removed"):
                logger.info("归档裁剪：移除 %d 个旧单元，释放 %.1f MB",
                            pruned["removed"], pruned.get("freed_bytes", 0) / 1_048_576)
    except Exception as e:  # noqa: BLE001 - 归档失败安全：不阻断调用方
        result["error"] = f"{type(e).__name__}: {e}"
        logger.warning("归档失败: %s", result["error"])
    return result


def _collect_source_files(project_dir: Path) -> list[Path]:
    """收集源码文件，排除 Drivers/（HAL 库按版本引用，不复制副本）。

    无后缀文件（Makefile/CMakeLists.txt）按文件名识别。
    """
    out: list[Path] = []
    for p in project_dir.rglob("*"):
        if not p.is_file() or "Drivers" in p.parts:
            continue
        if p.suffix in _SOURCE_EXTS or p.name in ("Makefile", "CMakeLists.txt"):
            out.append(p)
    return sorted(out)


def _collect_build_artifacts(project_dir: Path) -> list[Path]:
    """收集编译产物（elf/hex/bin/map/lst）。"""
    out: list[Path] = []
    for p in project_dir.rglob("*"):
        if p.is_file() and p.suffix in _BUILD_EXTS:
            out.append(p)
    return sorted(out)


def _pick_firmware(builds: list[Path]) -> Path | None:
    """单一烧录文件：hex → bin → elf 优先序（全部存在时取最优先）。"""
    for ext in _FIRMWARE_ORDER:
        for p in builds:
            if p.suffix == ext:
                return p
    return None


def _copy_relative(root: Path, src: Path, dest_dir: Path) -> None:
    """保持相对目录结构复制（如 Core/Src/main.c → source/Core/Src/main.c）。"""
    rel = src.relative_to(root)
    target = dest_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)


def _build_project_info(
    proj: Path, project_id: str, compiled_ok: bool, meta: dict[str, Any] | None,
    sources: list[Path], builds: list[Path], firmware: Path | None,
) -> dict[str, Any]:
    """结构化元数据：优先调用方 meta，缺省解析 project_info.md（旧工程兼容）。"""
    info: dict[str, Any] = {
        "project_id": project_id,
        "project_name": proj.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "compiled": compiled_ok,
        "grade": "verified" if compiled_ok else "draft",
        "source_files": len(sources),
        "build_files": len(builds),
        "artifact": firmware.name if firmware else None,
    }
    if meta:
        info.update(meta)
    else:
        md = proj / "project_info.md"
        if md.exists():
            text = md.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("- **芯片**"):
                    info["chip"] = line.split("**", 2)[-1].lstrip(": ").strip()
                elif line.startswith("- **主频**"):
                    info["clock_mhz"] = line.split("**", 2)[-1].lstrip(": ").strip()
                elif line.startswith("- **生成工具**"):
                    info["generator_version"] = line.split("**", 2)[-1].lstrip(": ").strip()
    info.setdefault("chip", "unknown")
    return info


def _update_index(root: Path, info: dict[str, Any]) -> None:
    """追加/更新归档索引（index.json，保持全部单元可查询）。"""
    index_path = root / "index.json"
    entries: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                entries = data["entries"]
        except (OSError, ValueError):
            entries = []
    entries.append(info)
    index_path.write_text(
        json.dumps({"count": len(entries), "entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_index(archive_root: str | Path | None = None) -> list[dict[str, Any]]:
    """读取归档索引（全部归档单元摘要）。"""
    root = Path(archive_root) if archive_root else _ARCHIVE_ROOT
    index_path = root / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return data.get("entries", []) if isinstance(data, dict) else []
    except (OSError, ValueError):
        return []


def query_index(
    *,
    compiled: bool | None = None,
    chip: str | None = None,
    name: str | None = None,
    archive_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """按条件查询归档索引（compiled/chip/名称模糊匹配）。"""
    entries = load_index(archive_root)
    out = []
    for e in entries:
        if compiled is not None and e.get("compiled") is not compiled:
            continue
        if chip and str(e.get("chip", "")).lower() != chip.lower():
            continue
        if name and name.lower() not in str(e.get("project_name", "")).lower():
            continue
        out.append(e)
    return out


def prune_archive(*, max_units: int = MAX_ARCHIVE_UNITS, archive_root: str | Path | None = None) -> dict[str, Any]:
    """裁剪归档：按修改时间保留最近 max_units 个归档单元，删除更旧的（防无限膨胀）。

    2026-08-17 分支结构适配：归档单元在 root/{branch}/{project_id}/（branch=a/b/c/auto），
    同时兼容旧的 root/{project_id}/ 平铺单元；跳过 source/ 与 index.json，失败安全。
    """
    root = Path(archive_root) if archive_root else _ARCHIVE_ROOT
    result: dict[str, Any] = {"removed": 0, "freed_bytes": 0, "kept": 0}
    if not root.is_dir():
        return result
    try:
        units: list[Path] = []
        for d in root.iterdir():
            if not d.is_dir() or d.name == "source":
                continue
            if d.name in ("a", "b", "c", "auto"):
                units.extend(x for x in d.iterdir() if x.is_dir())
            else:
                units.append(d)  # 旧平铺单元
        units.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        for d in units[max_units:]:
            try:
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                shutil.rmtree(d, ignore_errors=True)
                result["removed"] += 1
                result["freed_bytes"] += size
            except OSError as exc:  # noqa: BLE001 - 单个单元删除失败不影响整体
                logger.warning("归档裁剪跳过 %s: %s", d.name, exc)
        result["kept"] = min(len(units), max_units)
    except Exception as exc:  # noqa: BLE001 - 裁剪失败安全
        logger.warning("归档裁剪失败: %s", exc)
    return result


__all__ = ["archive_project", "load_index", "query_index", "prune_archive"]
