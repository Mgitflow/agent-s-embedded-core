"""电气手册解读 + 参数计算（填数调度）。

念安 2026-08-19 设计：模板占位符 ${xxx} 是「给你看的占位」——没有芯片手册
就填不了真实数据，填不了就不能真用。本模块干两件事：

1. ElectricalProfile —— 加载芯片肖像里的 electrical.json（手册解读出的「定型」
   数据：时钟树 + 引脚电气 + 参数上下限），这些数据由 datasheet/RM 解读，定型后
   不可提前填、用的时候直接查。
2. calculate_* —— 智能调度填数：输入目标参数（如 50Hz PWM），用时钟树 + 上下限
   计算真实配置值（Prescaler/Period/BRR），并校验不越界（防「过度结构」）。

数据来源：knowledge/manuals/<chip>/electrical.json（2026-08-19 手册归知识库分区，
每个芯片/开发板一套专属手册；时钟树权威源是 profile.json，此处只留填数必需字段）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PwmConfig:
    """PWM 定时器配置（填数结果）。"""

    prescaler: int
    period: int
    timer_mhz: int
    actual_hz: float


class ElectricalProfile:
    """芯片电气手册定型数据（时钟树 + 引脚电气 + 参数上下限）。"""

    def __init__(self, chip: str = "stm32f407zgt6", manual_dir: Path | None = None) -> None:
        # 手册资料统一放知识库分区 knowledge/manuals/<chip>/（2026-08-19 念安定：
        # 手册不塞芯片肖像目录，芯片肖像只留结构数据）。manual_dir 可显式传入（测试用）。
        if manual_dir is None:
            from infrastructure.config import manual_dir as _manual_dir

            manual_dir = _manual_dir(chip)
        self.chip = chip
        self.path = manual_dir / "electrical.json"
        if not self.path.exists():
            raise FileNotFoundError(f"芯片电气手册缺失: {self.path}（需先解读手册生成 electrical.json）")
        self.data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))

    # ---- 时钟树 ----
    @property
    def clock_tree(self) -> dict[str, Any]:
        tree = self.data.get("clock_tree", {})
        return tree if isinstance(tree, dict) else {}

    def timer_clock_mhz(self, tim: str) -> int:
        """定时器时钟：TIM1/8 挂 APB2，TIM2-7 挂 APB1（RM0090 时钟树）。"""
        if tim in ("TIM1", "TIM8"):
            return int(self.clock_tree.get("apb2_timer_mhz", 168))
        return int(self.clock_tree.get("apb1_timer_mhz", 84))

    # ---- 工作条件（温度/电压）----
    @property
    def operating_conditions(self) -> dict[str, Any]:
        oc = self.data.get("operating_conditions", {})
        return oc if isinstance(oc, dict) else {}

    # ---- 复位监控（POR/PDR/PVD/BOR）----
    @property
    def reset_supervisor(self) -> dict[str, Any]:
        rs = self.data.get("reset_supervisor", {})
        return rs if isinstance(rs, dict) else {}

    # ---- 内存（flash/sram/ccm/backup + 扇区表）----
    @property
    def memory(self) -> dict[str, Any]:
        mem = self.data.get("memory", {})
        return mem if isinstance(mem, dict) else {}

    def validate_memory_layout(self) -> dict[str, Any]:
        """校验内存分区一致性（防「129=128+64」的坑）。

        念安 8-19「每次检查芯片前完整解读手册，防『129 其实是 128+64』两种模式要分开、
        内部也分开配置」：手册里的总 SRAM 数，实际是多个分区（SRAM1+SRAM2+CCM）的总和，
        且 CCM 仅 CPU 可访问（DMA 不能）。生成 .ld / 分配堆栈时若把不连续分区当连续块用
        （或把 CCM 当普通 SRAM 给 DMA），会 HardFault。

        校验项：
        1. sram_regions 各分区总和 == sram_kb（防「129=128+64」类错配）
        2. sram_regions 起始地址递增（防分区重叠/错位）
        3. 声明 ccm_kb 必须有 ccm_start（防把 CCM 当连续 SRAM 尾部）
        4. ccm_dma_accessible 显式声明（F4/G4 CCM 仅 CPU，DMA 不能访问）

        返回 {"valid": bool, "issues": [...], "memory": {...}}。
        """
        mem = self.memory
        issues: list[str] = []
        regions = mem.get("sram_regions", [])
        if isinstance(regions, list) and regions:
            total = sum(r.get("size_kb", 0) for r in regions if isinstance(r, dict))
            sram_kb = int(mem.get("sram_kb", 0))
            if total != sram_kb:
                issues.append(
                    f"SRAM 分区总和 {total}KB != 声明 sram_kb {sram_kb}KB（129=128+64 类错配）"
                )
            starts = [
                int(r.get("start", "0x0"), 16)
                for r in regions
                if isinstance(r, dict) and r.get("start")
            ]
            if starts and starts != sorted(starts):
                issues.append("SRAM 分区起始地址非递增（可能重叠/错位）")
        if mem.get("ccm_kb"):
            if not mem.get("ccm_start"):
                issues.append("CCM 声明了大小但无起始地址（可能被当连续 SRAM 用）")
            if "ccm_dma_accessible" not in mem:
                issues.append("CCM 未声明 DMA 可访问性（F4/G4 CCM 仅 CPU 可访问，DMA 不能）")
        return {"valid": not issues, "issues": issues, "memory": mem}

    # ---- 看门狗 ----
    @property
    def watchdog(self) -> dict[str, Any]:
        wd = self.data.get("watchdog", {})
        return wd if isinstance(wd, dict) else {}

    # ---- RTC ----
    @property
    def rtc(self) -> dict[str, Any]:
        rt = self.data.get("rtc", {})
        return rt if isinstance(rt, dict) else {}

    # ---- USB ----
    @property
    def usb(self) -> dict[str, Any]:
        u = self.data.get("usb", {})
        return u if isinstance(u, dict) else {}

    # ---- 启动模式 ----
    @property
    def boot(self) -> dict[str, Any]:
        b = self.data.get("boot", {})
        return b if isinstance(b, dict) else {}

    # ---- 引脚电气 ----
    @property
    def pin_electrical(self) -> dict[str, Any]:
        pe = self.data.get("pin_electrical", {})
        return pe if isinstance(pe, dict) else {}

    # ---- 参数上下限 ----
    @property
    def param_limits(self) -> dict[str, Any]:
        pl = self.data.get("param_limits", {})
        return pl if isinstance(pl, dict) else {}

    # ---- 智能调度填数 ----
    def calculate_pwm(self, freq_hz: float | None = None, tim: str = "TIM1", resolution: int = 1000) -> PwmConfig:
        """PWM 频率 → (Prescaler, Period)。period 尽量接近 resolution（占空比分辨率）。

        频率公式：f = timer_clock / (Prescaler+1) / (Period+1)
        无具体要求（freq_hz=None）时，用官方手册标准值（标杆兜底）。
        """
        limits = self.param_limits.get("pwm", {})
        if freq_hz is None:
            freq_hz = float(limits.get("standard_freq_hz", 1000))  # 无要求 → 标准值
        fmax = float(limits.get("freq_max_hz", 42_000_000))
        fmin = float(limits.get("freq_min_hz", 0.02))
        if freq_hz > fmax or freq_hz < fmin:
            raise ValueError(f"PWM 频率 {freq_hz}Hz 越界（{fmin}~{fmax}Hz）")
        timer_hz = self.timer_clock_mhz(tim) * 1_000_000
        prescaler = int(timer_hz / (freq_hz * resolution)) - 1
        if prescaler < 0:
            prescaler = 0
        period = int(timer_hz / (freq_hz * (prescaler + 1))) - 1
        max16 = (1 << int(limits.get("timer_bits", 16))) - 1
        if period > max16:
            period = max16
            prescaler = int(timer_hz / (freq_hz * (period + 1))) - 1
        actual = timer_hz / (prescaler + 1) / (period + 1)
        return PwmConfig(prescaler=prescaler, period=period, timer_mhz=self.timer_clock_mhz(tim), actual_hz=actual)

    def calculate_uart_brr(self, baud: int | None = None, usart_clock_mhz: int | None = None) -> int:
        """UART 波特率 → BRR 寄存器值（BRR = usart_clock / baud）。无要求 → 标准值 115200。

        注：HAL 模板走 ``Init.BaudRate``（直接填波特率，HAL 内部算 BRR），**不用本函数**。
        本函数是「寄存器级编程」（不用 HAL、直接写 BRR 寄存器）才需要的原始计算。
        """
        limits = self.param_limits.get("uart", {})
        if baud is None:
            baud = int(limits.get("standard_baud", 115200))  # 无要求 → 标准值
        if baud > int(limits.get("baud_max", 10_500_000)) or baud < int(limits.get("baud_min", 1200)):
            raise ValueError(f"UART 波特率 {baud} 越界")
        clock = usart_clock_mhz if usart_clock_mhz is not None else int(self.clock_tree.get("apb2_mhz", 84))
        return int(clock * 1_000_000 / baud)

    def check_pin_voltage(self, v: float) -> bool:
        """校验引脚电压是否在 VDD 范围内（防过度结构）。"""
        pe = self.pin_electrical
        return float(pe.get("vdd_min_v", 1.8)) <= v <= float(pe.get("vdd_max_v", 3.6))

    def calculate_i2c_clock(self, freq_hz: int | None = None) -> int:
        """I2C 时钟：无要求 → 标准 100kHz；可选快速 400kHz（超限报错）。"""
        limits = self.param_limits.get("i2c", {})
        if freq_hz is None:
            return int(limits.get("standard_clock_hz", 100000))
        fmax = int(limits.get("clock_max_hz", 400000))
        if freq_hz > fmax:
            raise ValueError(f"I2C 时钟 {freq_hz}Hz 越界（最大 {fmax}Hz）")
        return freq_hz

    def calculate_spi_prescaler(self, target_mhz: float | None = None, apb: int = 2) -> int:
        """SPI 波特率分频：从 prescaler_options 选满足 target_mhz 的最小分频。

        apb=2（SPI1/4/5/6 挂 APB2，F4 最高 42MHz）或 apb=1（SPI2/3 挂 APB1，最高 21MHz）。
        无要求 → 标准 10MHz。
        """
        limits = self.param_limits.get("spi", {})
        apb_max = float(limits.get(f"spi_apb{apb}_max_mhz", 42 if apb == 2 else 21))
        if target_mhz is None:
            target_mhz = float(limits.get("standard_mhz", 10))
        options = [int(o) for o in limits.get("prescaler_options", [2, 4, 8, 16, 32, 64, 128, 256])]
        for presc in options:
            if apb_max / presc <= target_mhz:
                return presc
        return options[-1]

    def calculate_adc_clock_mhz(self) -> float:
        """ADC 最大时钟（MHz）。F4 最高 36MHz（否则精度下降）。"""
        return float(self.param_limits.get("adc", {}).get("adc_clock_max_mhz", 36))

    def to_alignment_table(self) -> dict[str, Any]:
        """电气性能对齐表：把 electrical.json 的 10 大类汇总成扁平查阅表。

        供「写代码时查阅」——不同芯片 electrical.json 数据不同，此表按 chip 自动适配。
        不光是时钟、参数，工作条件/复位监控/内存/看门狗/RTC/USB/启动 全部对齐暴露。
        """
        return {
            "时钟树": self.clock_tree,
            "工作条件": self.operating_conditions,
            "复位监控": self.reset_supervisor,
            "内存": self.memory,
            "看门狗": self.watchdog,
            "RTC": self.rtc,
            "USB": self.usb,
            "启动模式": self.boot,
            "引脚电气": self.pin_electrical,
            "参数上下限": self.param_limits,
        }


# 开发板 → 芯片电气映射（开发板电气性能本质是主控芯片的，复用芯片 electrical.json）
BOARD_TO_CHIP = {
    "atk_explorer_f407": "stm32f407zgt6",  # 正点原子探索者 = F407ZGT6
}


def load_profile(chip: str = "stm32f407zgt6") -> ElectricalProfile:
    """便捷入口：加载芯片电气手册。开发板名自动映射到主控芯片。"""
    resolved = BOARD_TO_CHIP.get(chip, chip)
    return ElectricalProfile(resolved)


# ═══════════════════════════════════════════════════════════════════
# 电气参数命名权威源（念安 8-20「语义成型」）
# 同一个电气概念，三层各叫一个名 —— 此处单一写清对应关系，一眼看透：
#   识别层(用户语义) → functional 模板占位符 → 单区块模板占位符(HAL 字段语义)
# fill_electrical_params 按此表把「识别层语义名」填成「functional 占位符名」；
# 6 外设铺开时再据此映射到「单区块 _hal 名」（functional 退居对照校验）。
# ═══════════════════════════════════════════════════════════════════
REQ_TO_PARAM: dict[str, dict[str, str]] = {
    # UART 波特率：识别 baud_rate → functional baud_rate（同名）→ block baudrate_hal
    "baud_rate": {"functional": "baud_rate", "block": "baudrate_hal"},
    # I2C 时钟：识别 clock_hz → functional i2c_speed → block clockspeed_hal
    "clock_hz": {"functional": "i2c_speed", "block": "clockspeed_hal"},
    # SPI 分频：识别 target_mhz → functional spi_prescaler(enum 字符串) → block baudrateprescaler_hal(完整宏名)
    "target_mhz": {"functional": "spi_prescaler", "block": "baudrateprescaler_hal"},
    # freq_hz（PWM 频率）特殊：一个频率 → prescaler + period 两个值（见 fill_electrical_params），
    # functional 用 prescaler/period，单区块用 prescaler_hal/period_hal。
}


def fill_electrical_params(chip: str, params: dict[str, Any]) -> dict[str, Any]:
    """电气填数调度：识别层语义参数 → 模板占位符参数（有需求→calculate，无需求→不覆盖）。

    念安 8-20「让电气资料去填配置参数」：模板正常用的时候，填充带参数，由电气资料
    算出真实配置值（日常填时钟数，有需求填频率/波特率）。优先级：用户显式给的底层
    参数 > 电气自动算 > 模板默认。

    命名对齐（权威源 REQ_TO_PARAM）：识别层语义名 → functional 占位符名，四条链：
      freq_hz    (PWM 频率)    → calculate_pwm → prescaler / period
      baud_rate  (UART 波特率)  → 直接填（functional 同名占位符，HAL 内部算 BRR）
      clock_hz   (I2C 时钟)    → calculate_i2c_clock → i2c_speed
      target_mhz (SPI 目标频率) → calculate_spi_prescaler → spi_prescaler

    失败安全：芯片电气手册缺失时返回原 params（不阻断模板渲染）。
    """
    filled = dict(params)
    try:
        prof = load_profile(chip)
    except FileNotFoundError:
        return filled
    # PWM：freq_hz → prescaler/period（用户给频率，算分频/周期；无频率则留模板默认）
    if "freq_hz" in filled:
        tim = str(filled.get("tim_instance") or filled.get("tim") or "TIM1")
        cfg = prof.calculate_pwm(float(filled["freq_hz"]), tim)
        filled.setdefault("prescaler", cfg.prescaler)
        filled.setdefault("period", cfg.period)
    # UART：baud_rate → 直接填（functional 同名占位符；HAL 模板走 Init.BaudRate，不填 BRR 寄存器值）
    if "baud_rate" in filled:
        filled["baud_rate"] = int(filled["baud_rate"])
    # I2C：clock_hz → i2c_speed（functional 占位符名；超限报错）
    if "clock_hz" in filled:
        filled["i2c_speed"] = prof.calculate_i2c_clock(int(filled["clock_hz"]))
    # SPI：target_mhz → spi_prescaler（functional enum 字符串，'8' 渲染成 SPI_BAUDRATEPRESCALER_8）
    if "target_mhz" in filled:
        filled["spi_prescaler"] = str(prof.calculate_spi_prescaler(float(filled["target_mhz"])))
    return filled


def parse_electrical_reqs(text: str) -> dict[str, Any]:
    """识别层：从需求文本提取电气高层参数（频率/波特率/时钟）。

    念安 8-20「识别层之后它自动算」：识别层把需求里的「50Hz」「9600 波特率」等
    抠成高层参数，交给 fill_electrical_params 自动算底层配置值。

    识别规则（数字 + 单位/关键词）：
      '做一个 50Hz 呼吸灯'        → {'freq_hz': 50}       (PWM 频率)
      '串口 9600 波特率'          → {'baud_rate': 9600}   (UART 波特率)
      'I2C 400kHz'                → {'clock_hz': 400000}  (I2C 时钟)
      'SPI 10MHz'                 → {'target_mhz': 10}    (SPI 目标频率)

    频率按外设上下文分派：提到 I2C → clock_hz，提到 SPI → target_mhz，否则默认 PWM freq_hz。
    未识别到任何电气参数 → 返回空 dict（不影响后续默认值兜底）。
    """
    reqs: dict[str, Any] = {}
    if not text:
        return reqs
    # 波特率（独立关键词，不混 Hz）
    m = re.search(r"(\d+)\s*(?:波特率|bps|baud)", text, re.I)
    if m:
        reqs["baud_rate"] = int(m.group(1))
    # 频率（数字 + 单位 Hz/kHz/MHz）
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kHz|MHz|Hz)\b", text, re.I)
    if m:
        val = float(m.group(1))
        unit = m.group(2).lower()
        if unit == "khz":
            val *= 1000
        elif unit == "mhz":
            val *= 1_000_000
        # 按外设上下文分派
        if re.search(r"i2c|iic", text, re.I):
            reqs["clock_hz"] = int(val)
        elif re.search(r"spi", text, re.I):
            reqs["target_mhz"] = val / 1_000_000
        else:
            reqs["freq_hz"] = val  # 默认 PWM 频率
    return reqs


if __name__ == "__main__":
    # 演示：50Hz 舵机 PWM → 填出真实 Prescaler/Period
    prof = ElectricalProfile()
    cfg = prof.calculate_pwm(50.0, "TIM1")
    print(f"50Hz PWM (TIM1 @{cfg.timer_mhz}MHz) → Prescaler={cfg.prescaler}, Period={cfg.period}, 实际={cfg.actual_hz:.3f}Hz")
    cfg2 = prof.calculate_pwm(50.0, "TIM3")
    print(f"50Hz PWM (TIM3 @{cfg2.timer_mhz}MHz) → Prescaler={cfg2.prescaler}, Period={cfg2.period}, 实际={cfg2.actual_hz:.3f}Hz")
    print(f"115200 波特率 BRR = {prof.calculate_uart_brr(115200)}")
    print(f"引脚 3.3V 合法 = {prof.check_pin_voltage(3.3)}, 5.0V 合法 = {prof.check_pin_voltage(5.0)}")
