"""芯片系列统一入口（智能巡查点）：型号判定、系列注册、HAL 库路径等全部经此索引，新增系列只改本文件注册表。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from contracts.exceptions import ChipResolutionError

# 项目根目录：本文件位于 infrastructure/ 下，上级即项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# reference HAL 库默认目录名规则：reference-stm32<key.lower()>（F1/F4/G4 → f1/f4/g4）
_DEFAULT_REFERENCE_NAME = "reference-stm32"
# reference 目录环境变量（F4 兼容旧变量名 S_REFERENCE_DIR）
_REFERENCE_ENV_VARS = {
    "F1": "S_REFERENCE_DIR_F1",
    "F4": "S_REFERENCE_DIR",
    "G4": "S_REFERENCE_DIR_G4",
}


@dataclass(frozen=True)
class FamilyAdapter:
    """一个芯片系列的对接器：持有该系列的全部路径/命名/覆盖信息。

    去枚举（2026-08-22）：由 ``_build_adapters()`` 扫 ``_series/*/family.json`` 自动注册，
    加系列 = 放一个 family.json，不改代码。
    """

    key: str                       # 系列键："STM32F4xx"（family.json 的 name）
    series_dir: str                # skills/chips/_series 下目录："f4"
    reference_key: str             # reference 库目录键："F4"（同系列复用：F446→F4）
    hal_prefix: str                # HAL 文件前缀："stm32f4xx"
    templates_key: str             # 模板注册表键："STM32F4xx"（变体复用基础系列）
    default_chip: str              # 该系列默认芯片 profile 名（小写）
    defines: tuple[str, ...] = ()  # 型号前缀识别（family.json 的 defines，如 "STM32F446xx"）
    source_overrides: dict[str, list[str]] = field(default_factory=dict)  # 外设→HAL 源覆盖
    startup_from_reference: bool = False  # 启动文件取自 reference 库（G4 官方 GCC 文件）


@dataclass(frozen=True)
class ChipResolution:
    """芯片解析上下文：切换机制（调度自动切换）的载体。

    一次 ``resolve()`` 解析出范式/系列/命名/路径等全链路所需信息，
    装配流水线从它取值，不再各自问 ``default_chip()``。
    """

    chip_name: str       # 规范化小写芯片名（具体型号/分支），如 "stm32f103c8t6"
    paradigm: str        # 范式键，如 "stm32"（预留 "esp32"）
    family_key: str      # 系列键，如 "STM32F1xx"
    series_dir: str      # 系列目录名，如 "f1"
    hal_prefix: str      # HAL 前缀，如 "stm32f1xx"
    reference_key: str   # reference 目录键，如 "F1"
    templates_key: str   # 模板注册键，如 "STM32F1xx"
    model_segment: str   # 型号段大类，如 "STM32F407"（芯片包对外接口）


# ========== 系列对接器注册表：扫 _series/*/family.json 自动注册（去枚举） ==========
def _derive_reference_key(name: str) -> str:
    """family.json 的 name → reference 库目录键（STM32F4xx_F446 → F4，STM32F7xx → F7）。"""
    base = name.split("_")[0]  # 变体（STM32F4xx_F446）取基础系列 STM32F4xx
    m = re.match(r"STM32([A-Z0-9]+?)xx", base)
    return m.group(1) if m else name


def _derive_templates_key(name: str) -> str:
    """family.json 的 name → 模板注册键（变体复用基础系列的模板）。"""
    return name.split("_")[0]


def _derive_hal_prefix(system_file: str) -> str:
    """family.json 的 system_file → HAL 前缀（system_stm32f4xx.c → stm32f4xx）。"""
    m = re.match(r"system_(stm32\w+)\.c", system_file)
    return m.group(1) if m else ""


def _chips_dir() -> Path:
    """chips 根目录（AGENT_S_CHIPS_DIR 可替换，与 config.CHIPS_DIR 同源）。

    独立实现避免模块加载期的 config ↔ chip_gateway 循环 import。
    """
    return Path(os.environ.get("AGENT_S_CHIPS_DIR", str(PROJECT_ROOT / "skills" / "chips")))


# 默认系列（未配置时，含空车降级用的示意默认芯片）
_DEFAULT_KEY = "STM32F4xx"
_DEFAULT_CHIP = "stm32f407zgt6"


