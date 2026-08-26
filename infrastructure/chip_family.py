"""芯片族元数据注册表：按 manifest 的 family/series/core 推导启动文件、链接脚本、openocd target 与 HAL defines。"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from infrastructure.chip_gateway import gateway as _chip_gateway  # 智能巡查点：系列目录/判定唯一事实源
from infrastructure.config import CHIPS_DIR


@dataclass(frozen=True)
class ChipFamily:
    """芯片族编译/烧录元数据。"""

    name: str
    core: str
    cpu_flag: str
    fpu_flag: str
    defines: list[str]
    startup_pattern: str
    system_file: str
    it_file: str
    linker_pattern: str
    openocd_target: str
    hal_base_sources: list[str]
    hal_family_dir: str
    default_chip: str = ""
    gpio_alternate: bool = True  # F1 的 GPIO_InitTypeDef 无 Alternate 字段（AF 复用隐式），F4/G4 有
    memory_bases: dict[str, str] = field(default_factory=dict)  # 内存基址（flash/ram/peripheral/ccm，材料声明）
    adc_resolution_macro: str = "ADC_RESOLUTION_12B"  # ADC 分辨率宏名：F1=ADC_RESOLUTION12b，F4/G4=ADC_RESOLUTION_12B


# 拔插式：_series 目录从 config.CHIPS_DIR 派生（AGENT_S_CHIPS_DIR 可替换）
_SERIES_DIR = Path(CHIPS_DIR) / "_series"


def _load_family_from_disk(key: str) -> ChipFamily | None:
    """尝试从 ``skills/chips/_series/<key>/family.json`` 加载族元数据。

    系列目录由智能巡查点 chip_gateway 统一索引（新增系列只改 gateway 一处）。
    """
    dir_name = _chip_gateway.series_dir(key)
    path = _SERIES_DIR / dir_name / "family.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ChipFamily(**data)
    except (OSError, json.JSONDecodeError, TypeError):
        # 加载失败时返回 None，后续回退到内置数据
        return None


# 完全从 _series/*/family.json 加载（材料驱动，无硬编码兜底）。
# 系列键由智能巡查点 chip_gateway 的 adapter 注册表提供（P1 材料化后改扫 _series 自动发现）。
# family.json 缺失/损坏的系列不进入 FAMILIES，get_family 对其回退默认 F4（fail-closed 见 resolve）。
FAMILIES: dict[str, ChipFamily] = {}
for _key in _chip_gateway.list_adapters():
    _fam = _load_family_from_disk(_key)
    if _fam is not None:
        FAMILIES[_key] = _fam

# 空车降级：无 _series/family.json 时注入内置 F4 默认（与 chip_gateway._fallback_adapter 对称），
# 使 get_family 的 fail-closed 回退不再 KeyError，空车可加载示意芯片。
if not FAMILIES:
    FAMILIES["STM32F4xx"] = ChipFamily(
        name="STM32F4xx",
        core="Cortex-M4",
        cpu_flag="cortex-m4",
        fpu_flag="-mfpu=fpv4-sp-d16 -mfloat-abi=hard",
        defines=["STM32F407xx", "USE_HAL_DRIVER"],
        startup_pattern="startup_stm32f407xx.s",
        system_file="system_stm32f4xx.c",
        it_file="stm32f4xx_it.c",
        linker_pattern="STM32F407ZGTx_FLASH.ld",
        openocd_target="stm32f4x.cfg",
        hal_base_sources=[
            "stm32f4xx_hal.c",
            "stm32f4xx_hal_cortex.c",
            "stm32f4xx_hal_rcc.c",
            "stm32f4xx_hal_pwr.c",
            "stm32f4xx_hal_pwr_ex.c",
        ],
        hal_family_dir="STM32F4xx_HAL_Driver",
        default_chip="stm32f407zgt6",
        gpio_alternate=True,
        memory_bases={
            "flash_base": "0x08000000",
            "ram_base": "0x20000000",
            "peripheral_base": "0x40000000",
            "ccm_base": "0x10000000",
        },
    )


def derive_linker_name(chip_name: str) -> str:
    """根据芯片型号推导 GCC 链接脚本文件名。

    例：STM32F407ZGT6 -> STM32F407ZGTx_FLASH.ld
        STM32F103C8T6 -> STM32F103C8Tx_FLASH.ld
        APM32F407VGT6 -> STM32F407VGTx_FLASH.ld
    """
    name = chip_name.upper().replace("APM32", "STM32")
    # STM32F{series}{pkg}{flash}{pins}{temp} -> STM32F{series}{pkg}{flash}{pins}x_FLASH.ld
    # flash 可能是字母（F4/F7）或数字（F1），因此用 [A-Z0-9] 匹配
    m = re.match(r"STM32F(\d+)([A-Z])([A-Z0-9])([A-Z])\d+", name)
    if m:
        series = m.group(1)
        pkg = m.group(2)
        flash = m.group(3)
        pins = m.group(4)
        return f"STM32F{series}{pkg}{flash}{pins}x_FLASH.ld"
    return f"{name}_FLASH.ld"


def family_from_chip_name(chip_name: str) -> str:
    """从芯片型号字符串推断 family 键。

    智能巡查点：判定逻辑统一收拢到 chip_gateway
    （适配器扫 _series/*/family.json 的 defines 自动注册，新增系列只放材料）。
    """
    return _chip_gateway.family_key_for_chip(chip_name)


def get_family(chip_name: str) -> ChipFamily:
    """获取芯片族的元数据，未知型号回退到 STM32F4xx。"""
    key = family_from_chip_name(chip_name)
    return FAMILIES.get(key, FAMILIES["STM32F4xx"])
