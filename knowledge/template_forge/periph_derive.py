"""外设参数反推（6 外设铺开框架）。

职责单一（2026-08-20 解耦）：只做「从 functional 渲染后的 init 代码反推用户可指定关键参数」
（instance + 数值参数），供 BlockAssembler.render_periph_init_from_bundle 做单区块铺开。
单区块渲染/对照校验归 block_assembler，本模块不碰。

反推原则：只反推「用户可指定的关键参数」（instance、baudrate、prescaler/period 等），
其余参数由单区块 meta.json 的 default 兜底（derive_params 机制）。
"""
from __future__ import annotations

import re
from typing import Any


def _derive_uart_params(init: str) -> dict[str, Any]:
    p: dict[str, Any] = {}
    if m := re.search(r"USART(\d+)", init):
        p["instance"] = m.group(1)
    if m := re.search(r"BaudRate\s*=\s*(\d+)", init):
        p["baudrate_hal"] = m.group(1)
    if m := re.search(r"GPIO_AF(\d+)_USART", init):
        p["af_number"] = m.group(1)
    if m := re.search(r"__HAL_RCC_GPIO([A-IK])_CLK_ENABLE", init):
        p["tx_port"] = m.group(1)
    if m := re.search(r"GPIO_PIN_(\d+) \| GPIO_PIN_(\d+)", init):
        p["tx_pin_no"], p["rx_pin_no"] = m.group(1), m.group(2)
    return p


def _derive_tim_params(init: str) -> dict[str, Any]:
    p: dict[str, Any] = {}
    if m := re.search(r"TIM(\d+)", init):
        p["instance"] = m.group(1)
    if m := re.search(r"Prescaler\s*=\s*(\d+)", init):
        p["prescaler_hal"] = m.group(1)
    if m := re.search(r"Period\s*=\s*(\d+)", init):
        p["period_hal"] = m.group(1)
    if m := re.search(r"CounterMode\s*=\s*(TIM_COUNTERMODE_\w+)", init):
        p["countermode_hal"] = m.group(1)
    # 通道配置参数（能力配置架构化 2026-08-24）：通道号 + 占空比，供 fill_block 生成
    # tim_channel_setup 代码段（内置单区块，不靠正则从 functional 猜增量）。
    if m := re.search(r"TIM_CHANNEL_(\d+)", init):
        p["channel"] = m.group(1)
    if m := re.search(r"\.Pulse\s*=\s*(\d+)", init):
        p["pulse"] = m.group(1)
    # 输入捕获极性（IC 能力配置参数，缺省 RISING）
    if m := re.search(r"TIM_INPUTCHANNELPOLARITY_(\w+)", init):
        p["ic_polarity"] = m.group(1)
    # 模式反推：TIM 的 Init 调用按功能模式（Base/PWM/OC/IC）不同，单区块模板只写死 Base，
    # 铺开时须按 functional 的实际模式替换 Init/DeInit 调用（否则 PWM 功能失效）。
    if "HAL_TIM_PWM_Init" in init:
        p["tim_mode"] = "pwm"
    elif "HAL_TIM_IC_Init" in init:
        p["tim_mode"] = "ic"
    elif "HAL_TIM_OC_Init" in init:
        p["tim_mode"] = "oc"
    else:
        p["tim_mode"] = "base"
    return p


def _derive_instance_params(pattern: str) -> Any:
    """通用反推：只提取外设编号（ADC/SPI/I2C/CAN 等用户常只指定编号）。"""

    def _derive(init: str) -> dict[str, Any]:
        p: dict[str, Any] = {}
        if m := re.search(pattern, init):
            p["instance"] = m.group(1)
        return p

    return _derive


def _derive_rtc_params(init: str) -> dict[str, Any]:
    """RTC 反推：单实例（STM32F4 仅一个 RTC），无编号可反推。

    业务参数（时分秒/日期）在 functional init 的 SetTime/SetDate 增量段，
    不在基础 init（单区块 rtc_init.tmpl 只渲染时钟源 + 句柄 + Init），
    故反推为空，电气默认（LSE 时钟源）由 fill_block 板卡画像驱动。
    """
    return {}


