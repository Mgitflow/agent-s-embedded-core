"""全局配置：路径、芯片 Skill 包系统与运行时开关。"""
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ═══════════════════════════════════════════
# 芯片 Skill 包（版本随项目，见 pyproject.toml / VERSION_LEDGER）
# 唯一芯片真相源：chip_gateway.default_chip()（默认 stm32f407zgt6），
# 可经 AGENT_S_CHIP / S_DEFAULT_CHIP / S_DEFAULT_FAMILY 环境变量切换（不再代码写死）。
# ═══════════════════════════════════════════
from infrastructure.chip_gateway import default_chip as _gateway_default_chip  # noqa: E402

_gateway_default = _gateway_default_chip()
ACTIVE_CHIP = os.environ.get("AGENT_S_CHIP", _gateway_default)
DEFAULT_CHIP_NAME = os.environ.get("AGENT_S_CHIP_NAME", _gateway_default.upper())

# 芯片肖像根（抽象接口，AB 门）：AGENT_S_CHIPS_DIR 可整体替换为候选/临时材料，
# 默认项目内 skills/chips。CHIP_SKILL_DIR/CHIP_MANIFEST/CHIPS_DIR 全部走它。
_CHIPS_ROOT = Path(os.environ.get("AGENT_S_CHIPS_DIR", str(PROJECT_ROOT / "skills" / "chips")))
CHIP_SKILL_DIR = str(_CHIPS_ROOT / ACTIVE_CHIP)
CHIP_MANIFEST = str(_CHIPS_ROOT / ACTIVE_CHIP / "manifest.yaml")


# config/settings.yaml 统一读取入口（server / assembly 共用，避免循环依赖与重复读取）
_settings_cache: dict[str, Any] | None = None


def load_settings() -> dict[str, Any]:
    """读取 config/settings.yaml（带缓存）。缺失/损坏返回 {}，不抛异常。"""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    if not settings_path.exists():
        _settings_cache = {}
        return _settings_cache
    try:
        import yaml

        with open(settings_path, encoding="utf-8") as f:
            _settings_cache = yaml.safe_load(f) or {}
    except Exception:  # noqa: BLE001
        _settings_cache = {}
    return _settings_cache


# 从 manifest 动态加载芯片配置（懒加载，首次访问时解析）
_chip_config_cache: dict[str, Any] | None = None


def get_chip_config(chip_name: str | None = None) -> dict[str, Any]:
    """加载指定芯片的 manifest 配置。不传则使用当前 AGENT_S_CHIP。"""
    global _chip_config_cache, CHIP_MANIFEST, CHIP_SKILL_DIR
    # 修复（审查 P1）：此前无参 fallback "stm32f407"（skills/chips/ 下不存在）
    # 与 ACTIVE_CHIP 默认 "apm32f407vgt6" 分叉 → 默认环境 get_chip_config() 返回空 dict
    # → fcnt 芯片 Skill 包静默加载失败。统一单一默认值。
    active = chip_name or ACTIVE_CHIP
    current_manifest = str(_CHIPS_ROOT / active / "manifest.yaml")
    if chip_name is None and _chip_config_cache is not None and CHIP_MANIFEST == current_manifest:
        return _chip_config_cache
    import yaml
    manifest_path = Path(current_manifest)
    config: dict[str, Any] = {}
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    if chip_name is None:
        CHIP_MANIFEST = current_manifest
        CHIP_SKILL_DIR = str(_CHIPS_ROOT / active)
        _chip_config_cache = config
    return config


def get_chip_skill_dir(chip_name: str | None = None) -> str:
    """获取指定芯片的 Skill 包目录。不传则使用当前 AGENT_S_CHIP。"""
    active = chip_name or ACTIVE_CHIP  # 统一默认（此前 "stm32f407" 不存在）
    return str(_CHIPS_ROOT / active)


def get_chip_standards_dir(chip_name: str | None = None) -> str:
    """获取指定芯片的 standards 目录。不传则使用当前 AGENT_S_CHIP。"""
    skill_dir = Path(get_chip_skill_dir(chip_name))
    return str(skill_dir / "standards")


