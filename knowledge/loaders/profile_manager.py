"""芯片画像管理器：扫描 skills/chips/* 读取 profile.json/af_map/standards 构建 IChipProfile，可按 FCNT→base 优先级 enrich 画像。"""
import json
import logging
from pathlib import Path
from typing import Any, cast

from contracts.exceptions import KnowledgeIOError
from contracts.interfaces import IChipProfile, IProfileManager
from contracts.peripheral_registry import PERIPHERAL_STANDARDS
from infrastructure.config import DEFAULT_CHIP_NAME

logger = logging.getLogger(__name__)


class ChipProfile(IChipProfile):
    """芯片画像：封装芯片所有能力、约束和骨架"""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def chip_name(self) -> str:
        return cast(str, self._data.get("chip_name", self._data.get("chip", "Unknown")))

    @property
    def family(self) -> str:
        tmp = self._data.get("family", "")
        return tmp if isinstance(tmp, str) else ""

    @property
    def core(self) -> str:
        tmp = self._data.get("core", "")
        return tmp if isinstance(tmp, str) else ""

    @property
    def max_clock_mhz(self) -> int:
        return cast(int, self._data.get("max_clock_mhz", self._data.get("clock", 72)))

    @property
    def flash_kb(self) -> int:
        return cast(int, self._data.get("flash_kb", self._data.get("flash", 64)))

    @property
    def ram_kb(self) -> int:
        return cast(int, self._data.get("ram_kb", self._data.get("ram", 20)))

    @property
    def ccm_kb(self) -> int:
        """CCM（紧耦合内存）大小，单位 KB。F407 为 64，F103/F446 无 CCM 为 0。"""
        return cast(int, self._data.get("ccm_kb", self._data.get("ccm", 0)))

    @property
    def has_fpu(self) -> bool:
        tmp = self._data.get("has_fpu", False)
        return tmp if isinstance(tmp, bool) else False

    @property
    def capabilities(self) -> dict[str, Any]:
        tmp = self._data.get("capabilities", {})
        return tmp if isinstance(tmp, dict) else {}

    @property
    def pin_map(self) -> dict[str, Any]:
        tmp = self._data.get("pin_map", {})
        return tmp if isinstance(tmp, dict) else {}

    @property
    def clock_bus(self) -> dict[str, Any]:
        tmp = self._data.get("clock_bus", {})
        return tmp if isinstance(tmp, dict) else {}

    @property
    def constraints(self) -> dict[str, Any]:
        import copy

        c = copy.deepcopy(self._data.get("constraints", {}))
        if not c.get("clock_requirements"):
            c["clock_requirements"] = copy.deepcopy(self._data.get("clock_requirements", {}))
        if not c.get("init_order"):
            c["init_order"] = list(self._data.get("init_order", []))
        tmp = c
        return tmp if isinstance(tmp, dict) else {}

    @property
    def af_map(self) -> dict[str, Any]:
        # 向后兼容：af_map 现在统一表示“外设实例 -> AF 编号”
        tmp = self._data.get("af_numbers", {})
        return tmp if isinstance(tmp, dict) else {}

    @property
    def af_numbers(self) -> dict[str, Any]:
        tmp = self._data.get("af_numbers", {})
        return tmp if isinstance(tmp, dict) else {}

    @property
    def signal_af_map(self) -> dict[str, Any]:
        """信号名 -> 默认引脚（如 ADC1_IN0 -> PA0）。"""
        tmp = self._data.get("signal_af_map", {})
        return tmp if isinstance(tmp, dict) else {}

    @property
    def skeleton(self) -> dict[str, Any]:
        tmp = self._data.get("skeleton", {})
        return tmp if isinstance(tmp, dict) else {}

    @property
    def debug(self) -> dict[str, Any]:
        tmp = self._data.get("debug", {})
        return tmp if isinstance(tmp, dict) else {}

    @property
    def error_led_pin(self) -> str:
        """错误指示灯引脚，用于 Error_Handler LED 闪烁提示。"""
        tmp = self.debug.get("error_led_pin", "PA5")
        return tmp if isinstance(tmp, str) else "PA5"

    @property
    def clock_tree(self) -> dict[str, Any]:
        """具体芯片时钟树（profile.json 的 clock_tree）。

        供空壳骨架（MxSkeleton）生成 SystemClock_Config 时按具体芯片取时钟配置。
        字段按系列不同：F4/G4 用 pll_m/n/p/q，F1 用 pll_mult（倍频）。
        """
        tmp = self._data.get("clock_tree", {})
        return tmp if isinstance(tmp, dict) else {}

    @property
    def dma(self) -> dict[str, Any]:
        tmp = self._data.get("dma", {})
        return tmp if isinstance(tmp, dict) else {}

    def get_dma_controllers(self) -> dict[str, Any]:
        tmp = self.dma.get("controllers", {})
        return tmp if isinstance(tmp, dict) else {}

    def get_dma_stream_map(self, controller: str = "DMA2") -> dict[str, Any]:
        """获取 DMA 控制器的 Stream→Channel→Peripheral 映射表"""
        return cast(dict[str, Any], self.dma.get("controllers", {}).get(controller, {}).get("stream_map", {}))

    def get_dma_irq_vector(self, stream_key: str) -> str:
        """获取 DMA Stream 对应的中断向量名"""
        return cast(str, self.dma.get("interrupt_vectors", {}).get(stream_key, ""))

    def get_init_order(self) -> list[str]:
        tmp = self.constraints.get("init_order", ["HAL_Init", "SystemClock_Config"])
        return tmp if isinstance(tmp, list) else ["HAL_Init", "SystemClock_Config"]

    def get_peripheral_clock_bus(self, peripheral: str) -> str:
        return cast(str, self.constraints.get("clock_requirements", {}).get(peripheral, "AHB1"))

    def get_af_pin(self, signal: str) -> str | None:
        return self.signal_af_map.get(signal)

    def get_af_number(self, instance: str) -> int | None:
        """获取外设实例对应的 Alternate Function 编号（如 USART1 → 7）。"""
        return self.af_numbers.get(instance)

    def get_af_default_pins(self, instance: str) -> dict[str, str]:
        """获取外设实例的默认引脚映射（如 USART1 → {tx: PA9, rx: PA10}）。"""
        return {}

    def get_default_tim_instance(self, need_advanced: bool = False) -> str:
        if need_advanced:
            advanced = self.capabilities.get("tim_advanced", ["TIM1"])
            return advanced[0] if advanced else "TIM1"
        return "TIM2"

    def get_default_uart_instance(self) -> str:
        instances = self.capabilities.get("uart_instances", ["USART1"])
        tmp = instances[0]
        return tmp if isinstance(tmp, str) else ""

    def get_default_adc_instance(self) -> str:
        instances = self.capabilities.get("adc_instances", ["ADC1"])
        tmp = instances[0]
        return tmp if isinstance(tmp, str) else ""

    def get_default_spi_instance(self) -> str:
        instances = self.capabilities.get("spi_instances", ["SPI1"])
        tmp = instances[0]
        return tmp if isinstance(tmp, str) else ""

    def get_default_i2c_instance(self) -> str:
        instances = self.capabilities.get("i2c_instances", ["I2C1"])
        tmp = instances[0]
        return tmp if isinstance(tmp, str) else ""

    def to_dict(self) -> dict[str, Any]:
        return self._data


