"""抽象接口契约：各层经 ABC/Protocol 协作，不依赖具体实现。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any, Protocol

from contracts.assessment import AssessorOutput
from contracts.generation import CodeSkillOutput
from contracts.planning import PlannerOutput
from contracts.rule_result import RuleResult


class IAssessor(ABC):
    """评估器接口：评估计划风险。"""

    @abstractmethod
    def assess(self, plan: PlannerOutput) -> AssessorOutput:
        """评估计划风险并返回结果。"""
        ...

    @abstractmethod
    def scan_risky_patterns(self, text: str) -> list[str]:
        """扫描文本中的危险模式。"""
        ...


class IPromptManager(Protocol):
    """Prompt 管理器协议：构建各类提示词（Planner/Generator 依赖）。

    契约强类型：替代 set_prompt_manager(pm: Any) 的 Any。
    agents.prompt_manager.core.PromptManager 通过结构子类型满足本协议。
    """

    def get_beaker(self) -> Any: ...

    def gather_context(self, user_input: str, chip_hint: str | None = None) -> dict[str, Any]: ...

    def build_planner_prompt(self, user_input: str, context: dict[str, Any]) -> str: ...

    def build_code_prompt(self, plan: Any, context: dict[str, Any]) -> str: ...

    def render(self, template_name: str, variables: dict[str, Any]) -> str: ...


class ICodeSkill(ABC):
    """代码生成器接口：根据计划生成代码。"""

    @abstractmethod
    def generate(self, plan: PlannerOutput, user_input: str = "") -> CodeSkillOutput:
        """根据计划生成代码。"""
        ...

    @abstractmethod
    def set_llm(self, client: ILLMClient) -> None:
        """注入 LLM 客户端。"""
        ...

    @abstractmethod
    def set_prompt_manager(self, pm: IPromptManager) -> None:
        """注入 PromptManager。"""
        ...


class IReflector(ABC):
    """审查器接口：审查生成代码质量。"""

    @abstractmethod
    def reflect(
        self,
        scene: str,
        code_artifact: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """审查代码并返回报告。"""
        ...


class IPeripheralRegistry(ABC):
    """外设注册表接口：提供外设关键词、场景、芯片、结构、标准等注册数据。"""

    @abstractmethod
    def get_peripheral_keywords(self) -> dict[str, list[str]]:
        """返回外设关键词映射。"""
        ...

    @abstractmethod
    def get_scene_keywords(self) -> dict[str, list[str]]:
        """返回场景关键词映射。"""
        ...

    @abstractmethod
    def get_chip_keywords(self) -> dict[str, str]:
        """返回芯片关键词映射。"""
        ...

    @abstractmethod
    def get_peripheral_structure(self) -> dict[str, list[str]]:
        """返回外设结构映射。"""
        ...

    @abstractmethod
    def get_peripheral_standards(self) -> dict[str, str]:
        """返回外设标准文件映射。"""
        ...


class IPeripheralDataRepository(ABC):
    """外设运行时数据仓库接口：提供 defaults、constraints、scene 规则。"""

    @abstractmethod
    def defaults(self, peripheral: str) -> dict[str, Any]:
        """返回外设默认参数。"""
        ...

    @abstractmethod
    def constraints(self, peripheral: str) -> dict[str, Any]:
        """返回外设约束。"""
        ...

    @abstractmethod
    def scene_rules(self, peripheral: str) -> list[dict[str, Any]]:
        """返回外设场景路由规则。"""
        ...

    @abstractmethod
    def fallback_scene(self, peripheral: str) -> str:
        """返回外设默认场景。"""
        ...

    @abstractmethod
    def resolve_scene(self, peripheral: str, user_input: str, original_scene: str) -> str:
        """根据用户输入和规则解析最终场景。"""
        ...


class IProjectConfigRepository(ABC):
    """工程生成配置仓库接口：提供 DMA 方向推断、外设实例提取等规则。"""

    @abstractmethod
    def get_dma_direction(self, user_input: str) -> str:
        """根据用户输入推断 DMA 方向。"""
        ...

    @abstractmethod
    def extract_instance(self, peripheral: str, user_input: str) -> str:
        """从用户输入提取外设实例名。"""
        ...

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """返回指定键的配置。"""
        ...

    @abstractmethod
    def reload(self) -> None:
        """重新加载配置。"""
        ...


class IRuleEngine(ABC):
    """规则引擎接口：按场景校验上下文。"""

    @abstractmethod
    def validate(self, scene: str, context: dict[str, Any]) -> list[RuleResult]:
        """返回规则校验结果列表。"""
        ...


class ILLMClient(ABC):
    """LLM 客户端接口：统一聊天与流式接口。"""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], model_type: str = "code",
             temperature: float = 0.2, max_tokens: int = 2048,
             timeout: int | None = None) -> str:
        """非流式对话。"""
        ...

    @abstractmethod
    def chat_stream(self, messages: list[dict[str, str]], model_type: str = "code",
                    temperature: float = 0.2, max_tokens: int = 2048,
                    timeout: int | None = None) -> Iterator[str]:
        """流式对话，返回 token 迭代器。"""
        ...


class IChipProfile(ABC):
    """芯片画像接口：封装芯片能力、约束和骨架数据。

    该接口使 engine 层无需直接依赖 knowledge.loaders.profile_manager。
    """

    @property
    @abstractmethod
    def chip_name(self) -> str:
        ...

    @property
    @abstractmethod
    def core(self) -> str:
        ...

    @property
    @abstractmethod
    def max_clock_mhz(self) -> int:
        ...

    @property
    @abstractmethod
    def flash_kb(self) -> int:
        ...

    @property
    @abstractmethod
    def ram_kb(self) -> int:
        ...

    @property
    @abstractmethod
    def ccm_kb(self) -> int:
        """CCM（紧耦合内存）大小，单位 KB。F407 为 64，F103/F446 无 CCM 为 0。"""
        ...

    @property
    @abstractmethod
    def pin_map(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_init_order(self) -> list[str]:
        ...

    @abstractmethod
    def get_peripheral_clock_bus(self, peripheral: str) -> str:
        ...

    @abstractmethod
    def get_af_pin(self, signal: str) -> str | None:
        ...

    @abstractmethod
    def get_af_number(self, instance: str) -> int | None:
        ...

    @abstractmethod
    def get_af_default_pins(self, instance: str) -> dict[str, str]:
        ...

    @abstractmethod
    def get_default_tim_instance(self, need_advanced: bool = False) -> str:
        ...

    @abstractmethod
    def get_default_uart_instance(self) -> str:
        ...

    @abstractmethod
    def get_default_adc_instance(self) -> str:
        ...

    @abstractmethod
    def get_default_spi_instance(self) -> str:
        ...

    @abstractmethod
    def get_default_i2c_instance(self) -> str:
        ...

    @property
    @abstractmethod
    def error_led_pin(self) -> str:
        ...

    @property
    @abstractmethod
    def clock_tree(self) -> dict[str, Any]:
        """具体芯片时钟树（profile.json 的 clock_tree：pll_m/n/p/q 或 pll_mult、sysclk、flash_latency）。

        供空壳骨架（MxSkeleton）生成 SystemClock_Config 时按具体芯片取时钟配置，
        不再用系列级硬编码默认值。
        """
        ...


class IProfileManager(ABC):
    """芯片画像管理器接口：按芯片名返回 IChipProfile。"""

    @abstractmethod
    def get_profile(self, chip_name: str | None = None) -> IChipProfile:
        ...

    @abstractmethod
    def list_profiles(self) -> list[str]:
        ...

    @abstractmethod
    def set_default(self, chip_name: str) -> None:
        ...


class IMxSkeleton(ABC):
    """骨架模板引擎接口：生成 main.c / main.h / 启动文件 / 链接脚本等。

    该接口使 engine 层无需直接依赖 knowledge.loaders.mx_skeleton。
    """

    @abstractmethod
    def generate_main_h(self, peripheral_headers: list[str] | None = None) -> str:
        ...

    @abstractmethod
    def generate_main_c(
        self,
        peripheral_includes: list[str] | None = None,
        peripheral_handles: list[str] | None = None,
        peripheral_inits: list[str] | None = None,
        peripheral_init_protos: list[str] | None = None,
        main_loop_body: list[str] | None = None,
    ) -> str:
        ...

    @abstractmethod
    def generate_it_c(
        self,
        extern_handles: list[str] | None = None,
        irq_handlers: list[str] | None = None,
    ) -> str:
        ...

    @abstractmethod
    def generate_it_h(self, irq_protos: list[str] | None = None) -> str:
        ...

    @abstractmethod
    def generate_system(self) -> str:
        ...

    @abstractmethod
    def generate_project_info(
        self,
        project_name: str,
        peripherals: list[str],
        peripheral_headers: list[str] | None = None,
        timestamp: str = "",
    ) -> str:
        ...

    @abstractmethod
    def generate_startup_s(self) -> str:
        ...

    @abstractmethod
    def generate_linker_ld(self, chip_name: str | None = None) -> str:
        ...

    @abstractmethod
    def generate_hal_conf_h(self, enabled_modules: list[str] | None = None) -> str:
        ...

    @abstractmethod
    def build_file_tree(self, peripherals: list[str], project_name: str) -> dict[str, str]:
        ...