# 工作区（编译产物归档根）
# 「，不被当垃圾」：默认写到项目外同级目录
# <parent>/agent-s-output/（与项目 git 仓库物理隔离），AGENT_S_WORKSPACE 可覆盖。
_OUTPUT_EXTERNAL = PROJECT_ROOT.parent / "agent-s-output"
WORKSPACE_ROOT = os.environ.get("AGENT_S_WORKSPACE", str(_OUTPUT_EXTERNAL))

# LM Studio
LM_STUDIO_URL = os.environ.get("AGENT_S_LLM_URL", "http://127.0.0.1:1234/v1/chat/completions")
LM_STUDIO_TIMEOUT = int(os.environ.get("AGENT_S_LLM_TIMEOUT", "300"))
LM_STUDIO_STREAM_TIMEOUT = int(os.environ.get("AGENT_S_STREAM_TIMEOUT", "120"))

# ── LLM 双通道：本地 LM Studio 直连 ↔ 云端 OpenAI 兼容 API ──
# 设置 AGENT_S_LLM_API_KEY 即启用云端通道（自动附加 Authorization: Bearer）。
# AGENT_S_LLM_CLOUD_URL 指定云端端点（OpenAI 兼容，如 https://api.deepseek.com/v1/chat/completions）。
# 本地限制多（显存/并发/模型），云端 API 可换更大模型、更高并发。
LLM_API_KEY = os.environ.get("AGENT_S_LLM_API_KEY", "")
LLM_CLOUD_URL = os.environ.get("AGENT_S_LLM_CLOUD_URL", "")
LLM_PROVIDER = "cloud" if (LLM_API_KEY or LLM_CLOUD_URL) else "local"

# 模型路由
MODEL_R1 = os.environ.get("AGENT_S_MODEL_R1", "oreal-deepseek-r1-distill-qwen-7b")
MODEL_CODE = os.environ.get("AGENT_S_MODEL_CODE", "qwen2.5-coder-7b-instruct")
MODEL_VL = os.environ.get("AGENT_S_MODEL_VL", "qwen2.5-vl-7b-q4_0/qwen2.5-vl-7b-instruct")
MODEL_TIFA = os.environ.get("AGENT_S_MODEL_TIFA", "tifa-7b-qwen2-v0.1")

# 知识库路径（三区架构：reserve / beaker / reflux）
KNOWLEDGE_BASE = str(PROJECT_ROOT / "knowledge")
RESERVE_DIR = str(PROJECT_ROOT / "knowledge" / "reserve")
BEAKER_DIR = str(PROJECT_ROOT / "knowledge" / "beaker")
# 修根：REFLUX_DIR 支持 AGENT_S_REFLUX_DIR 环境变量覆盖——
# 测试通过 conftest 指向临时目录，回流数据与运行时隔离（此前测试写真实
# knowledge/reflux/ 被 IDE 锁即挂）。未设置时保持项目内路径不变。
REFLUX_DIR = os.environ.get(
    "AGENT_S_REFLUX_DIR",
    str(PROJECT_ROOT / "knowledge" / "reflux"),
)
LOADERS_DIR = str(PROJECT_ROOT / "knowledge" / "loaders")

# ═══════════════════════════════════════════
# 核心数据根（拔插式改造：open-core 护城河）
# 芯片肖像（skills/chips）与功能模板（forge_templates）是 S 的「数据库」——
# 骨架开源、数据可插拔。这两个目录通过本「数据根」统一索引，可用环境变量
# 整体替换（指向外部数据包），骨架代码零改动即可「换数据库」。
# ═══════════════════════════════════════════

# 芯片肖像根：默认项目内 skills/chips，AGENT_S_CHIPS_DIR 可整体替换
CHIPS_DIR = Path(os.environ.get(
    "AGENT_S_CHIPS_DIR",
    str(PROJECT_ROOT / "skills" / "chips"),
))

# 功能模板根：默认项目内 forge_templates，AGENT_S_TEMPLATES_DIR 可整体替换
TEMPLATES_DIR = Path(os.environ.get(
    "AGENT_S_TEMPLATES_DIR",
    str(PROJECT_ROOT / "knowledge" / "template_forge" / "forge_templates"),
))