def _derive_adc_params(init: str) -> dict[str, Any]:
    """ADC 反推：instance + 采样通道（channel）+ GPIO 引脚（adc_pin/adc_port/adc_pin_no）。

    通道配置（ConfigChannel）是 ADC 固有能力，已内置 adc_init.tmpl——channel 从
    functional 渲染后的 init 反推（ADC_CHANNEL_x），供单区块渲染采样通道。

    GPIO 引脚从 init 的「模拟模式 GPIO 配置段」反推（不是芯片画像）——开发板模板的
    ADC 引脚是定型代码（如探索者电位器 PA5），functional 是渲染后的实际引脚，从模板
    本身反推才能保证「通道」和「引脚」永远一致；芯片画像反推的是「单独芯片的默认引脚」，
    在开发板场景会顶掉定型引脚（念安 2026-08-24 纠正）。
    """
    p: dict[str, Any] = {}
    if m := re.search(r"ADC(\d+)", init):
        p["instance"] = m.group(1)
    if m := re.search(r"ADC_CHANNEL_(\d+)", init):
        p["adc_channel"] = m.group(1)
    # GPIO 引脚：找 GPIO_MODE_ANALOG 前的 GPIO_PIN_x + 后的 HAL_GPIO_Init(GPIOx)，
    # 这是 ADC 采样引脚（模拟模式），不是 LED 等输出引脚。
    m_analog = re.search(r"GPIO_MODE_ANALOG", init)
    if m_analog:
        prefix = init[: m_analog.start()]
        suffix = init[m_analog.start():]
        m_pins = re.findall(r"GPIO_PIN_(\d+)", prefix)
        m_port = re.search(r"HAL_GPIO_Init\(GPIO([A-IK]),", suffix)
        if m_pins:
            p["adc_pin_no"] = m_pins[-1]  # 模拟模式前最近的引脚（ADC 采样脚）
        if m_port:
            p["adc_port"] = m_port.group(1)
        if p.get("adc_port") and p.get("adc_pin_no"):
            p["adc_pin"] = f"P{p['adc_port']}{p['adc_pin_no']}"
    return p


def _derive_can_params(init: str) -> dict[str, Any]:
    """CAN 反推：instance + prescaler（对称面补全，对齐 UART 反推 baudrate / TIM 反推 prescaler）。

    board can_send 的定型波特率（prescaler=6，探索者 875kHz）与 meta default（16）差异大，
    不反推则走铺开后电气值被 meta 覆盖、波特率漂移。反推保留用户/板卡定型值。
    """
    p: dict[str, Any] = {}
    if m := re.search(r"CAN(\d+)", init):
        p["instance"] = m.group(1)
    if m := re.search(r"Prescaler\s*=\s*(\d+)", init):
        p["prescaler_hal"] = m.group(1)
    return p


# 外设 → (derive_fn, init_func fmt, deinit_func fmt, globals fmt)。DMA 是辅助外设（依附 UART/TIM），不独立铺开。
# globals fmt 是标准句柄声明（对齐单区块模板顶部），铺开时替代 functional 的功能特定句柄名。
_PERIPH_DERIVE: dict[str, tuple[Any, str, str, str]] = {
    "UART": (_derive_uart_params, "MX_USART{instance}_UART_Init", "MX_USART{instance}_UART_DeInit", "UART_HandleTypeDef huart{instance};"),
    "TIM": (_derive_tim_params, "MX_TIM{instance}_Init", "MX_TIM{instance}_DeInit", "TIM_HandleTypeDef htim{instance};"),
    "ADC": (_derive_adc_params, "MX_ADC{instance}_Init", "MX_ADC{instance}_DeInit", "ADC_HandleTypeDef hadc{instance};"),
    "SPI": (_derive_instance_params(r"SPI(\d+)"), "MX_SPI{instance}_Init", "MX_SPI{instance}_DeInit", "SPI_HandleTypeDef hspi{instance};"),
    "I2C": (_derive_instance_params(r"I2C(\d+)"), "MX_I2C{instance}_Init", "MX_I2C{instance}_DeInit", "I2C_HandleTypeDef hi2c{instance};"),
    "CAN": (_derive_can_params, "MX_CAN{instance}_Init", "MX_CAN{instance}_DeInit", "CAN_HandleTypeDef hcan{instance};"),
    # RTC 单实例（STM32F4 仅一个 RTC）：init_func 无 {instance} 后缀，globals 无编号。
    # 2026-08-24 纳入铺开——此前 RTC 不在铺开表，走 functional 老路，rtc_init.tmpl 是死模板
    # （且缺 LSE 使能）。纳入后基础 init 走单区块（含板卡画像驱动的 LSE 能力），
    # SetTime/SetDate 业务逻辑作为增量从 functional 保留。
    "RTC": (_derive_rtc_params, "MX_RTC_Init", "MX_RTC_DeInit", "RTC_HandleTypeDef hrtc;"),
}

