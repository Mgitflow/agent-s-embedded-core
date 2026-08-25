"""Makefile 生成与编译验证：按外设精确过滤 HAL 源文件生成可 make 的 Makefile，并提供 arm-none-eabi-gcc 编译检查入口。"""
import logging
import os
import shutil
import subprocess  # nosec
from pathlib import Path

from infrastructure.chip_family import ChipFamily, derive_linker_name, get_family

logger = logging.getLogger(__name__)

# 外设→HAL 源文件映射已材料化：_series/*/manifest.yaml 的 hal_peripherals（识别公共区块）。
# 由 chip_gateway.peripheral_hal_sources 统一读取（按系列），此处不再维护 F4 基准表 + replace 前缀。


def _hal_sources_for_peripherals(peripherals: list[str] | None, family_name: str) -> list[str]:
    """根据使用的外设列表生成需要编译的 HAL 源文件列表。

    2026-08-22 识别公共区块：外设→源文件从系列 manifest 的 hal_peripherals 读（材料驱动），
    不再写死 F4 基准表 + replace 前缀——G4 的 FDCAN/COMP/OPAMP、F1 无 ETH 等系列差异正确体现。
    """
    from infrastructure.chip_family import FAMILIES
    from infrastructure.chip_gateway import gateway  # 智能巡查点：外设源清单按系列材料化

    family = FAMILIES.get(family_name) or get_family(family_name)
    peri_sources = gateway.peripheral_hal_sources(gateway.series_dir(family.name))

    used: set[str] = set()
    for p in (peripherals or []):
        for src in peri_sources.get(p.upper(), []):
            used.add(src)
    # 至少包含 GPIO 基础（很多 HAL 头依赖 gpio），源文件从系列材料取（前缀正确）
    if used:
        used.update(peri_sources.get("GPIO", []))

    sources = list(family.hal_base_sources)
    sources.extend(sorted(used))
    return [f"Drivers/HAL/Src/{s}" for s in sources]


def _build_peripheral_sources(
    peripherals: list[str] | None,
    source_files: list[str] | None,
) -> str:
    """显式列出各外设源文件，避免 $(wildcard Core/Src/*.c) 把旧工程残留文件编进去。

    优先使用调用方传入的真实 source_files（如 gpio.c / uart.c）。
    """
    if source_files:
        peripheral_sources = [f"Core/Src/{src}" for src in source_files]
    else:
        peripheral_sources = [f"Core/Src/{p.lower()}.c" for p in (peripherals or []) if p.upper() != "GPIO"]
        if peripherals and "GPIO" not in [p.upper() for p in peripherals]:
            peripheral_sources.insert(0, "Core/Src/gpio.c")
    return "\n".join(f"C_SOURCES += {s}" for s in peripheral_sources)


def _build_makefile_content(
    chip: str,
    family: ChipFamily,
    hal_sources_lines: str,
    peripheral_sources_lines: str,
) -> list[str]:
    """组装 Makefile 文本内容。"""
    defines = " ".join("-D" + d for d in family.defines)
    return [
        "# Agent-S Generated Makefile",
        f"# Chip: {chip} | Family: {family.name}",
        "TARGET = firmware",
        "PREFIX = arm-none-eabi-",
        "CC = $(PREFIX)gcc",
        "CP = $(PREFIX)objcopy",
        "HEX = $(CP) -O ihex",
        "BIN = $(CP) -O binary -S",
        "SZ = $(PREFIX)size",
        "",
        "# Startup assembly",
        f"STARTUP_FILE = Core/Startup/{family.startup_pattern}",
        "",
        "# Core sources",
        f"C_SOURCES = Core/Src/main.c Core/Src/{family.it_file} Core/Src/{family.system_file}",
        "C_SOURCES += $(STARTUP_FILE)",
        "",
        "# Peripheral sources (explicit list avoids stale files from previous builds)",
        peripheral_sources_lines,
        "",
        "# HAL sources (filtered by peripherals)",
        hal_sources_lines,
        "",
        "# Include paths",
        "C_INCLUDES = -ICore/Inc",
        "C_INCLUDES += -IDrivers/HAL/Inc",
        "C_INCLUDES += -IDrivers/CMSIS/Include",
        "C_INCLUDES += -IDrivers/DEVICE/Include",
        f"C_DEFS = {defines}",
        "",
        f"CPU = -mcpu={family.cpu_flag}",
        f"FPU = {family.fpu_flag}",
        f"LDSCRIPT = {derive_linker_name(chip)}",
        "CFLAGS = $(CPU) $(FPU) -mthumb -Wall -Os -ffunction-sections -fdata-sections $(C_DEFS) $(C_INCLUDES)",
        "LDFLAGS = $(CPU) $(FPU) -mthumb -Wl,--gc-sections -specs=nosys.specs -T$(LDSCRIPT)",
        "",
        "all: $(TARGET).elf $(TARGET).hex $(TARGET).bin",
        "",
        "# 链接脚本是 elf 的依赖：改 .ld（如 RAM/CCM 大小）必须触发重链",
        "# 2026-08-17 教训：改了 RAM 192K→128K 但 Makefile 不重链 → 烧录还是旧栈顶 → HardFault",
        "$(TARGET).elf: $(C_SOURCES) $(LDSCRIPT)",
        "\t$(CC) $(CFLAGS) $(filter-out $(LDSCRIPT),$^) $(LDFLAGS) -o $@",
        "\t$(SZ) $@",
        "",
        "%.hex: %.elf",
        "\t$(HEX) $< $@",
        "",
        "%.bin: %.elf",
        "\t$(BIN) $< $@",
        "",
        "clean:",
        "ifeq ($(OS),Windows_NT)",
        "\tcmd /C del /F /Q $(TARGET).elf $(TARGET).hex $(TARGET).bin",
        "else",
        "\trm -f $(TARGET).elf $(TARGET).hex $(TARGET).bin",
        "endif",
        "",
        ".PHONY: all clean",
    ]


