"""外部依赖管理器：单文件记录所有外部依赖来源、路径映射与完整性验证。"""
import logging
from pathlib import Path
from typing import Any

from infrastructure.chip_gateway import gateway  # 芯片系列识别接口（三系列动态路径）
from infrastructure.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


# ========== 外部依赖源定义 ==========
# 每个条目记录: 原始来源 → 项目内路径 → 用途

# 三系列 HAL 库元数据（加系列/加外设只改这里，文件清单由 _build_external_sources 动态生成）
_HAL_FAMILIES: dict[str, dict[str, Any]] = {
    "STM32Cube_FW_F1": {
        "prefix": "stm32f1xx", "ref": "f1", "version": "1.8.5",
        "core": "core_cm3.h", "description": "STM32F1 HAL 库官方驱动",
        "device": ["stm32f103xb.h", "stm32f1xx.h", "system_stm32f1xx.h"],
        "peripherals": ["adc", "can", "cec", "cortex", "crc", "dac", "dma", "eth",
                        "exti", "flash", "gpio", "hcd", "i2c", "i2s", "irda", "iwdg",
                        "mmc", "nand", "nor", "pccard", "pcd", "pwr", "rcc", "rtc",
                        "sd", "smartcard", "spi", "sram", "tim", "uart", "usart", "wwdg"],
    },
    "STM32Cube_FW_F4": {
        "prefix": "stm32f4xx", "ref": "f4", "version": "1.28.3",
        "core": "core_cm4.h", "description": "STM32F4 HAL 库官方驱动",
        "device": ["stm32f407xx.h", "stm32f4xx.h", "system_stm32f4xx.h"],
        "peripherals": ["adc", "can", "cec", "cortex", "crc", "cryp", "dac", "dcmi",
                        "dfsdm", "dma", "dma2d", "dsi", "eth", "exti", "flash", "fmpi2c",
                        "fmpsmbus", "gpio", "hash", "hcd", "i2c", "i2s", "irda", "iwdg",
                        "lptim", "ltdc", "mmc", "nand", "nor", "pccard", "pcd", "pwr",
                        "qspi", "rcc", "rng", "rtc", "sai", "sd", "sdram", "smartcard",
                        "smbus", "spdifrx", "spi", "sram", "tim", "uart", "usart", "wwdg"],
    },
    "STM32Cube_FW_G4": {
        "prefix": "stm32g4xx", "ref": "g4", "version": "1.5.0",
        "core": "core_cm4.h", "description": "STM32G4 HAL 库官方驱动",
        "device": ["stm32g431xx.h", "stm32g4xx.h", "system_stm32g4xx.h"],
        "peripherals": ["adc", "comp", "cordic", "cortex", "crc", "cryp", "dac", "dma",
                        "exti", "fdcan", "flash", "fmac", "gpio", "hrtim", "i2c", "i2s",
                        "irda", "iwdg", "lptim", "nand", "nor", "opamp", "pcd", "pwr",
                        "qspi", "rcc", "rng", "rtc", "sai", "smartcard", "smbus", "spi",
                        "sram", "tim", "uart", "usart", "wwdg"],
    },
}


def _build_external_sources() -> dict[str, dict[str, Any]]:
    """按 _HAL_FAMILIES 动态生成三系列外部依赖（文件清单 = 基础 + 外设，前缀参数化）。

    版本号为 ST 官方发布基线，以实际 reference 库为准（此处仅作来源记录）。
    """
    sources: dict[str, dict[str, Any]] = {}
    for name, fam in _HAL_FAMILIES.items():
        prefix = fam["prefix"]
        ref = fam["ref"]
        headers = [f"{prefix}_hal.h", f"{prefix}_hal_def.h", f"{prefix}_hal_conf_template.h"]
        srcs = [f"{prefix}_hal.c"]
        for p in fam["peripherals"]:
            headers.append(f"{prefix}_hal_{p}.h")
            srcs.append(f"{prefix}_hal_{p}.c")
        sources[name] = {
            "version": fam["version"],
            "original_path": f"STM32Cube/Repository/{name}_V{fam['version']}",
            "license": "BSD-3-Clause (STMicroelectronics)",
            "description": fam["description"],
            "components": {
                "hal_headers": {
                    "original": f"Drivers/STM32{ref.upper()}xx_HAL_Driver/Inc/",
                    "internal": f"../reference-stm32{ref}/hal/Inc/",
                    "files": headers,
                },
                "hal_sources": {
                    "original": f"Drivers/STM32{ref.upper()}xx_HAL_Driver/Src/",
                    "internal": f"../reference-stm32{ref}/hal/Src/",
                    "files": srcs,
                },
                "cmsis_core": {
                    "original": "Drivers/CMSIS/Include/",
                    "internal": f"../reference-stm32{ref}/cmsis/Include/",
                    "files": [fam["core"], "cmsis_compiler.h", "cmsis_gcc.h",
                              "cmsis_version.h", "mpu_armv7.h"],
                },
                "device_headers": {
                    "original": f"Drivers/CMSIS/Device/ST/STM32{ref.upper()}xx/Include/",
                    "internal": f"../reference-stm32{ref}/device/Include/",
                    "files": fam["device"],
                },
                "mx_templates": {
                    "original": f"Projects/STM32{ref.upper()}-Discovery/Templates/",
                    "internal": f"../reference-stm32{ref}/templates/",
                    # 精简库只保留 hal_conf 模板（main.c/it.c 等由 MxSkeleton 内部生成，不依赖 reference Src）
                    "files": {
                        f"Inc/{prefix}_hal_conf.h": f"Inc/{prefix}_hal_conf.h",
                    },
                },
            },
        }
    return sources


