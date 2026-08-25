"""一条龙：文字 → 生成 → 编译 → 烧录（可选，需工具链）。

最小可运行示例的「完整链路」版本——和 ``examples/run_example.py``（只演示生成）
互补：这个把生成出的工程真正编译成固件、烧到板子上。

用法：
    python scripts/build_flash.py                      # 默认「点灯」，编译 + 烧录
    python scripts/build_flash.py "点灯"               # 指定文字
    python scripts/build_flash.py "点灯" --no-flash    # 只编译，不烧录
    python scripts/build_flash.py "点灯" --compile-only # 只生成 + 编译（不烧录）

工具链（自动探测 + 环境变量覆盖，不写死路径）：
    AGENT_S_ARM_GCC      arm-none-eabi-gcc 路径（makefile_generator 已支持）
    STM32_CUBE_FW        STM32Cube HAL 库根目录（编译必需）
    STM32_PROGRAMMER_CLI STM32_Programmer_CLI.exe 路径（烧录必需）

没板子/没工具链也能跑「生成」这一步；编译/烧录缺工具链时明确提示缺什么、跳过什么，
不静默失败——这就是「空车能开」和「有工具链能跑通」的分界。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.makefile_generator import _find_arm_gcc, _find_make  # noqa: E402

DEFAULT_TEXT = "点灯"
DEFAULT_CHIP = "stm32f407zgt6"
OUT_DIR = ROOT / "output" / "build_flash_demo"


# ── 工具链探测（环境变量优先，其次自动探测，找不到返回 None）────────────────
def _find_cube_fw() -> str | None:
    """STM32Cube HAL 库根目录：env → C:/Users/*/STM32Cube/Repository/STM32Cube_FW_F4_*。"""
    env = os.environ.get("STM32_CUBE_FW")
    if env and Path(env).exists():
        return Path(env).as_posix()
    users = Path("C:/Users")
    if users.exists():
        for user in users.iterdir():
            repo = user / "STM32Cube" / "Repository"
            if repo.exists():
                # 只取「解压后的目录」，排除 .zip（Repository 里常同时有 zip 和目录，
                # Windows glob 大小写不敏感会把 zip 也匹配进来）。
                cands = sorted(p for p in repo.glob("STM32Cube_FW_F4_*") if p.is_dir())
                if cands:
                    # 必须正斜杠：Makefile 里 $(STM32_CUBE_FW)/Drivers/... 拼接，
                    # 反斜杠会被 make 当转义符吞掉导致 include 路径断裂。
                    return cands[-1].as_posix()
    return None


def _find_programmer() -> str | None:
    """STM32_Programmer_CLI：env → C:/ST 下 CubeIDE 插件内。"""
    env = os.environ.get("STM32_PROGRAMMER_CLI")
    if env and Path(env).exists():
        return env
    for cube_root in (Path("C:/ST"), Path("C:/Program Files/STMicroelectronics")):
        if not cube_root.exists():
            continue
        cands = list(cube_root.glob(
            "STM32CubeIDE*/STM32CubeIDE/plugins/"
            "com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer*/"
            "tools/bin/STM32_Programmer_CLI.exe"
        ))
        if cands:
            return str(cands[0])
    return None


# ── 四步 ────────────────────────────────────────────────
def generate(text: str, chip: str, out_dir: Path) -> tuple[bool, str]:
    """assemble_routed 生成完整工程写盘。"""
    from knowledge.template_forge.functional_assembler import FunctionalAssembler

    r = FunctionalAssembler().assemble_routed(text, chip=chip)
    if not r or not r.get("files"):
        return False, f"未识别到模板: {text!r}（missing={r.get('missing') if r else '?'}）"
    for rel, content in r["files"].items():
        parts = rel.split("/")
        target = out_dir / Path(*parts[1:]) if len(parts) > 1 else out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return True, f"生成 {len(r['files'])} 文件 → {out_dir}（模板: {','.join(r.get('templates', [])) or '-'}）"


def compile_proj(out_dir: Path) -> tuple[bool, str]:
    """arm-none-eabi-gcc 编译，返回 (成功, 日志)。"""
    make = _find_make()
    gcc = _find_arm_gcc()
    fw = _find_cube_fw()
    if not gcc:
        return False, "缺 arm-none-eabi-gcc（设 AGENT_S_ARM_GCC 或装 STM32CubeIDE 工具链）"
    if not make:
        return False, "缺 make（装 mingw32-make 或 STM32CubeIDE）"
    if not fw:
        return False, "缺 STM32Cube HAL 库（设 STM32_CUBE_FW 指向 STM32Cube_FW_F4_*）"

    arm_bin = Path(gcc).resolve().parent
    env = os.environ.copy()
    env["PATH"] = f"{arm_bin}{os.pathsep}{env['PATH']}"
    env["STM32_CUBE_FW"] = fw
    r = subprocess.run(
        [make, "-C", str(out_dir), "-j4"], capture_output=True, text=True, env=env, timeout=180
    )
    hex_path = out_dir / "firmware.hex"
    log = (r.stdout or "")[-1200:] + (r.stderr or "")[-1200:]
    return r.returncode == 0 and hex_path.exists(), log


def flash(hex_path: Path) -> tuple[bool, str]:
    """SWD 烧录 + 校验 + 复位（Normal 模式；HOTPLUG 会擦除失败）。"""
    cli = _find_programmer()
    if not cli:
        return False, "缺 STM32_Programmer_CLI（设 STM32_PROGRAMMER_CLI 指向 CLI.exe）"
    r = subprocess.run(
        [cli, "-c", "port=SWD", "-w", str(hex_path), "-v", "-rst"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    out = (r.stdout or "") + (r.stderr or "")
    return "Download verified successfully" in out, out[-600:]


def main() -> int:
    ap = argparse.ArgumentParser(description="文字 → 生成 → 编译 → 烧录 一条龙")
    ap.add_argument("text", nargs="?", default=DEFAULT_TEXT, help="自然语言需求（默认「点灯」）")
    ap.add_argument("--chip", default=DEFAULT_CHIP, help="芯片名（默认 stm32f407zgt6）")
    ap.add_argument("--no-flash", action="store_true", help="只编译，不烧录")
    ap.add_argument("--compile-only", action="store_true", help="只生成 + 编译，不烧录")
    args = ap.parse_args()

    print("=" * 62)
    print(f"需求: {args.text}    芯片: {args.chip}")
    print("=" * 62)

    # ① 生成
    ok, msg = generate(args.text, args.chip, OUT_DIR)
    print(f"[1/3 生成] {'✅' if ok else '❌'} {msg}")
    if not ok:
        return 1

    # ② 编译
    ok, log = compile_proj(OUT_DIR)
    print(f"[2/3 编译] {'✅' if ok else '❌'}")
    if not ok:
        print("  " + log.strip()[-800:])
        return 1
    print("  firmware.hex 已生成")

    # ③ 烧录
    if args.no_flash or args.compile_only:
        print("[3/3 烧录] ⏭ 跳过（--no-flash / --compile-only）")
        return 0
    ok, log = flash(OUT_DIR / "firmware.hex")
    print(f"[3/3 烧录] {'✅' if ok else '❌'}")
    if not ok:
        print("  " + log.strip()[-400:])
        return 1

    print("=" * 62)
    print("全链路跑通：文字 → 生成 → 编译 → 烧录。去看板子吧。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