# 手册资料根：电气手册/开发手册/资料索引等「芯片硬件资料」统一归知识库分区
# （定：芯片肖像目录，单独开 knowledge/manuals/<chip>/，
# 按芯片名对应；芯片肖像 skills/chips/<chip>/ 只留结构数据 profile/pin_map/af_map）。
# AGENT_S_MANUALS_DIR 可整体替换（拔插式，与 CHIPS_DIR 同机制）。
MANUALS_DIR = Path(os.environ.get(
    "AGENT_S_MANUALS_DIR",
    str(PROJECT_ROOT / "knowledge" / "manuals"),
))


def manual_dir(chip: str | None = None) -> Path:
    """某芯片的手册资料目录：knowledge/manuals/<chip>/（芯片名对应）。"""
    active = chip or ACTIVE_CHIP
    return MANUALS_DIR / active


# 外设标准路径 (v2.3.0: 从芯片 Skill 包动态加载)
STANDARDS_DIR = str(CHIPS_DIR / ACTIVE_CHIP / "standards")


def _discover_standard_paths(base: Path) -> dict[str, str]:
    """扫描芯片 Skill 包的 standards/ 目录，自动发现 *_standard.json 文件。"""
    paths: dict[str, str] = {}
    if not base.is_dir():
        return paths
    for path in base.glob("*_standard.json"):
        # gpio_standard.json -> GPIO
        peripheral = path.stem.replace("_standard", "").upper()
        paths[peripheral] = str(path)
    return paths


# 运行时按 ACTIVE_CHIP 动态构建，通过 get_standard_paths() 延迟访问
_STANDARD_PATHS_CACHE: dict[str, str] | None = None


def get_standard_paths(chip_name: str | None = None) -> dict[str, str]:
    """获取指定芯片的标准路径（延迟构建）。"""
    global _STANDARD_PATHS_CACHE
    active = chip_name or ACTIVE_CHIP
    base = _CHIPS_ROOT / active / "standards"
    paths = _discover_standard_paths(base)
    if chip_name is None:
        _STANDARD_PATHS_CACHE = paths
    return paths


# 向后兼容别名
STANDARD_PATHS = get_standard_paths()
STANDARDS_PATH = STANDARDS_DIR

# 回流（沉淀日志）——修根：全部从 REFLUX_DIR（支持 AGENT_S_REFLUX_DIR
# 环境变量覆盖）派生，测试隔离 reflux 数据时一处设置全生效。
KNOWLEDGE_RAW_PATH = str(PROJECT_ROOT / "knowledge" / "crawled")  # 补：integrator 原始知识目录（从 E 抄 integrator 时漏配）
KNOWLEDGE_VERIFIED_PATH = os.path.join(REFLUX_DIR, "verified.json")
KNOWLEDGE_INTEGRATED_PATH = os.path.join(REFLUX_DIR, "integrated.json")
KNOWLEDGE_MISMATCH_PATH = os.path.join(REFLUX_DIR, "mismatch.json")
ERROR_LOG_PATH = os.path.join(REFLUX_DIR, "error.json")
ACCUMULATION_PATH = REFLUX_DIR
FEEDBACK_QUEUE_PATH = os.path.join(REFLUX_DIR, "feedback_queue.json")

# 知识治理开关
KNOWLEDGE_ENABLED = True
KNOWLEDGE_CACHE_TTL = 300
KNOWLEDGE_EXPIRE_DAYS = 30

# v1.3.0 alias
CACHE_TTL = KNOWLEDGE_CACHE_TTL

# 代码保存默认配置
SAVE = {
    "max_name_length": 40,
    "extension": ".c",
}