EXTERNAL_SOURCES: dict[str, dict[str, Any]] = _build_external_sources()

# 项目内已有（非外部搬迁，而是项目自建的知识资产）
# 开源骨架只夹带 mx_skeleton 模板引擎这一项自建资产；其余知识资产（芯片肖像、
# 功能模板、手册数据、电气数据）属护城河，不随骨架开源。
INTERNAL_ASSETS = {
    "mx_skeleton": {
        "path": "knowledge/loaders/mx_skeleton.py",
        "description": "MX 模板引擎（基于官方 MX 模板构建）",
    },
}


class ExternalDependencyManager:
    """外部依赖管理器"""

    def __init__(self) -> None:
        self._issues: list[str] = []
        self._stats: dict[str, int] = {"total": 0, "present": 0, "missing": 0}

    def validate(self) -> bool:
        """验证所有外部依赖文件是否在项目内就位"""
        self._issues = []
        self._stats = {"total": 0, "present": 0, "missing": 0}

        for source_name, source_info in EXTERNAL_SOURCES.items():
            for comp_name, comp_info in source_info["components"].items():
                internal_dir = Path(PROJECT_ROOT) / comp_info["internal"]

                if isinstance(comp_info["files"], dict):
                    # 文件映射模式
                    for rel_path in comp_info["files"].values():
                        self._stats["total"] += 1
                        full_path = internal_dir / rel_path
                        if full_path.exists():
                            self._stats["present"] += 1
                        else:
                            self._stats["missing"] += 1
                            self._issues.append(
                                f"[缺失] {source_name}/{comp_name}: {rel_path}"
                            )
                else:
                    # 文件列表模式
                    for fname in comp_info["files"]:
                        self._stats["total"] += 1
                        full_path = internal_dir / fname
                        if full_path.exists():
                            self._stats["present"] += 1
                        else:
                            self._stats["missing"] += 1
                            self._issues.append(
                                f"[缺失] {source_name}/{comp_name}: {fname}"
                            )

        if self._issues:
            logger.warning(f"ExternalDependencyManager: {len(self._issues)} 个文件缺失")
        else:
            logger.info("ExternalDependencyManager: 所有外部依赖文件已就位")

        return len(self._issues) == 0

    def validate_internal_assets(self) -> bool:
        """验证项目内部知识资产是否存在"""
        all_ok = True
        for name, info in INTERNAL_ASSETS.items():
            path = info["path"]
            full_path = Path(PROJECT_ROOT) / path
            if not full_path.exists():
                self._issues.append(f"[缺失] 内部资产 {name}: {path}")
                all_ok = False
        return all_ok

    def report(self) -> str:
        """生成依赖报告"""
        lines = []
        lines.append("=" * 60)
        lines.append("外部依赖报告 (External Dependencies Report)")
        lines.append("=" * 60)

        # 验证统计
        self.validate()
        lines.append(f"\n文件统计: {self._stats['total']} 个文件")
        lines.append(f"  就位: {self._stats['present']}")
        lines.append(f"  缺失: {self._stats['missing']}")

        # 外部来源
        lines.append("\n--- 外部依赖源 ---")
        for source_name, source_info in EXTERNAL_SOURCES.items():
            lines.append(f"\n{source_name} v{source_info['version']}")
            lines.append(f"  许可证: {source_info['license']}")
            lines.append(f"  说明: {source_info['description']}")
            for comp_name, comp_info in source_info["components"].items():
                if isinstance(comp_info["files"], dict):
                    count = len(comp_info["files"])
                else:
                    count = len(comp_info["files"])
                lines.append(f"  {comp_name}: {count} 文件 → {comp_info['internal']}")

        # 内部资产
        lines.append("\n--- 项目内部知识资产 ---")
        for name, info in INTERNAL_ASSETS.items():
            lines.append(f"  {name}: {info['path']}")
            lines.append(f"    说明: {info['description']}")

        # 问题
        if self._issues:
            lines.append("\n--- 问题列表 ---")
            for issue in self._issues:
                lines.append(f"  {issue}")
        else:
            lines.append("\n--- 状态: 全部就位 ---")

        lines.append("=" * 60)
        return "\n".join(lines)

    def get_include_paths(self, series: str = "F4") -> list[str]:
        """获取编译所需的 include 路径（按芯片系列，默认 F4）。"""
        ref = gateway.reference_dir(series)
        return [
            str(ref / "hal" / "Inc"),
            str(ref / "cmsis" / "Include"),
            str(ref / "device" / "Include"),
        ]

    def get_source_paths(self, series: str = "F4") -> list[str]:
        """获取编译所需的源文件路径（按芯片系列，默认 F4）。"""
        return [str(gateway.reference_dir(series) / "hal" / "Src")]

    def get_template_path(self, series: str = "F4") -> str:
        """获取 MX 模板路径（按芯片系列，默认 F4）。"""
        return str(gateway.reference_dir(series) / "templates")


# ========== 便捷函数 ==========

def validate_all() -> bool:
    """快速验证所有依赖"""
    edm = ExternalDependencyManager()
    return edm.validate() and edm.validate_internal_assets()


def print_report() -> None:
    """打印依赖报告"""
    edm = ExternalDependencyManager()
    print(edm.report())


# ========== 自检 ==========
if __name__ == "__main__":
    print_report()
