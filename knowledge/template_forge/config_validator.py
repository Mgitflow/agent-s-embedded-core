"""生成前配置校验：对标 CubeMX 的必填/范围/枚举/引脚存在性/实例合法性五类规则，规则表驱动、独立可组合，返回 violations 由调用方决定。"""

from __future__ import annotations

import logging
import re
from typing import Any

from knowledge.template_forge.chip_portrait_adapter import DEFAULT_CHIP, ChipPortraitAdapter

_log = logging.getLogger(__name__)

# ── 参数约束规则表（新约束加这里，校验器逻辑不动） ──
# 键 = 模板 id；值 = 参数名 → 约束（min/max 数值范围 / enum 枚举集合）
PARAM_RULES: dict[str, dict[str, dict[str, Any]]] = {
    "led_blink": {
        "led_port": {"enum": list("ABCDEFGHIK")},
        "led_pin": {"min": 0, "max": 15},
        "delay_ms": {"min": 1, "max": 60000},
    },
    "button_read": {
        "btn_port": {"enum": list("ABCDEFGHIK")},
        "btn_pin": {"min": 0, "max": 15},
        "debounce_ms": {"min": 1, "max": 10000},
    },
    "gpio_exti": {
        "exti_port": {"enum": list("ABCDEFGHIK")},
        "exti_pin": {"min": 0, "max": 15},
    },
    "pwm_output": {
        "tim_instance": {"enum": ["1", "2", "3", "4", "5", "8", "9", "10", "11", "12", "13", "14"]},
        "channel": {"enum": ["1", "2", "3", "4"]},
        "period": {"min": 1, "max": 65535},
        "prescaler": {"min": 0, "max": 65535},
        "pulse": {"min": 0, "max": 65535},
    },
    "pwm_servo": {
        "tim_instance": {"enum": ["1", "2", "3", "4", "5", "8"]},
        "channel": {"enum": ["1", "2", "3", "4"]},
        "period": {"min": 1, "max": 65535},
    },
    "tim_periodic": {
        "tim_instance": {"enum": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14"]},
        "period": {"min": 1, "max": 65535},
        "prescaler": {"min": 0, "max": 65535},
    },
    "tim_input_capture": {
        "tim_instance": {"enum": ["1", "2", "3", "4", "5", "8"]},
        "channel": {"enum": ["1", "2", "3", "4"]},
    },
    "uart_print": {
        "uart_instance": {"enum": ["1", "2", "3", "4", "5", "6"]},
        "baud_rate": {"min": 1200, "max": 921600},
        "print_timeout": {"min": 1, "max": 60000},
        "print_interval": {"min": 0, "max": 60000},
    },
    "uart_interrupt": {
        "uart_instance": {"enum": ["1", "2", "3", "4", "5", "6"]},
        "baud_rate": {"min": 1200, "max": 921600},
        "irq_priority": {"min": 0, "max": 15},
    },
    "uart_dma": {
        "uart_instance": {"enum": ["1", "2", "3", "4", "5", "6"]},
        "baud_rate": {"min": 1200, "max": 921600},
        "dma_stream": {"min": 0, "max": 7},
    },
    "spi_master": {
        "spi_instance": {"enum": ["1", "2", "3"]},
        "spi_prescaler": {"enum": ["2", "4", "8", "16", "32", "64", "128", "256"]},
        "spi_timeout": {"min": 1, "max": 60000},
        "spi_interval": {"min": 0, "max": 60000},
    },
    "i2c_scan": {
        "i2c_instance": {"enum": ["1", "2", "3"]},
        "i2c_speed": {"enum": ["100000", "400000"]},
        "scan_timeout": {"min": 1, "max": 60000},
    },
    "i2c_sensor": {
        "i2c_instance": {"enum": ["1", "2", "3"]},
        "i2c_speed": {"enum": ["100000", "400000"]},
    },
    "adc_read": {
        "adc_instance": {"enum": ["1", "2", "3"]},
        "adc_channel": {"min": 0, "max": 15},
        "adc_timeout": {"min": 1, "max": 60000},
        "adc_interval": {"min": 0, "max": 60000},
    },
    "adc_dma_scan": {
        "adc_instance": {"enum": ["1", "2", "3"]},
        "channel_count": {"min": 1, "max": 16},
        "dma_stream": {"min": 0, "max": 7},
    },
    "dac_output": {
        "dac_instance": {"enum": ["1"]},
        "channel": {"enum": ["1", "2"]},
        "dac_max": {"min": 1, "max": 4095},
    },
    "dma_mem_copy": {
        "dma_controller": {"enum": ["1", "2"]},
        "dma_stream": {"min": 0, "max": 7},
        "copy_len": {"min": 1, "max": 65535},
    },
    "can_communication": {
        "can_instance": {"enum": ["1", "2"]},
        "can_prescaler": {"min": 1, "max": 1024},
        "can_interval": {"min": 0, "max": 60000},
    },
    "sd_card": {
        "sd_clock_div": {"enum": ["2", "4", "8", "16", "32", "64", "128", "256"]},
        "sd_timeout": {"min": 1, "max": 60000},
    },
    "iwdg_refresh": {
        "iwdg_prescaler": {"enum": ["4", "8", "16", "32", "64", "128", "256"]},
        "iwdg_period_ms": {"min": 1, "max": 32000},
    },
    "wwdg_refresh": {
        "wwdg_prescaler": {"enum": ["1", "2", "4", "8"]},
        "wwdg_period_ms": {"min": 1, "max": 60000},
    },
    "rng_random": {"rng_interval": {"min": 0, "max": 60000}},
    "crc_compute": {"crc_len": {"min": 1, "max": 65535}},
    "system_reset": {"iwdg_reload": {"min": 1, "max": 4095}},
    "rtc_calendar": {"rtc_year": {"min": 2000, "max": 2099}},
}

# ── 类型推断兜底（参数名语义 → 自动约束） ──
_SUFFIX_RULES: list[tuple[str, dict[str, Any]]] = [
    (r"_ms$", {"min": 1, "max": 60000}),
    (r"_timeout$", {"min": 1, "max": 60000}),
    (r"_interval$", {"min": 0, "max": 60000}),
    (r"_rate$", {"min": 1200, "max": 921600}),
    (r"_prescaler$", {"min": 0, "max": 65535}),
    (r"_period$", {"min": 1, "max": 65535}),
    (r"_reload$", {"min": 1, "max": 4095}),
]


class ConfigValidator:
    """生成前配置校验器（对照 CubeMX 审查机制：必填/范围/枚举/引脚）。"""

    def __init__(
        self, adapter: ChipPortraitAdapter | None = None, chip: str | None = None
    ) -> None:
        self._adapter = adapter or ChipPortraitAdapter(chip=chip or DEFAULT_CHIP)

    # ---- 主入口 ----

    def validate(self, template_id: str, params: dict[str, Any]) -> list[str]:
        """校验模板参数。返回违规列表（空 = 通过）。

        Returns:
            ["必填缺失 led_pin", "led_pin 值 20 超出范围 [0,15]", ...]
        """
        violations: list[str] = []
        violations.extend(self._check_required(template_id, params))
        violations.extend(self._check_rules(template_id, params))
        violations.extend(self._check_pins(params))
        return violations

    # ---- ① 必填 ----

    def _check_required(self, template_id: str, params: dict[str, Any]) -> list[str]:
        from knowledge.template_forge.functional_templates import FunctionalTemplateStore

        tpl = FunctionalTemplateStore().get(template_id)
        if tpl is None:
            return [f"模板不存在: {template_id}"]
        out: list[str] = []
        for key, spec in (tpl.get("params") or {}).items():
            # required 且无默认值 → 用户必须给；有默认值 → 渲染兜底不算缺失
            if (
                isinstance(spec, dict)
                and spec.get("required")
                and "default" not in spec
                and key not in params
            ):
                out.append(f"必填参数缺失: {key}")
        return out

    # ---- ②③ 范围/枚举（规则表 + 类型推断） ----

    def _check_rules(self, template_id: str, params: dict[str, Any]) -> list[str]:
        rules = PARAM_RULES.get(template_id, {})
        out: list[str] = []
        for key, value in params.items():
            if value is None or value == "":
                continue
            rule = rules.get(key) or self._infer_rule(key)
            if not rule:
                continue
            # 枚举
            enum = rule.get("enum")
            if enum and str(value) not in [str(e) for e in enum]:
                out.append(f"{key} 值 {value} 非法，允许 {enum}")
            # 范围（数值型）
            if "min" in rule or "max" in rule:
                try:
                    num = float(value)
                except (TypeError, ValueError):
                    continue
                lo, hi = rule.get("min", float("-inf")), rule.get("max", float("inf"))
                if num < lo or num > hi:
                    out.append(f"{key} 值 {value} 超出范围 [{lo},{hi}]")
        return out

    @staticmethod
    def _infer_rule(key: str) -> dict[str, Any] | None:
        for pattern, rule in _SUFFIX_RULES:
            if re.search(pattern, key):
                return rule
        return None

    # ---- ④ 引脚存在性 ----

    def _check_pins(self, params: dict[str, Any]) -> list[str]:
        """引脚存在性检查。芯片无 pin_map（如探索者 ZGT6 只有 profile）→ 跳过，
        不能因数据缺失误杀（失败安全）。"""
        if not self._adapter.has_pin_data():
            return []
        out: list[str] = []
        for key, value in params.items():
            if key.endswith("_pin") and isinstance(value, str) and value.upper().startswith("P"):
                pin = value.upper()
                if self._adapter.get_pin_info(pin) is None:
                    out.append(f"{key} 引脚 {pin} 不存在于芯片（pin_map 无此引脚）")
        return out

    # ---- ⑤ 实例校验 ----

    def validate_instance(self, peripheral: str, instance: str) -> bool:
        """外设实例是否芯片支持（USART1-6/TIM1-14 等）。"""
        return self._adapter.supports_peripheral(f"{peripheral}{instance}")


def validate_template_params(
    template_id: str, params: dict[str, Any], chip: str = DEFAULT_CHIP
) -> list[str]:
    """便捷入口：配置校验。"""
    return ConfigValidator(chip=chip).validate(template_id, params)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    v = ConfigValidator()
    # 正常
    print("led_blink 正常:", v.validate("led_blink", {"led_pin": "5", "led_port": "A"}))
    # 必填缺失
    print("led_blink 缺 led_pin:", v.validate("led_blink", {"led_port": "A"}))
    # 范围越界
    print("led_blink pin=20:", v.validate("led_blink", {"led_pin": "20", "led_port": "A"}))
    print("led_blink port=Z:", v.validate("led_blink", {"led_pin": "5", "led_port": "Z"}))
    # 引脚不存在
    print("uart tx=PA99:", v.validate("uart_print", {"tx_pin": "PA99"}))
    # 枚举
    print("uart instance=9:", v.validate("uart_print", {"uart_instance": "9"}))