# ========== Reference: 外部 HAL/CMSIS/模板文件 ==========
# reference（STM32 HAL 库）移出主仓库，作为外部附属库，路径可注入：
#   - F1 → 环境变量 S_REFERENCE_DIR_F1
#   - F4 → 环境变量 S_REFERENCE_DIR（默认）
#   - G4 → 环境变量 S_REFERENCE_DIR_G4
#   默认相对项目父目录的 reference-stm32f<x>/，clone 到任意位置不指向本机路径。
#   缺库的系列：生成仍可用（Makefile/源码/链接脚本），编译阶段明确 skipped 标注缺库。
_REFERENCE_DIRS: dict[str, Path] = {
    "F1": Path(os.environ.get("S_REFERENCE_DIR_F1", str(PROJECT_ROOT.parent / "reference-stm32f1"))),
    "F4": Path(os.environ.get("S_REFERENCE_DIR", str(PROJECT_ROOT.parent / "reference-stm32f4"))),
    "G4": Path(os.environ.get("S_REFERENCE_DIR_G4", str(PROJECT_ROOT.parent / "reference-stm32g4"))),
}


def reference_dir_for_family(family: str) -> Path:
    """按芯片系列解析 reference HAL 库目录（未知系列回退 F4）。

    智能巡查点：统一委托 chip_gateway 索引（唯一事实源）。
    兼容两种 family 命名：'F4'/'STM32F4xx'/'f4' 均命中 F4。
    """
    from infrastructure.chip_gateway import gateway

    return gateway.reference_dir(family)


REFERENCE_DIR = str(_REFERENCE_DIRS["F4"])
REFERENCE_HAL_INC = str(Path(REFERENCE_DIR) / "hal" / "Inc")
REFERENCE_HAL_SRC = str(Path(REFERENCE_DIR) / "hal" / "Src")
REFERENCE_CMSIS_INC = str(Path(REFERENCE_DIR) / "cmsis" / "Include")
REFERENCE_DEVICE_INC = str(Path(REFERENCE_DIR) / "device" / "Include")
REFERENCE_TEMPLATES = str(Path(REFERENCE_DIR) / "templates")
REFERENCE_TEMPLATES_INC = str(Path(REFERENCE_DIR) / "templates" / "Inc")
REFERENCE_TEMPLATES_SRC = str(Path(REFERENCE_DIR) / "templates" / "Src")

# ═══════════════════════════════════════════
# 外部组件路径（集中化：open-core 拔插式）
# 此前「共享知识库根 / 公共 UI 目录」散落多处各自硬编码默认值，
# 开源后别人 clone 不设环境变量会报路径不存在。
# 统一收敛到这里，各散落点 import config 引用，不再各自写死默认值。
# 这些是「外部组件」（数据库/共享UI），是 open-core 拆分的边界：骨架只留接口，
# 组件可插拔（换路径 / 换实现），核心数据不随仓库走。
# ═══════════════════════════════════════════

# 共享知识库根（组织共享：S 细化产物归入，其他链路共享）
# 默认不写死本机路径，改为「相对项目父目录的 shared_knowledge/」——开源后 clone 到
# 任意位置，不设 AGENT_SHARED_KB 也不会指向作者本机路径。
SHARED_KB_ROOT = Path(os.environ.get(
    "AGENT_SHARED_KB",
    str(PROJECT_ROOT.parent / "shared_knowledge"),
))

# 公共 UI 目录（组织共享：agent-c-chamber/shared/ui，供 /manifest 前端）
SHARED_UI_DIR = Path(os.environ.get(
    "AGENT_SHARED_UI_DIR",
    str(PROJECT_ROOT.parent / "agent-c-chamber" / "shared" / "ui"),
))

# ST 官方 HAL 固件（真编译验证时引用真实 HAL 库，编译成 elf/hex/bin）
# 默认按 CubeMX 标准安装路径取（Path.home()/STM32Cube/Repository/...），
# env STM32_CUBE_FW 可覆盖——开源后别人 clone 不装 ST 固件也能通过 env 指向自己的。
# 这是「外部组件」（ST 官方固件），open-core 边界：骨架只留引用，固件不随仓库走。
STM32_CUBE_FW_DIR = Path(os.environ.get(
    "STM32_CUBE_FW",
    str(Path.home() / "STM32Cube" / "Repository" / "STM32Cube_FW_F4_V1.28.3"),
))
