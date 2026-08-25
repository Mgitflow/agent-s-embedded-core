"""默认值自动填充层（统一入口）。

念安 2026-08-21「默认值打底 + 需求精准定位 + 差啥补啥」：
用户没提的参数 → 从芯片肖像取默认值自动填，默认值按芯片型号自适应
（官方手册标准值），不再依赖模板写死的通用值。

统一收编之前散落各处的填充，形成单一入口、单一优先级：

    用户显式 params > 识别层（需求文本抠出）> 电气标准值（芯片手册）> 模板 meta default

收编的三处：
  1. 识别层：parse_electrical_reqs（电气高频参数）+ parse_pin_reqs（引脚指定）
  2. 电气填数：fill_electrical_params（用户给了高层参数 → 按芯片手册算底层）
  3. 电气默认打底（本模块新增）：用户没给 → 芯片手册标准值。
     —— ElectricalProfile.calculate_* 早已支持「无要求→标准值」兜底，但生产调度
        fill_electrical_params 没接，导致 PWM/SPI 的 prescaler/period 落在模板写死的
        通用值上（如 pwm_output 写死 8400，实际 F407 标准 1kHz 应为 167；换 F103 全错）。

引脚默认不在此层：引脚占位分配（用户首选 → 肖像候选 → GPIO 池避让）由
PinAllocator 在渲染阶段处理，本层只负责把识别层抠出的引脚参数透传过去。
"""
from __future__ import annotations

import logging
from typing import Any

from knowledge.template_forge.chip_portrait_adapter import DEFAULT_CHIP
from knowledge.template_forge.electrical import (
    fill_electrical_params,
    load_profile,
    parse_electrical_reqs,
)
from knowledge.template_forge.pin_recognition import parse_pin_reqs

_log = logging.getLogger(__name__)

# 舵机标准频率：行业固定 50Hz（20ms 周期），区别于通用 PWM 的 standard_freq_hz(1kHz)。
# electrical.json 的 param_limits 未收录 servo 标准，故此处硬编码为行业基准。
SERVO_STANDARD_HZ = 50.0


