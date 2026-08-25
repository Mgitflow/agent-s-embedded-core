"""把 gen_pin_data_from_cubemx 生成的数据落盘到 build_pin_map.py / build_pin_map_zgt6.py。

用法：python knowledge/loaders/apply_cubemx_pin_data.py
- 生成 A-E 端口新 PIN_DATA，替换 build_pin_map.py 里 PIN_DATA 的 A-E 部分（保留非 GPIO/PH0/PH1）
- 生成 F/G 端口新 PF_DATA/PG_DATA，替换 build_pin_map_zgt6.py 里的 PF_DATA/PG_DATA
- 替换后做语法检查（py_compile）
"""
from __future__ import annotations

import py_compile
import sys
from pathlib import Path

# 定位项目根（本文件在 knowledge/loaders/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_pin_data_from_cubemx import build_pin_map, parse_cubemx, render_pin_data  # noqa: E402


def apply_pin_map_py() -> None:
    cubemx = parse_cubemx()
    pin_map = build_pin_map(cubemx)

    # ── 1. build_pin_map.py：替换 PIN_DATA 的 A-E 端口部分 ──
    bp = PROJECT_ROOT / "knowledge/loaders/build_pin_map.py"
    txt = bp.read_text(encoding="utf-8")
    start = txt.index('    # ═══ GPIO A ═══')
    end = txt.index('    # ═══ 非 GPIO 引脚')
    ae_src = render_pin_data(pin_map, "ABCDE")
    new_txt = txt[:start] + ae_src + txt[end:]
    bp.write_text(new_txt, encoding="utf-8")
    print("build_pin_map.py PIN_DATA A-E 端口已替换")

    # ── 2. build_pin_map_zgt6.py：替换 PF_DATA / PG_DATA ──
    bz = PROJECT_ROOT / "knowledge/loaders/build_pin_map_zgt6.py"
    txt2 = bz.read_text(encoding="utf-8")
    # PF_DATA 范围：PF_DATA 定义 到 PG_DATA 定义之前
    pf_start = txt2.index('PF_DATA: dict[str, dict[str, Any]] = {')
    pg_start = txt2.index('# G 端口')
    pf_src = render_pin_data(pin_map, "F")
    # PG_DATA 范围：PG_DATA 定义 到 PH 端口注释之前
    pg_def = txt2.index('PG_DATA: dict[str, dict[str, Any]] = {')
    ph_start = txt2.index('# PH 端口')
    pg_src = render_pin_data(pin_map, "G")
    new_txt2 = (
        txt2[:pf_start]
        + "PF_DATA: dict[str, dict[str, Any]] = {\n"
        + pf_src
        + "}\n\n"
        + txt2[pg_start:pg_def]
        + "PG_DATA: dict[str, dict[str, Any]] = {\n"
        + pg_src
        + "}\n\n"
        + txt2[ph_start:]
    )
    bz.write_text(new_txt2, encoding="utf-8")
    print("build_pin_map_zgt6.py PF_DATA/PG_DATA 已替换")

    # ── 3. 语法检查 ──
    py_compile.compile(str(bp), doraise=True)
    py_compile.compile(str(bz), doraise=True)
    print("语法检查通过")


if __name__ == "__main__":
    apply_pin_map_py()