# ── 增量识别（2026-08-20 念安「增量还是按模板走 + 分层隔离 + 优先级」）──────────
# 铺开时单区块只渲染「基础 init」（时钟+句柄+Init+引脚复用），functional 的「功能增量」
# （NVIC/Receive_IT、OC 配置/PWM_Start 等）不在单区块模板里，须从 functional init 保留。
# 增量识别：按 HAL 调用/配置宏逐行匹配「基础 init 之外的功能代码行」。
# 注意：TIM 的 OC 配置是多行块（声明+赋值+if ConfigChannel），逐行匹配会漏 if 大括号，
#   见 extract_increments 的块级合并逻辑（if 块内行归入增量）。
_INCREMENT_MARKERS: dict[str, list[str]] = {
    "UART": [r"HAL_NVIC_\w+", r"HAL_UART_Receive_IT", r"HAL_UART_Transmit_IT"],
    "TIM": [
        # OC/IC 通道配置（TIM_OC_InitTypeDef/.OCMode/.Pulse/.OCPolarity/.OCFastMode/
        # HAL_TIM_PWM_ConfigChannel/HAL_TIM_IC_ConfigChannel）已内置 tim_init.tmpl
        # 的 ${tim_channel_setup} 插槽（能力配置架构化 2026-08-24），不再靠正则猜增量——
        # 否则 IC 输入捕获的 ConfigChannel 因缺标记整个丢失。
        r"HAL_TIM_PWM_Start", r"HAL_TIM_OC_Start", r"HAL_TIM_IC_Start",
        # 中断增量（2026-08-23 对称修复）：UART/ADC/SPI/I2C/CAN 都有 HAL_NVIC_\w+，
        # 唯独 TIM 漏了 → tim_periodic/tim_input_capture 的 NVIC+Start_IT 被丢，
        # 中断根本不会使能（更谈不上 IRQHandler 生成）。
        r"HAL_NVIC_\w+", r"HAL_TIM_Base_Start_IT",
    ],
    "ADC": [
        r"HAL_NVIC_\w+", r"HAL_ADC_Start", r"HAL_ADC_Start_IT", r"HAL_ADC_Start_DMA",
        r"HAL_DMA_Init", r"__HAL_LINKDMA",
        # HAL_ADC_ConfigChannel 已内置 adc_init.tmpl（能力配置架构化 2026-08-24），
        # 不再靠「从 functional 样本正则猜增量」——否则 functional 漏 ConfigChannel 就丢功能。
    ],
    "SPI": [r"HAL_NVIC_\w+", r"HAL_SPI_Transmit", r"HAL_SPI_Receive"],
    "I2C": [r"HAL_NVIC_\w+", r"HAL_I2C_Master_Transmit", r"HAL_I2C_Master_Receive"],
    "CAN": [
        r"HAL_NVIC_\w+", r"HAL_CAN_Start", r"HAL_CAN_ActivateNotification",
        # HAL_CAN_ConfigFilter / CAN_FilterTypeDef / .Filter* 已内置 can_init.tmpl
        # （能力配置架构化 2026-08-24），不再靠正则从 functional 猜增量。
    ],
    # RTC 增量：时间/日期结构声明 + SetTime/SetDate 业务（基础 init 时钟源已由 rtc_init.tmpl 覆盖，
    # 不在此增量之列）。2026-08-24 纳入铺开后，业务逻辑从 functional 保留。
    "RTC": [
        r"RTC_TimeTypeDef", r"RTC_DateTypeDef", r"HAL_RTC_SetTime", r"HAL_RTC_SetDate",
        r"RTC_WEEKDAY_", r"rtc_sTime\.", r"rtc_sDate\.",
    ],
}

# 变量名标准化：functional 功能特定变量名 → 单区块标准变量名（铺开后基础 init 用标准名，
# 增量段引用的句柄/缓冲须跟着标准化，否则引用未定义变量）。
# 分两类：
#   ① 句柄名（huart/hadc/htim/...）→ 通用正则 standardize_handles（前缀因模板而异：uartirq_/adcscan_/pwm_）
#   ② 功能特定变量（缓冲/配置结构）→ 本表精确映射
_VAR_NAME_MAP: dict[str, list[tuple[str, str]]] = {
    "UART": [(r"uartirq_rx_byte", "rx_byte"), (r"uart_rx_byte", "rx_byte")],
    "TIM": [(r"pwm_oc", "oc_config"), (r"pwm_gpio", "tim_gpio")],
    # RTC 句柄：functional 用 rtc_hrtc（功能特定前缀），单区块标准名 hrtc（无数字，_HANDLE_H_RE
    # 的正则要求 h<periph>\d+ 带编号，匹配不到 RTC，故走精确映射）。业务变量 rtc_sTime/rtc_sDate
    # 增量段内自洽（声明+使用都在增量），不改名。
    "RTC": [(r"\brtc_hrtc\b", "hrtc")],
}