def generate_makefile(
    project_dir: str,
    chip: str,
    peripherals: list[str] | None = None,
    source_files: list[str] | None = None,
) -> str:
    """生成 Makefile。peripherals 用于精确过滤 HAL 源文件。"""
    family = get_family(chip)

    hal_sources = _hal_sources_for_peripherals(peripherals, family.name)
    hal_sources_lines = "\n".join(f"C_SOURCES += {s}" for s in hal_sources)
    peripheral_sources_lines = _build_peripheral_sources(peripherals, source_files)

    content = _build_makefile_content(chip, family, hal_sources_lines, peripheral_sources_lines)
    path = os.path.join(project_dir, "Makefile")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(content))
    logger.info(f"Makefile: {path}")
    return path


def _find_arm_gcc() -> str | None:
    """查找 arm-none-eabi-gcc：项目 tools/ → env 覆盖 → STM32CubeIDE 内置 → PATH。"""
    import glob as _glob
    import os
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent

    # ① 项目本地 tools/
    local_candidates = list(_glob.glob(
        str(project_root / "tools" / "**" / "arm-none-eabi-gcc.exe"),
        recursive=True
    ))
    if local_candidates:
        return local_candidates[0]

    # ② 环境变量显式指定（AGENT_S_ARM_GCC，迁移/多工具链场景）
    env_gcc = os.environ.get("AGENT_S_ARM_GCC")
    if env_gcc and Path(env_gcc).exists():
        return env_gcc

    # ③ STM32CubeIDE 内置 GCC（GNU Tools for STM32，版本号动态，glob 匹配）
    for cube_root in (Path("C:/ST"), Path("C:/Program Files/STMicroelectronics")):
        if not cube_root.exists():
            continue
        cube_candidates = list(_glob.glob(
            str(cube_root / "STM32CubeIDE*" / "STM32CubeIDE" / "plugins"
                / "com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32*"
                / "tools" / "bin" / "arm-none-eabi-gcc.exe")
        ))
        if cube_candidates:
            return cube_candidates[0]

    # ④ 系统 PATH
    return shutil.which("arm-none-eabi-gcc")


# 单次编译超时（秒）
COMPILE_TIMEOUT = 120  # 2026-08-06：60→120——负载高峰（IDE 索引/杀毒）时 make 编译可能超 60s 导致偶发失败


def _find_make() -> str | None:
    """查找 make：PATH → STM32CubeIDE 内置 → MinGW。"""
    import glob as _glob
    from pathlib import Path

    # ① PATH（make / mingw32-make）
    for name in ("make", "mingw32-make"):
        p = shutil.which(name)
        if p:
            return p

    # ② STM32CubeIDE 内置 make
    for cube_root in (Path("C:/ST"), Path("C:/Program Files/STMicroelectronics")):
        if not cube_root.exists():
            continue
        for c in _glob.glob(str(cube_root / "STM32CubeIDE*" / "STM32CubeIDE" / "plugins"
                                 / "com.st.stm32cube.ide.mcu.externaltools.make*"
                                 / "tools" / "bin" / "make.exe")):
            return c

    # ③ MinGW（常见安装位置：MSYS2 默认 C:/mingw64；已移除个人 D 盘路径，避免开源泄露）
    for root in (Path("C:/mingw64/bin"),):
        for name in ("make.exe", "mingw32-make.exe"):
            cand = root / name
            if cand.exists():
                return str(cand)

    return None


def compile_check(project_dir: str) -> str | None:
    """尝试编译，返回 None=成功 或 错误信息"""
    arm_gcc = _find_arm_gcc()
    if not arm_gcc:
        return "arm-none-eabi-gcc not found (OK if not installed)"
    make = _find_make()
    if not make:
        return "make not found (OK if not installed)"

    # 2026-08-14 芯片数据扩充：缺 HAL 驱动库（F1/G4 系列未下载 reference 库）→ skipped
    # 而非硬编失败——生成完整，编译需按系列下载对应 STM32Cube 库。
    hal_inc = Path(project_dir) / "Drivers" / "HAL" / "Inc"
    if not hal_inc.exists() or not any(hal_inc.glob("*_hal.h")):
        return "HAL driver library not found in project (对应系列 HAL 库未安装：F4→S_REFERENCE_DIR / F1→S_REFERENCE_DIR_F1 / G4→S_REFERENCE_DIR_G4)"

    env = os.environ.copy()
    arm_bin = Path(arm_gcc).resolve().parent
    env["PATH"] = f"{arm_bin}{os.pathsep}{env.get('PATH', '')}"

    try:
        r = subprocess.run([make, "-C", project_dir, "-j4"],  # nosec
                          capture_output=True, text=True, timeout=COMPILE_TIMEOUT, env=env)
        if r.returncode == 0:
            return None
        return (r.stderr or r.stdout)[:500]
    except subprocess.TimeoutExpired:
        return "Compilation timed out"
    except subprocess.SubprocessError as e:
        return f"Compilation error: {e}"