def _fallback_adapter() -> FamilyAdapter:
    """空车降级：无任何 _series/family.json 时，注入内置示意 F4 适配器兜底。"""
    return FamilyAdapter(
        key=_DEFAULT_KEY,
        series_dir="f4",
        reference_key="F4",
        hal_prefix="stm32f4xx",
        templates_key=_DEFAULT_KEY,
        default_chip=_DEFAULT_CHIP,
    )


def _build_adapters() -> dict[str, FamilyAdapter]:
    """扫 ``skills/chips/_series/*/family.json`` 自动注册 FamilyAdapter（去枚举）。

    加系列 = 放一个 `_series/<dir>/family.json`（含 name/defines/system_file/default_chip），
    本函数自动接入，不改代码。
    """
    import json

    series_root = _chips_dir() / "_series"
    adapters: dict[str, FamilyAdapter] = {}
    if not series_root.exists():
        adapters[_DEFAULT_KEY] = _fallback_adapter()
        return adapters

    for series_dir in sorted(p.name for p in series_root.iterdir() if p.is_dir()):
        fam_path = series_root / series_dir / "family.json"
        if not fam_path.exists():
            continue
        try:
            fam = json.loads(fam_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(fam, dict):
            continue
        name = str(fam.get("name", ""))
        hal_prefix = _derive_hal_prefix(str(fam.get("system_file", "")))
        if not name or not hal_prefix:
            continue
        adapters[name] = FamilyAdapter(
            key=name,
            series_dir=series_dir,
            reference_key=_derive_reference_key(name),
            hal_prefix=hal_prefix,
            templates_key=_derive_templates_key(name),
            default_chip=str(fam.get("default_chip", "")),
            defines=tuple(str(d) for d in fam.get("defines", [])),
            startup_from_reference=(series_dir == "g4"),
        )
    if not adapters:
        adapters[_DEFAULT_KEY] = _fallback_adapter()
    return adapters


_FAMILY_ADAPTERS: dict[str, FamilyAdapter] = _build_adapters()

# 环境变量：默认芯片 / 默认系列切换点
_ENV_DEFAULT_CHIP = "S_DEFAULT_CHIP"
_ENV_DEFAULT_FAMILY = "S_DEFAULT_FAMILY"


class ChipGateway:
    """智能巡查点：全部芯片出口/入口的唯一索引。"""

    def __init__(self, adapters: dict[str, FamilyAdapter] | None = None) -> None:
        self._adapters: dict[str, FamilyAdapter] = dict(adapters or _FAMILY_ADAPTERS)
        # 判定顺序 = 注册顺序（dict 有序；动态新增 adapter 自动生效，不依赖静态列表）

    # ---------- 型号/系列判定 ----------
    def family_key_for_chip(self, chip_name: str) -> str:
        """芯片型号或系列名 → 系列键（未知回退默认系列）。

        兼容多种输入：精确系列键（"STM32F4xx"）、reference 简称（"F1"/"F4"/"G4"）、
        具体型号（"STM32F103C8T6" / "stm32g431rbt6"）。识别优先级：
        精确键 → 简称 → 芯片包 manifest 声明 → defines 型号/系列前缀（去枚举）。
        """
        return self._try_family_key(chip_name) or _DEFAULT_KEY

    def _try_family_key(self, chip_name: str) -> str | None:
        """识别系列键，识别不到返回 None（不回退默认）。

        供 ``family_key_for_chip``（回退默认）与 ``resolve``（fail-closed）共用。
        """
        s = str(chip_name).upper()
        # 1. 精确系列键（如 STM32F4xx_F446）
        if s in self._adapters:
            return s
        # 2. reference 简称 / 系列名包含匹配（F1/F4/G4）
        for key, adapter in self._adapters.items():
            if s in (adapter.reference_key, key.upper()):
                return key
        # 3. 芯片包 manifest 声明（去枚举：读 chip.family，不靠 token 硬编码）
        manifest_key = self._family_from_chip_manifest(chip_name)
        if manifest_key:
            return manifest_key
        # 4. defines 型号前缀匹配（精确到子型号，如 STM32F446 → F4_F446 变体）
        for key, adapter in self._adapters.items():
            for define in adapter.defines:
                prefix = self._model_prefix(define)
                if prefix and s.startswith(prefix):
                    return key
        # 5. 系列前缀匹配（STM32G4/STM32F4，识别系列内非默认型号，如 G474/F429）
        for key, adapter in self._adapters.items():
            sp = self._series_prefix(adapter.hal_prefix)
            if sp and s.startswith(sp):
                return key
        return None

    def _family_from_chip_manifest(self, chip_name: str) -> str | None:
        """扫 chips 目录读芯片包 manifest 的 chip.family 声明 → 系列键。"""
        from infrastructure.config import CHIPS_DIR

        chips_dir = Path(CHIPS_DIR)
        name = str(chip_name).lower().strip()
        if not name or not chips_dir.exists():
            return None
        matched: list[Path] = []
        for p in sorted(chips_dir.iterdir()):
            if not p.is_dir() or p.name.startswith("_"):
                continue
            pn = p.name.lower()
            if pn == name or (name in pn) or (pn in name):
                matched.append(p)
        for p in matched:
            family = self._read_manifest_family(p)
            if family:
                key = self._family_to_key(family)
                if key:
                    return key
        return None

    @staticmethod
    def _read_manifest_family(chip_dir: Path) -> str | None:
        """读芯片包 manifest.yaml 的 chip.family 字段（无 yaml 依赖，正则直读）。"""
        manifest_path = chip_dir / "manifest.yaml"
        if not manifest_path.exists():
            return None
        try:
            text = manifest_path.read_text(encoding="utf-8")
        except OSError:
            return None
        m = re.search(r"^\s*family:\s*(\w+)", text, re.MULTILINE)
        return m.group(1).upper() if m else None

    @staticmethod
    def _read_manifest_model_segment(chip_dir: Path) -> str:
        """读芯片包 manifest.yaml 的 model_segment 字段（型号段大类，如 STM32F407）。"""
        manifest_path = chip_dir / "manifest.yaml"
        if not manifest_path.exists():
            return ""
        try:
            text = manifest_path.read_text(encoding="utf-8")
        except OSError:
            return ""
        m = re.search(r'^\s*model_segment:\s*"?(\w+)"?', text, re.MULTILINE)
        return m.group(1).upper() if m else ""

    def _family_to_key(self, family: str) -> str | None:
        """series.family（如 "F4"）→ 系列键（如 "STM32F4xx"）。"""
        fam = str(family).upper()
        for key, adapter in self._adapters.items():
            if adapter.reference_key.upper() == fam:
                return key
        return None

    @staticmethod
    def _model_prefix(define: str) -> str:
        """family.json 的 defines 型号宏 → 型号前缀（STM32F446xx → STM32F446）。"""
        m = re.match(r"(STM32\w+?)x", define, re.IGNORECASE)
        return m.group(1).upper() if m else ""

    @staticmethod
    def _series_prefix(hal_prefix: str) -> str:
        """HAL 前缀 → 系列前缀（stm32g4xx → STM32G4，识别系列内非默认型号如 G474）。"""
        m = re.match(r"stm32([a-z]\d)", hal_prefix, re.IGNORECASE)
        return f"STM32{m.group(1).upper()}" if m else ""

    def _is_ambiguous_series(self, chip_name: str) -> bool:
        """判断输入是否为「系列级」（纯系列键/简称），此类输入有歧义（下有多型号段）。

        例：F4 / STM32F4xx 都是系列级（下有 F407/F429/F446…），不能静默选默认；
        STM32F4xx_F446 是变体（已精确到型号段），不算歧义。
        """
        s = str(chip_name).upper()
        for key, adapter in self._adapters.items():
            if "_" not in key and s == key.upper():
                return True
            if s == adapter.reference_key.upper():
                return True
        return False

    # ---------- 切换机制（调度自动切换） ----------
    def resolve(self, chip_name: str) -> ChipResolution:
        """解析芯片名 → ChipResolution（切换机制统一入口）。

        fail-closed：识别不到明确抛 ChipResolutionError，绝不静默回退默认芯片；
        系列级输入（F4/STM32F4xx）报歧义，要求精确到具体型号。
        装配流水线应从本方法取上下文，而不是各自问 default_chip()。
        """
        if self._is_ambiguous_series(chip_name):
            raise ChipResolutionError(
                f"歧义: {chip_name!r} 是系列级输入，下有多个型号段，请指定具体型号"
            )
        key = self._try_family_key(chip_name)
        if key is None:
            raise ChipResolutionError(
                f"未知芯片/系列: {chip_name!r}，未在 skills/chips 或 _series 注册"
            )
        adapter = self._adapters[key]
        normalized = self._normalize_chip(chip_name)
        self._verify_chip_materials(normalized)
        return ChipResolution(
            chip_name=normalized,
            paradigm=self._paradigm_for(adapter),
            family_key=key,
            series_dir=adapter.series_dir,
            hal_prefix=adapter.hal_prefix,
            reference_key=adapter.reference_key,
            templates_key=adapter.templates_key,
            model_segment=self._model_segment_for(normalized),
        )

    def _model_segment_for(self, chip_name: str) -> str:
        """定位芯片包目录读 model_segment（型号段大类）；无芯片包（F446/F7）返回空。"""
        chips_dir = _chips_dir()
        name = str(chip_name).lower()
        if not chips_dir.exists():
            return ""
        for p in sorted(chips_dir.iterdir()):
            if not p.is_dir() or p.name.startswith("_"):
                continue
            if p.name.lower() == name:
                return self._read_manifest_model_segment(p)
        return ""

    def _verify_chip_materials(self, chip_name: str) -> None:
        """材料安检（门槛2）：芯片包目录存在则校验三件套齐全，缺则 fail-closed。"""
        chips_dir = _chips_dir()
        chip_dir = chips_dir / str(chip_name).lower()
        if not chip_dir.exists():
            return  # 无芯片包（F446/F7 系列级），不校验
        missing = [f for f in ("profile.json", "pin_map.json", "af_map.json") if not (chip_dir / f).exists()]
        if missing:
            raise ChipResolutionError(f"材料缺失: {chip_name} 缺 {', '.join(missing)}")

    @staticmethod
    def _normalize_chip(chip_name: str) -> str:
        """规范化芯片名：转小写、去空白。"""
        return str(chip_name).strip().lower()

    @staticmethod
    def _paradigm_for(adapter: FamilyAdapter) -> str:
        """从范式基座（_common）读范式键（paradigm 字段）；缺失 fallback "stm32"。

        范式显式化（P4）：范式由材料声明，不再硬编码。将来 ESP32 范式放同级基座
        （_paradigms/esp32/），本函数读对应基座的 paradigm 字段即可。
        """
        common_manifest = _chips_dir() / "_common" / "manifest.yaml"
        if common_manifest.exists():
            try:
                text = common_manifest.read_text(encoding="utf-8")
            except OSError:
                text = ""
            m = re.search(r"^\s*paradigm:\s*(\w+)", text, re.MULTILINE)
            if m:
                return m.group(1).lower()
        return "stm32"

    def adapter_for_chip(self, chip_name: str) -> FamilyAdapter:
        return self._adapters[self.family_key_for_chip(chip_name)]

    def adapter_for_key(self, key: str) -> FamilyAdapter:
        return self._adapters.get(str(key), self._adapters[_DEFAULT_KEY])

    # ---------- 默认芯片（可切换） ----------
    def default_chip(self) -> str:
        """当前默认芯片 profile 名：S_DEFAULT_CHIP > S_DEFAULT_FAMILY > F4 默认。"""
        env_chip = os.environ.get(_ENV_DEFAULT_CHIP)
        if env_chip:
            return env_chip.strip().lower()
        env_family = os.environ.get(_ENV_DEFAULT_FAMILY)
        if env_family:
            key = self.family_key_for_chip(env_family)
            if key == _DEFAULT_KEY and env_family.upper() not in ("F4", "STM32F4XX"):
                # 环境变量是系列名时按前缀精确匹配
                for k, a in self._adapters.items():
                    if env_family.upper() in (a.reference_key, k.upper()):
                        return a.default_chip
            return self._adapters[key].default_chip
        return self._adapters[_DEFAULT_KEY].default_chip

    def default_adapter(self) -> FamilyAdapter:
        return self.adapter_for_chip(self.default_chip())

    # ---------- 路径与命名（统一索引） ----------
    def series_dir(self, key: str) -> str:
        return self.adapter_for_key(key).series_dir

    def hal_prefix(self, chip_or_key: str) -> str:
        """芯片型号或系列键 → HAL 前缀（stm32f4xx / stm32f1xx / stm32g4xx）。"""
        key = self.family_key_for_chip(chip_or_key)
        return self.adapter_for_key(key).hal_prefix

    def templates_key(self, key: str) -> str:
        return self.adapter_for_key(key).templates_key

    def source_overrides(self, key: str) -> dict[str, list[str]]:
        return self.adapter_for_key(key).source_overrides

    def peripheral_hal_sources(self, series_dir: str) -> dict[str, list[str]]:
        """读 ``_series/<dir>/manifest.yaml`` 的 hal_peripherals → {外设: [.c 源文件]}（识别公共区块）。

        外设→HAL 源文件映射按系列材料化（manifest.yaml 的 hal_peripherals 声明），
        编译处（makefile_generator）据此精确过滤源文件，不再写死 F4 表 + replace 前缀。
        manifest 缺失的系列（f4_f446/f7）回退 f4——变体复用 F4 库；f7 缺库编译 skipped。
        """
        import yaml

        def _load(dir_name: str) -> dict[str, list[str]]:
            manifest = _chips_dir() / "_series" / dir_name / "manifest.yaml"
            if not manifest.exists():
                return {}
            try:
                data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                return {}
            if not isinstance(data, dict):
                return {}
            result: dict[str, list[str]] = {}
            for p in data.get("hal_peripherals") or []:
                if not isinstance(p, dict):
                    continue
                name = p.get("name")
                files = [str(f) for f in p.get("hal_files", []) or [] if str(f).endswith(".c")]
                if name and files:
                    result[str(name).upper()] = files
            return result

        return _load(series_dir) or _load("f4")

    def startup_from_reference(self, key: str) -> bool:
        return self.adapter_for_key(key).startup_from_reference

    def reference_dir(self, chip_or_key: str) -> Path:
        """按系列解析 reference HAL 库目录（未知回退 F4；环境变量可覆盖）。"""
        key = self.adapter_for_key(
            self.family_key_for_chip(chip_or_key)
        ).reference_key
        env = _REFERENCE_ENV_VARS.get(key)
        if env and os.environ.get(env):
            return Path(os.environ[env])
        return PROJECT_ROOT.parent / f"{_DEFAULT_REFERENCE_NAME}{key.lower()}"

    # ---------- 枚举 ----------
    def list_adapters(self) -> dict[str, FamilyAdapter]:
        return dict(self._adapters)

    def reference_keys(self) -> list[str]:
        """去重后的 reference 目录键（F446 复用 F4 → 只出一次）。"""
        seen: list[str] = []
        for a in self._adapters.values():
            if a.reference_key not in seen:
                seen.append(a.reference_key)
        return seen

    def list_supported_chips(self) -> list[str]:
        """扫描 chips 目录下全部已注册芯片 profile。

        2026-08-19 拔插式：chips 目录从 config.CHIPS_DIR 取（AGENT_S_CHIPS_DIR 可替换）。
        """
        from infrastructure.config import CHIPS_DIR

        chips_dir = Path(CHIPS_DIR)
        names: list[str] = []
        if chips_dir.exists():
            for p in sorted(chips_dir.iterdir()):
                if p.is_dir() and not p.name.startswith("_") and (p / "profile.json").exists():
                    names.append(p.name)
        return names


# 全局单例：对外一律用 gateway
gateway = ChipGateway()


# ========== 模块级便捷函数（调用方从本模块 import 即可） ==========
def family_key_for_chip(chip_name: str) -> str:
    return gateway.family_key_for_chip(chip_name)


def adapter_for_chip(chip_name: str) -> FamilyAdapter:
    return gateway.adapter_for_chip(chip_name)


def default_chip() -> str:
    return gateway.default_chip()


def reference_dir(chip_or_key: str) -> Path:
    return gateway.reference_dir(chip_or_key)


def hal_prefix(chip_or_key: str) -> str:
    return gateway.hal_prefix(chip_or_key)


def resolve(chip_name: str) -> ChipResolution:
    """切换机制入口：解析芯片名 → ChipResolution（fail-closed，识别不到抛异常）。"""
    return gateway.resolve(chip_name)


__all__ = [
    "FamilyAdapter",
    "ChipResolution",
    "ChipGateway",
    "gateway",
    "family_key_for_chip",
    "adapter_for_chip",
    "default_chip",
    "reference_dir",
    "hal_prefix",
    "resolve",
    "PROJECT_ROOT",
]