class ParameterFiller:
    """默认值自动填充层：识别层 + 电气填数 + 电气默认打底（芯片自适应）。"""

    def __init__(self, chip: str = DEFAULT_CHIP) -> None:
        self._chip = chip

    def fill(
        self,
        template_ids: list[str] | None,
        params: dict[str, Any] | None = None,
        text: str = "",
    ) -> dict[str, Any]:
        """统一填充入口。

        优先级：用户显式 params > 识别层（text 抠出）> 电气标准值（芯片手册）。
        引脚参数（parse_pin_reqs）在此识别并透传，由 PinAllocator 后续消费。

        Args:
            template_ids: 已确定的功能模板清单（决定需要哪些电气默认）。
            params: 用户显式参数（最高优先级，不被覆盖）。
            text: 需求文本（识别层从中抠电气参数 + 引脚）。
        """
        filled: dict[str, Any] = {
            **parse_electrical_reqs(text),
            **parse_pin_reqs(text),
            **(params or {}),
        }
        # 电气填数：用户给了高层参数（freq_hz/baud_rate/clock_hz/target_mhz）→ 算底层
        filled = fill_electrical_params(self._chip, filled)
        # 电气默认打底：用户没给 → 芯片手册标准值（按模板需求，不无脑全填）
        filled = self._fill_electrical_defaults(template_ids or [], filled)
        return filled

    def fill_block(self, peripheral: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """单区块模板的电气默认填充（`_hal` 后缀字段，芯片自适应）。

        与 fill()（functional 层）对称：functional 用 prescaler/period，
        单区块用 prescaler_hal/period_hal（HAL 字段语义），同一套芯片手册标准值。
        修正单区块 meta.json 写死的错值（tim_init prescaler_hal=8400、spi_init
        SPI_BAUDRATEPRESCALER_16），改为按芯片时钟自适应。

        Args:
            peripheral: 外设名（tim/uart/spi/i2c/adc...），对应单区块模板目录。
            params: 用户显式参数（最高优先级，不被覆盖）。
        """
        filled = dict(params or {})
        # RTC 时钟源：板卡画像驱动（不依赖芯片画像，芯片手册缺失也应工作）。
        # 「板卡有没有焊 LSE 晶振」是板卡属性，不是芯片属性——board.json oscillator.lse 是唯一真相源。
        if peripheral == "rtc" and "rtc_clock_setup" not in filled:
            filled["rtc_clock_setup"] = self._resolve_rtc_clock_setup()
        try:
            prof = load_profile(self._chip)
        except FileNotFoundError:
            return filled  # 手册缺失 → 不阻断，meta default 兜底

        if peripheral == "tim":
            # TIM：prescaler_hal/period_hal 依赖 timer 时钟，芯片自适应（标准 1kHz）
            if "prescaler_hal" not in filled and "period_hal" not in filled:
                tim = str(filled.get("instance") or "1")
                cfg = prof.calculate_pwm(None, f"TIM{tim}")
                filled["prescaler_hal"] = cfg.prescaler
                filled["period_hal"] = cfg.period
            # 通道配置（TIM 能力配置，内置单区块）：根据 tim_mode 生成 OC/IC 通道配置代码段，
            # 不靠正则从 functional 样本猜增量（此前 IC 输入捕获的 ConfigChannel 因缺标记整个丢失）。
            if "tim_channel_setup" not in filled:
                filled["tim_channel_setup"] = self._resolve_tim_channel_setup(filled)
        elif peripheral == "spi":
            # SPI：分频依赖 APB 时钟（SPI2/3 挂 APB1，其余挂 APB2），芯片自适应
            if "baudrateprescaler_hal" not in filled:
                inst = str(filled.get("instance") or "1")
                apb = 1 if inst in ("2", "3") else 2
                div = prof.calculate_spi_prescaler(None, apb)
                filled["baudrateprescaler_hal"] = f"SPI_BAUDRATEPRESCALER_{div}"
        elif peripheral == "uart":
            # UART：标准波特率 115200（meta default 已是，此处显式取芯片手册权威值）
            if "baudrate_hal" not in filled:
                filled["baudrate_hal"] = int(
                    prof.param_limits.get("uart", {}).get("standard_baud", 115200)
                )
        elif peripheral == "i2c":
            # I2C：标准时钟 100kHz
            if "clockspeed_hal" not in filled:
                filled["clockspeed_hal"] = prof.calculate_i2c_clock()
        return filled

    def _resolve_rtc_clock_setup(self) -> str:
        """RTC 时钟源配置代码段：板卡画像 oscillator.lse 驱动（材料驱动）。

        板卡焊了 LSE 晶振（board.json oscillator.lse.confirmed=true）→ 使能 LSE +
        RCC_RTCCLKSOURCE_LSE（走时精确 ±20ppm）；无 LSE → LSI（内部 32K，复位默认时钟源，
        无需使能晶振，偏 ~2.3%）。

        「板卡有没有焊晶振」是板卡属性（探索者有、最小系统板未必有），不是芯片属性，
        所以读 board.json 而非 electrical.json。整段代码作为 rtc_clock_setup 参数注入
        rtc_init.tmpl 的 ${rtc_clock_setup} 插槽——能力配置（时钟源）材料化，不在模板写死。
        """
        if self._board_has_lse():
            # CubeMX 标准：HAL_RCCEx_PeriphCLKConfig 封装整个 LSE 使能序列（PWR 时钟 +
            # 备份域访问 + LSE 晶振 + 等就绪 + 选 RTC 时钟源），作为单一调用不被
            # split_init_for_msp 的「时钟使能 → msp」规则拆断（展开式序列里的
            # __HAL_RCC_PWR_CLK_ENABLE 会被拆到 msp，导致 EnableBkUpAccess 提前、顺序错乱）。
            return (
                "    /* 板载 LSE 32.768K 晶振（板卡画像 oscillator.lse）——RTC 走时精确 */\n"
                "    RCC_PeriphCLKInitTypeDef rtc_clk = {0};\n"
                "    rtc_clk.PeriphClockSelection = RCC_PERIPHCLK_RTC;\n"
                "    rtc_clk.RTCClockSelection = RCC_RTCCLKSOURCE_LSE;\n"
                "    if (HAL_RCCEx_PeriphCLKConfig(&rtc_clk) != HAL_OK)\n"
                "    {\n"
                "      Error_Handler();\n"
                "    }\n"
                "    __HAL_RCC_RTC_ENABLE();"
            )
        return "    __HAL_RCC_RTC_ENABLE();  /* LSI 内部 32K（无 LSE 晶振，复位默认时钟源） */"

    def _resolve_tim_channel_setup(self, filled: dict[str, Any]) -> str:
        """TIM 通道配置代码段：根据 tim_mode（derive 反推）生成 OC/IC 通道配置。

        base 定时器无通道；pwm/oc 用 TIM_OC_InitTypeDef + HAL_TIM_PWM_ConfigChannel；
        ic 用 TIM_IC_InitTypeDef + HAL_TIM_IC_ConfigChannel。channel/pulse 由 derive 反推，
        极性缺省走标准值（PWM1/上升沿）。整段作为 tim_channel_setup 参数注入 tim_init.tmpl
        的 ${tim_channel_setup} 插槽——能力配置材料化，不在模板/正则里写死。
        """
        mode = str(filled.get("tim_mode", "base"))
        instance = str(filled.get("instance", "1"))
        channel = str(filled.get("channel", "1"))
        pulse = str(filled.get("pulse", "0"))
        if mode in ("pwm", "oc"):
            return (
                f"    TIM_OC_InitTypeDef tim_oc = {{0}};\n"
                f"    tim_oc.OCMode = TIM_OCMODE_PWM1;\n"
                f"    tim_oc.Pulse = {pulse};\n"
                f"    tim_oc.OCPolarity = TIM_OCPOLARITY_HIGH;\n"
                f"    tim_oc.OCFastMode = TIM_OCFAST_DISABLE;\n"
                f"    if (HAL_TIM_PWM_ConfigChannel(&htim{instance}, &tim_oc, TIM_CHANNEL_{channel}) != HAL_OK)\n"
                f"    {{\n"
                f"        Error_Handler();\n"
                f"    }}"
            )
        if mode == "ic":
            polarity = str(filled.get("ic_polarity", "RISING"))
            return (
                f"    TIM_IC_InitTypeDef tim_ic = {{0}};\n"
                f"    tim_ic.ICPolarity = TIM_INPUTCHANNELPOLARITY_{polarity};\n"
                f"    tim_ic.ICSelection = TIM_ICSELECTION_DIRECTTI;\n"
                f"    tim_ic.ICPrescaler = TIM_ICPSC_DIV1;\n"
                f"    tim_ic.ICFilter = 0;\n"
                f"    if (HAL_TIM_IC_ConfigChannel(&htim{instance}, &tim_ic, TIM_CHANNEL_{channel}) != HAL_OK)\n"
                f"    {{\n"
                f"        Error_Handler();\n"
                f"    }}"
            )
        return ""  # base 定时器：无通道配置

    def _board_has_lse(self) -> bool:
        """板卡是否焊有 LSE 晶振（board.json oscillator.lse）。

        材料驱动：board.json 的 oscillator.lse 是唯一真相源。板卡画像缺失/解析失败
        一律视为无 LSE（fail-closed：不谎称有精确时钟），回退 LSI。
        """
        try:
            import json as _json
            from pathlib import Path as _Path

            from infrastructure.board_resolver import resolve_board_json

            root = _Path(__file__).resolve().parents[2]
            board_path = resolve_board_json(root, self._chip)
            if not board_path:
                return False
            board = _json.loads(board_path.read_text(encoding="utf-8"))
            lse = (board.get("oscillator") or {}).get("lse") or {}
            return lse.get("type") == "crystal" and bool(lse.get("confirmed"))
        except Exception:  # noqa: BLE001 —— 板卡画像读取失败不阻断，回退 LSI
            return False

    # ---- 电气默认打底（芯片自适应） ----

    def _fill_electrical_defaults(
        self, template_ids: list[str], filled: dict[str, Any]
    ) -> dict[str, Any]:
        """按模板前缀补电气默认（只在用户没给时填，取芯片手册标准值）。

        舵机与通用 PWM 分开：舵机固定 50Hz（SERVO_STANDARD_HZ），
        通用 PWM 用 param_limits 的 standard_freq_hz（默认 1kHz）。

        失败安全：芯片电气手册缺失时原样返回（不阻断，模板 meta default 兜底）。
        """
        if not template_ids:
            return filled
        try:
            prof = load_profile(self._chip)
        except FileNotFoundError:
            return filled

        need_servo = any(t.startswith("pwm_servo") for t in template_ids)
        need_pwm = any(t.startswith("pwm") for t in template_ids)
        need_spi = any(t.startswith("spi") for t in template_ids)
        need_uart = any(t.startswith("uart") for t in template_ids)
        need_i2c = any(t.startswith("i2c") for t in template_ids)
        need_adc = any(t.startswith("adc") for t in template_ids)

        # PWM / 舵机：prescaler + period 依赖 timer 时钟，芯片自适应
        if "prescaler" not in filled and "period" not in filled:
            tim = str(filled.get("tim_instance") or "1")
            if need_servo:
                # 舵机：50Hz + 1us 分辨率（period≈20000，脉宽 500~2500us），prescaler 按芯片时钟算
                cfg = prof.calculate_pwm(SERVO_STANDARD_HZ, f"TIM{tim}", resolution=20000)
            elif need_pwm:
                # 通用 PWM：无要求 → param_limits 标准 1kHz（resolution 默认 1000）
                cfg = prof.calculate_pwm(None, f"TIM{tim}")
            else:
                cfg = None
            if cfg is not None:
                filled.setdefault("prescaler", cfg.prescaler)
                filled.setdefault("period", cfg.period)

        # SPI：prescaler 依赖 APB 时钟，芯片自适应
        if need_spi and "spi_prescaler" not in filled:
            filled["spi_prescaler"] = str(prof.calculate_spi_prescaler(None))

        # UART：标准波特率（meta default 已是 115200，此处显式取芯片手册权威值）
        if need_uart and "baud_rate" not in filled:
            filled["baud_rate"] = int(
                prof.param_limits.get("uart", {}).get("standard_baud", 115200)
            )

        # I2C：标准时钟（100kHz）
        if need_i2c and "i2c_speed" not in filled:
            filled["i2c_speed"] = prof.calculate_i2c_clock()

        # ADC 分辨率宏名（系列级：F1=ADC_RESOLUTION12b，F4/G4=ADC_RESOLUTION_12B）
        # 材料驱动：从 family.json 的 adc_resolution_macro 读，不再写死 F4 宏
        if need_adc and "adc_resolution" not in filled:
            from infrastructure.chip_family import get_family

            filled["adc_resolution"] = get_family(self._chip).adc_resolution_macro

        return filled