class ProfileManager(IProfileManager):
    """芯片画像管理器：扫描 skills/chips 下所有芯片 Skill 包，FCNT 作为 enrichment 来源。"""

    _SKILL_RESERVED_PREFIXES = ("_", ".")

    def __init__(self, fcnt_module: Any = None) -> None:
        self._profiles: dict[str, ChipProfile] = {}
        self._default_chip = DEFAULT_CHIP_NAME
        self._fcnt = fcnt_module

        # 1. 扫描 skills/chips 下所有芯片包（多芯片卡槽基础）
        self._scan_skill_packages()

        # 2. 若未传入 FCNT，尝试自动加载
        if self._fcnt is None:
            try:
                from knowledge.reserve import fcnt as _fcnt_module
                self._fcnt = _fcnt_module.load()
            except (KnowledgeIOError, OSError, json.JSONDecodeError) as e:
                logger.warning(f"自动加载 FCNT 失败: {e}")

        # 3. 用 FCNT enrich 匹配的芯片画像，并将其设为默认
        if self._fcnt:
            self._enrich_from_fcnt()

        # 4. 确认默认芯片有效
        if self._default_chip not in self._profiles and self._profiles:
            self._default_chip = next(iter(self._profiles.keys()))
            logger.warning(f"默认芯片 {DEFAULT_CHIP_NAME} 未注册，回退到 {self._default_chip}")

        logger.info(f"ProfileManager: 已加载 {len(self._profiles)} 个芯片画像: {list(self._profiles.keys())}")

    def _scan_skill_packages(self) -> None:
        """扫描 skills/chips/* 下的芯片 Skill 包，读取 profile.json。"""
        skills_root = Path(__file__).parent.parent.parent / "skills" / "chips"
        if not skills_root.exists():
            return

        for skill_dir in skills_root.iterdir():
            if not skill_dir.is_dir():
                continue
            if skill_dir.name.startswith(self._SKILL_RESERVED_PREFIXES):
                continue
            profile_path = skill_dir / "profile.json"
            if not profile_path.exists():
                continue
            self._load_skill_profile(skill_dir)

    def _load_skill_profile(self, skill_dir: Path) -> None:
        """加载单个芯片 Skill 包：profile + af_map + standards。"""
        profile_path = skill_dir / "profile.json"
        try:
            with open(profile_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"加载芯片 Skill 失败 {profile_path}: {e}")
            return

        chip_name = data.get("chip") or data.get("chip_name") or data.get("meta", {}).get("chip", "")
        if not chip_name:
            logger.warning(f"芯片 Skill 无芯片名: {skill_dir}")
            return

        # 统一字段名：把 meta 中的关键字段提升到顶层，便于后续访问
        meta = data.get("meta", {})
        data.setdefault("chip_name", chip_name)
        data.setdefault("family", meta.get("family"))
        data.setdefault("core", meta.get("core"))
        data.setdefault("max_clock_mhz", meta.get("max_clock_mhz"))
        data.setdefault("flash_kb", meta.get("flash_kb"))
        data.setdefault("ram_kb", meta.get("ram_kb"))
        data.setdefault("ccm_kb", meta.get("ccm_kb", 0))
        data.setdefault("has_fpu", meta.get("has_fpu"))

        # 区分 profile.json 中的两种 af_map：信号->引脚 与 实例->AF编号
        self._normalize_af_fields(data)

        # 加载 af_map.json
        af_map_path = skill_dir / "af_map.json"
        if af_map_path.exists():
            try:
                with open(af_map_path, encoding="utf-8") as f:
                    af_data = json.load(f)
                data.setdefault("af_numbers", {})
                data.setdefault("af_default_pins", {})
                if not data["af_numbers"]:
                    data["af_numbers"] = af_data.get("af_numbers", {})
                if not data["af_default_pins"]:
                    data["af_default_pins"] = af_data.get("default_pins", {})
            except (OSError, json.JSONDecodeError) as e:
                logger.debug(f"加载 AF 映射失败 {af_map_path}: {e}")

        # 从芯片包自己的 standards/ 加载规则
        self._enrich_from_standards_dir(data, skill_dir / "standards")
        self._profiles[chip_name] = ChipProfile(data)
        logger.info(f"从 Skill 包加载芯片画像: {chip_name} ({skill_dir.name})")

    def _enrich_from_fcnt(self) -> None:
        """用 FCNT 正式知识模块 enrich 已扫描到的匹配芯片画像，并设为默认。"""
        try:
            meta = self._fcnt.get_chip_info()
            if not meta:
                logger.warning("FCNT 模块无芯片信息，跳过 enrichment")
                return

            chip_name = meta.get("chip", DEFAULT_CHIP_NAME)

            # 找到匹配的已注册芯片（名称包含关系）
            target_name = self._resolve_fcnt_target(chip_name)
            if target_name is None:
                # 未匹配到现有芯片包，则以 FCNT 数据新建一个画像
                target_name = chip_name
                self._profiles[target_name] = ChipProfile({})

            existing = self._profiles[target_name].to_dict()
            fcnt_data = {
                "chip_name": chip_name,
                "family": meta.get("family", existing.get("family", "F4")),
                "core": meta.get("core", existing.get("core", "Cortex-M4")),
                "max_clock_mhz": meta.get("max_clock_mhz", existing.get("max_clock_mhz", 168)),
                "flash_kb": meta.get("flash_kb", existing.get("flash_kb", 512)),
                "ram_kb": meta.get("ram_kb", existing.get("ram_kb", 192)),
                "has_fpu": meta.get("has_fpu", existing.get("has_fpu", True)),
                "capabilities": self._merge_capabilities(
                    existing.get("capabilities", {}),
                    self._fcnt.get_chip_capabilities(),
                ),
                "pin_map": self._fcnt.profile.get("pin_map", existing.get("pin_map", {})),
                "clock_bus": self._fcnt.profile.get("clock_bus", existing.get("clock_bus", {})),
                "af_map": self._fcnt.profile.get("af_map", existing.get("af_map", {})),
                "skeleton": self._fcnt.profile.get("skeleton", existing.get("skeleton", {})),
                "dma": self._fcnt.profile.get("dma", existing.get("dma", {})),
                "debug": self._fcnt.profile.get("debug", existing.get("debug", {"error_led_pin": "PA5"})),
                "constraints": self._merge_constraints(
                    existing.get("constraints", {}),
                    {
                        "init_order": self._fcnt.profile.get("init_order", []),
                        "clock_requirements": self._fcnt.get_clock_requirements(),
                        "nvic_priorities": self._fcnt.profile.get("nvic_priorities", {}),
                        "special_pins": self._fcnt.profile.get("special_pins", {}),
                    },
                ),
            }
            existing.update(fcnt_data)
            self._normalize_af_fields(existing)
            self._profiles[target_name] = ChipProfile(existing)
            self._default_chip = target_name
            logger.info(f"从 FCNT enrichment 芯片画像: {target_name}")

        except (KnowledgeIOError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"FCNT enrichment 失败: {e}")

    def _resolve_fcnt_target(self, chip_name: str) -> str | None:
        """根据 FCNT 芯片名找到已注册的匹配芯片画像。"""
        if chip_name in self._profiles:
            return chip_name
        name_lower = chip_name.lower()
        for key in self._profiles:
            key_lower = key.lower()
            if name_lower in key_lower or key_lower in name_lower:
                return key
        return None

    @staticmethod
    def _merge_capabilities(existing: dict[str, Any], fcnt_caps: dict[str, Any]) -> dict[str, Any]:
        """合并芯片能力：FCNT 补充未覆盖的字段，但不删除已有字段。"""
        result = dict(existing)
        for k, v in fcnt_caps.items():
            if k not in result or not result[k]:
                result[k] = v
        return result

    @staticmethod
    def _merge_constraints(existing: dict[str, Any], fcnt_constraints: dict[str, Any]) -> dict[str, Any]:
        """合并约束：FCNT 补充未覆盖的字段，但不删除已有字段。"""
        result = dict(existing)
        for k, v in fcnt_constraints.items():
            if k not in result or not result[k]:
                result[k] = v
            elif isinstance(result[k], dict) and isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    if sub_k not in result[k] or not result[k][sub_k]:
                        result[k][sub_k] = sub_v
        return result

    @staticmethod
    def _normalize_af_fields(data: dict[str, Any]) -> None:
        """统一 AF 字段语义：

        - profile.json 里的 ``af_map`` 如果是 ``信号 -> 引脚``（值为字符串），
          则重命名为 ``signal_af_map``，避免和 ``af_map.json`` 里的 AF 编号冲突。
        - profile.json 里的 ``af_map`` 如果是 ``实例 -> AF 编号``（值为整数），
          则重命名为 ``af_numbers``。
        """
        af_map = data.get("af_map")
        if not isinstance(af_map, dict) or not af_map:
            data.pop("af_map", None)
            return

        sample_value = next(iter(af_map.values()))
        if isinstance(sample_value, str):
            # 信号 -> 引脚映射
            data["signal_af_map"] = af_map
            data.pop("af_map", None)
        elif isinstance(sample_value, (int, float)):
            # 实例 -> AF 编号映射
            data["af_numbers"] = af_map
            data.pop("af_map", None)
        else:
            # 无法识别，保留原字段但清空，避免后续误用
            logger.warning(f"af_map 字段类型无法识别（sample={sample_value!r}），已忽略")
            data.pop("af_map", None)

    def _enrich_from_standards_dir(self, data: dict[str, Any], standards_dir: Path) -> None:
        """从芯片包自己的 standards/ 目录加载外设标准规则。"""
        if not standards_dir.exists():
            return
        constraints = data.setdefault("constraints", {})
        peripheral_rules = constraints.setdefault("peripheral_rules", {})
        for peri, filename in PERIPHERAL_STANDARDS.items():
            std_path = standards_dir / filename
            if not std_path.exists():
                continue
            try:
                with open(std_path, encoding="utf-8") as f:
                    std_data = json.load(f)
                rules = []
                for scene_name, scene_data in std_data.get("scenes", {}).items():
                    for rule in scene_data.get("rules", []):
                        rules.append({
                            "id": rule.get("id", ""),
                            "level": rule.get("level", ""),
                            "description": rule.get("description", ""),
                            "scene": scene_name,
                        })
                peripheral_rules[peri] = rules
            except (OSError, json.JSONDecodeError) as e:
                logger.debug(f"加载标准文件失败 {std_path}: {e}")

    def get_profile(self, chip_name: str | None = None) -> ChipProfile:
        name = chip_name or self._default_chip
        if name in self._profiles:
            return self._profiles[name]
        for key in self._profiles:
            if name.upper() in key.upper() or key.upper() in name.upper():
                return self._profiles[key]
        logger.warning(f"未找到芯片画像: {name}，使用默认 {self._default_chip}")
        if self._default_chip in self._profiles:
            return self._profiles[self._default_chip]
        raise ValueError(f"无可用芯片画像: {name}")

    def list_profiles(self) -> list[str]:
        return list(self._profiles.keys())

    def set_default(self, chip_name: str) -> None:
        if chip_name in self._profiles:
            self._default_chip = chip_name
        else:
            logger.warning(f"芯片 {chip_name} 不在画像中: {list(self._profiles.keys())}")