# 句柄名通用标准化：functional 功能特定句柄前缀（uartirq_huart1 / adcscan_hadc1 /
# adcscan_hdma0）→ 标准句柄名（huart1 / hadc1 / hdma0）。句柄是基础 init 和增量共享的，
# 必须统一（否则基础声明 hadc1、增量却引用 adcscan_hadc1 → 未定义）。
_HANDLE_H_RE = re.compile(r"\b\w+_(h(?:uart|usart|tim|adc|dac|spi|i2c|can|dma|gpio|rtc|sd)\d+)\b")
# TIM 特殊：functional 用 pwm_tim1（无 h 前缀），标准名 htim1
_TIM_HANDLE_RE = re.compile(r"\b\w+_tim(\d+)\b")


def standardize_handles(code: str) -> str:
    """句柄变量名标准化：功能特定前缀 → 标准句柄名（h<外设><数字>）。"""
    code = _HANDLE_H_RE.sub(r"\1", code)
    code = _TIM_HANDLE_RE.sub(r"htim\1", code)
    return code


def _standardize_vars(peripheral: str, code: str) -> str:
    """统一变量名标准化：句柄（通用正则）+ 功能特定变量（_VAR_NAME_MAP）。"""
    code = standardize_handles(code)
    for pat, repl in _VAR_NAME_MAP.get(peripheral, []):
        code = re.sub(pat, repl, code)
    return code


def extract_increments(peripheral: str, init: str) -> str:
    """从 functional init 提取「功能增量」段（单区块基础 init 没有的部分），变量名标准化。

    增量识别：逐行按 _INCREMENT_MARKERS[peripheral] 匹配；多行 if 块（如
    `if (HAL_TIM_PWM_ConfigChannel(...) != HAL_OK) { ... }`）把块内行一并归入增量。
    变量名标准化：功能特定变量名（uartirq_huart）→ 标准名（huart），对齐单区块基础 init。

    返回去首尾空白的增量代码段（无增量则返回空串）。
    """
    markers = _INCREMENT_MARKERS.get(peripheral, [])
    if not markers:
        return ""
    lines = init.split("\n")
    inc_lines: list[str] = []
    brace_depth = 0
    pending_block = False  # 增量 if 语句（`if (...) 无 {`）的后续 { } 块待纳入
    for line in lines:
        stripped = line.strip()
        if pending_block or brace_depth > 0:
            # 已在增量 if 块内，块内行（{ / Error_Handler / }）一并归入增量
            inc_lines.append(line)
            brace_depth += stripped.count("{") - stripped.count("}")
            if brace_depth <= 0:
                pending_block = False
            continue
        if any(re.search(m, stripped) for m in markers):
            inc_lines.append(line)
            # if 语句开头（`if (HAL_TIM_PWM_ConfigChannel(...) != HAL_OK)`，行尾无 {）→ 后续块纳入
            if "if (" in stripped and "{" not in stripped:
                pending_block = True
                brace_depth = 0
    if not inc_lines:
        return ""
    inc = "\n".join(inc_lines)
    return _standardize_vars(peripheral, inc).strip("\n")


def extract_increment_globals(peripheral: str, globals_seg: str) -> str:
    """从 functional globals 提取增量变量声明（非主外设句柄），变量名标准化。

    主外设句柄（如 ADC 的 ``ADC_HandleTypeDef``）由单区块 globals_fmt 提供（标准名），跳过；
    辅助外设句柄（如 ADC DMA 扫描的 ``DMA_HandleTypeDef``）和功能变量（UART 中断的
    ``uint8_t rx_byte``）是增量依赖，标准化变量名后保留。
    """
    if not globals_seg:
        return ""
    main_handle = f"{peripheral}_HandleTypeDef"
    keep_lines: list[str] = []
    for line in globals_seg.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if main_handle in stripped:
            continue  # 主外设句柄由单区块提供，跳过
        keep_lines.append(line)
    if not keep_lines:
        return ""
    seg = "\n".join(keep_lines)
    return _standardize_vars(peripheral, seg).strip("\n")


def extract_pin_mux(peripheral: str, init: str) -> str:
    """从 functional init 提取引脚复用块（GPIO_InitTypeDef ... HAL_GPIO_Init），变量名标准化。

    单区块 tim_init（及部分外设）模板缺引脚复用段——基础定时器/外设不需要引脚，
    PWM/IC/OC 等模式才需要。铺开时从 functional 保留引脚复用块，标准化后进 msp
    （复用 split_init_for_msp 的 GPIO 块规则：复合外设引脚复用 → hal_msp.c）。
    """
    lines = init.split("\n")
    mux_lines: list[str] = []
    in_gpio = False
    for line in lines:
        stripped = line.strip()
        if "GPIO_InitTypeDef" in stripped:
            in_gpio = True
        if in_gpio:
            mux_lines.append(line)
            if "HAL_GPIO_Init" in stripped:
                in_gpio = False
    if not mux_lines:
        return ""
    mux = "\n".join(mux_lines)
    return _standardize_vars(peripheral, mux).strip("\n")
