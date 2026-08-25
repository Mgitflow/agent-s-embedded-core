"""单区块拼装器（Block Assembler）。

念安 2026-08-19「定位掰正」的地基：

    模板三层定位：
      空壳模板  = 芯片骨架（不参与拼装，只做工程空壳）
      整体模板  = functional/*.json（功能级，含业务逻辑 loop）
                  → 定位改为「证明样本」：拼装结果和它对照校验一致性
      单区块模板 = <外设>/<peri>_<init|config|interrupt>.tmpl（外设四段：
                  定义→初始化→配置→收工）
                  → 定位「拼装主体」：真正拿来拼装的最小单元

    一个功能 = 单区块（外设初始化四段）+ 简单逻辑（业务，二期补）。
    本模块先落地「单区块=初始化拼装主体」+「对照校验（functional=证明样本）」。

对比现状（掰正前）：FunctionalAssembler 直接用 functional/*.json 整体拼装
（它才是生成主体），单区块 .tmpl 只做单外设渲染 fallback。掰正后反过来：
拼装走单区块，functional 退居对照样本。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from knowledge.template_forge.chip_portrait_adapter import DEFAULT_CHIP
from knowledge.template_forge.template_utils import derive_params, fill

FORGE_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "template_forge" / "forge_templates"

# TIM 模式 → (Init 调用, DeInit 调用)。单区块 tim_init.tmpl 只写死 Base_Init，铺开时按
# functional 反推的功能模式替换（PWM 需 HAL_TIM_PWM_Init，否则 PWM 功能失效）。
_TIM_MODE_INIT: dict[str, tuple[str, str]] = {
    "base": ("HAL_TIM_Base_Init", "HAL_TIM_Base_DeInit"),
    "pwm": ("HAL_TIM_PWM_Init", "HAL_TIM_PWM_DeInit"),
    "oc": ("HAL_TIM_OC_Init", "HAL_TIM_OC_DeInit"),
    "ic": ("HAL_TIM_IC_Init", "HAL_TIM_IC_DeInit"),
}

# 6 外设对照校验（functional = 证明样本）的关键 HAL 调用语义点。
# 铺开（单区块基础 + functional 增量）后，这些关键 HAL 调用必须和 functional 样本一致，
# 否则就是「丢功能」——对照校验据此锁死铺开不漂移。
_KEY_HAL_CALLS: dict[str, list[str]] = {
    "UART": ["HAL_UART_Init", "HAL_NVIC_EnableIRQ", "HAL_UART_Receive_IT"],
    "TIM": ["HAL_TIM_PWM_Init", "HAL_TIM_PWM_ConfigChannel", "HAL_TIM_PWM_Start"],
    "ADC": ["HAL_ADC_Init", "HAL_ADC_ConfigChannel", "HAL_DMA_Init", "HAL_ADC_Start_DMA"],
    "SPI": ["HAL_SPI_Init"],
    "I2C": ["HAL_I2C_Init"],
    "CAN": ["HAL_CAN_Init", "HAL_CAN_ConfigFilter", "HAL_CAN_Start"],
}

# 外设 → (代表 functional 模板 id, 渲染参数)。对照校验的「证明样本」侧。
# 选含功能增量的模板（UART 中断 / TIM PWM / ADC DMA 扫描 / CAN 通信），这样增量不丢才测得出来。
_PERIPH_SAMPLE: dict[str, tuple[str, dict[str, Any]]] = {
    "UART": ("uart_interrupt", {"uart_instance": "1", "baud_rate": "9600", "irq_priority": "2"}),
    "TIM": ("pwm_output", {"tim_instance": "1", "prescaler": "3359", "period": "999", "pulse": "500", "channel": "1"}),
    "ADC": ("adc_read", {"adc_instance": "1"}),
    "SPI": ("spi_master", {"spi_instance": "1"}),
    "I2C": ("i2c_scan", {"i2c_instance": "1"}),
    "CAN": ("can_communication", {"can_instance": "1"}),
}


class BlockAssembler:
    """单区块拼装器：外设四段渲染 + 与 functional 对照校验。"""

    # ---- 单区块渲染（拼装主体）----

    def render_block(self, peripheral: str, scene: str = "init", params: dict[str, Any] | None = None, chip: str = DEFAULT_CHIP) -> str:
        """渲染某外设的单个区块（init/config/interrupt）。

        peripheral: gpio/tim/uart/adc/spi/i2c/can/dma/crc/iwdg/wwdg/rng/rtc/sdio
        scene:      init/config/interrupt（三件套）
        chip:       芯片型号（电气默认按芯片时钟自适应，修正 meta 写死的 prescaler/DIV16）
        """
        tid = f"{peripheral}_{scene}"
        tmpl_path = FORGE_DIR / peripheral / f"{tid}.tmpl"
        if not tmpl_path.exists():
            raise FileNotFoundError(f"单区块模板缺失: {tmpl_path}")
        tmpl = tmpl_path.read_text(encoding="utf-8")
        # 芯片自适应电气默认（先于 meta default，覆盖写死的 prescaler_hal=8400 / DIV16）
        from knowledge.template_forge.param_filler import ParameterFiller

        filled = ParameterFiller(chip).fill_block(peripheral, params or {})
        p = derive_params(tid, filled)
        code = fill(tmpl, p)
        if code is None:
            raise ValueError(f"单区块渲染失败: {tid}")
        return code

    def render_init(self, peripheral: str, params: dict[str, Any] | None = None, chip: str = DEFAULT_CHIP) -> str:
        """渲染外设初始化段（四段之首，拼装主体核心）。"""
        return self.render_block(peripheral, "init", params, chip)

    # ---- 改调用：functional bundle → 单区块 port 级函数（定位掰正核心）----

    @staticmethod
    def _extract_func(code: str, func_name: str) -> str:
        """从完整函数代码里提取某函数的函数体（含大括号内容，不含签名与壳）。

        用大括号配平（处理嵌套），稳健提取 MX_GPIO_Init 这类多函数模板的单一函数体。
        """
        idx = code.index(func_name)
        brace_start = code.index("{", idx)
        depth = 0
        for i in range(brace_start, len(code)):
            if code[i] == "{":
                depth += 1
            elif code[i] == "}":
                depth -= 1
                if depth == 0:
                    return code[brace_start + 1 : i].strip("\n")
        return ""

    def render_gpio_init_from_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        """定位掰正核心：从 functional 的 GPIO bundle 反推参数 → 单区块渲染外设级函数。

        改调用前：functional init 段（led_gpio_init 变量名）+ MX_GPIO_Init（外设级，不带 port）。
        改调用后：单区块 gpio_init（GPIO_InitStruct 变量名）+ MX_GPIO_Init（外设级，符合
        _common/manifest.yaml 的 hal_conventions.naming 权威源，多端口同名合并）。

        返回：
          {"init_func": "MX_GPIO_Init", "init_body": "...",   # 外设 .c 函数体（含手动调 HAL_GPIO_MspInit）
           "deinit_func": "MX_GPIO_DeInit", "deinit_body": "...",
           "msp_code": "__HAL_RCC_GPIOx_CLK_ENABLE();"}       # hal_msp.c 虚拟 HAL_GPIO_MspInit 的时钟
        """
        init = str(bundle.get("init", "") or "")
        # 开放式扫描（2026-08-23 念安「堆叠逻辑」）：GPIO 初始化是「可多个」的材料，不限条数——
        # 扫描监测所有 HAL_GPIO_Init 段 → 逐段适配渲染 → 过滤堆叠，直到扫完。
        # 单端口/多端口走同一条路径，不再「一对一/枚举」分支（原来只反推第一个端口，漏掉后面的）。
        segments = self._parse_gpio_ports(init)
        if not segments:
            # 兜底：init 无 HAL_GPIO_Init（异常/空 init），默认单端口 GPIOF/PF9（不静默丢）
            segments = [{
                "port": "F", "pin_mask": "GPIO_PIN_9", "mode": "GPIO_MODE_OUTPUT_PP",
                "pull": "GPIO_NOPULL", "speed": "GPIO_SPEED_FREQ_LOW", "init_level": "",
            }]
        return self._render_multi_port_gpio(segments, init)

    @staticmethod
    def _parse_gpio_ports(init: str) -> list[dict[str, str]]:
        """从 init 代码解析所有 GPIO 端口配置段（支持一个 bundle 多个端口）。

        按 HAL_GPIO_Init(GPIOx, 位置分段，每段提取 port/pin_mask/mode/pull/speed +
        初始 WritePin 电平。返回 [{"port","pin_mask","mode","pull","speed","init_level"}, ...]。
        """
        ports: list[dict[str, str]] = []
        init_calls = list(re.finditer(r"HAL_GPIO_Init\(GPIO([A-IK]),", init))
        if not init_calls:
            return ports
        for i, m in enumerate(init_calls):
            seg_start = init_calls[i - 1].end() if i > 0 else 0
            seg = init[seg_start:m.start()]
            port = m.group(1)
            # 变量名不固定（board_simple 用 GPIO_InitStruct，functional 用 led_gpio_init 等），
            # 用「.Pin = ...」通配任意变量名（架构层只认「初始化段」，不绑变量名）
            pm = re.search(r"\.Pin\s*=\s*([^;]+);", seg)
            pin_mask = pm.group(1).strip() if pm else "GPIO_PIN_0"
            mm = re.search(r"Mode\s*=\s*(GPIO_MODE_\w+)", seg)
            mode = mm.group(1) if mm else "GPIO_MODE_OUTPUT_PP"
            plm = re.search(r"Pull\s*=\s*(GPIO_\w+)", seg)
            pull = plm.group(1) if plm else "GPIO_NOPULL"
            sm = re.search(r"Speed\s*=\s*(GPIO_SPEED_FREQ_\w+)", seg)
            speed = sm.group(1) if sm else "GPIO_SPEED_FREQ_LOW"
            seg_after = init[m.end():init_calls[i + 1].start() if i + 1 < len(init_calls) else len(init)]
            wm = re.search(r"HAL_GPIO_WritePin\(GPIO" + port + r",[^,]+,\s*(GPIO_PIN_\w+)\)", seg_after)
            init_level = wm.group(1) if wm else ""
            ports.append({
                "port": port, "pin_mask": pin_mask, "mode": mode,
                "pull": pull, "speed": speed, "init_level": init_level,
            })
        return ports

    @staticmethod
    def _render_multi_port_gpio(ports: list[dict[str, str]], init: str) -> dict[str, Any]:
        """GPIO 初始化段 → MX_GPIO_Init（开放式：不限段数，单/多端口统一走这里）。

        架构层堆叠逻辑（2026-08-23 念安）：扫描出的每个端口段依次适配成标准
        GPIO_InitStruct 配置 + HAL_GPIO_Init，时钟使能拆进 msp_code，初始 WritePin
        原样保留。不写死端口数——1 个、N 个都是同一条循环。
        """
        body_lines = ["    GPIO_InitTypeDef GPIO_InitStruct = {0};"]
        deinit_lines: list[str] = []
        msp_lines: list[str] = []
        for p in ports:
            msp_lines.append(f"  __HAL_RCC_GPIO{p['port']}_CLK_ENABLE();")
            body_lines.append(f"    HAL_GPIO_MspInit(GPIO{p['port']});")
            body_lines.append(f"    GPIO_InitStruct.Pin = {p['pin_mask']};")
            body_lines.append(f"    GPIO_InitStruct.Mode = {p['mode']};")
            body_lines.append(f"    GPIO_InitStruct.Pull = {p['pull']};")
            body_lines.append(f"    GPIO_InitStruct.Speed = {p['speed']};")
            body_lines.append(f"    HAL_GPIO_Init(GPIO{p['port']}, &GPIO_InitStruct);")
            if p.get("init_level"):
                body_lines.append(
                    f"    HAL_GPIO_WritePin(GPIO{p['port']}, {p['pin_mask']}, {p['init_level']});"
                )
            deinit_lines.append(f"    HAL_GPIO_DeInit(GPIO{p['port']}, {p['pin_mask']});")
        # EXTI 中断增量（多端口也可能有中断模式，NVIC 行原样保留）
        increments = ""
        inc_lines = [ln for ln in init.split("\n") if re.search(r"HAL_NVIC_\w+", ln.strip())]
        if inc_lines:
            increments = "\n".join(inc_lines).strip("\n")
        return {
            "init_func": "MX_GPIO_Init",
            "init_body": "\n".join(body_lines),
            "deinit_func": "MX_GPIO_DeInit",
            "deinit_body": "\n".join(deinit_lines),
            "msp_code": "\n".join(msp_lines),
            "increments": increments,
        }

    # ---- 对照校验（functional = 证明样本）----

    @staticmethod
    def _gpio_semantics(code: str) -> dict[str, Any]:
        """从一段 GPIO 初始化代码里提取关键语义点（端口/引脚/模式/上下拉/速度/Init）。

        单区块和 functional 的代码文本不同（变量名/函数名），但语义点应该一致——
        这正是「对照校验」的依据：拼装结果（单区块）和证明样本（functional）语义对齐。
        """
        sem: dict[str, Any] = {}
        # port 从 HAL_GPIO_Init(GPIOx, 或虚拟 MspInit 的 HAL_GPIO_MspInit(GPIOx) 提取
        # （2026-08-20 虚拟 MspInit 后，时钟使能 __HAL_RCC_GPIOx_CLK_ENABLE 已拆进 msp，不再在 init 体）
        m = re.search(r"HAL_GPIO_Init\(GPIO([A-IK]),", code) or re.search(
            r"HAL_GPIO_MspInit\(GPIO([A-IK])\)", code
        )
        sem["port"] = m.group(1) if m else None
        m = re.search(r"GPIO_PIN_(\d+)", code)
        sem["pin"] = m.group(1) if m else None
        m = re.search(r"Mode\s*=\s*(GPIO_MODE_\w+)", code)
        sem["mode"] = m.group(1) if m else None
        m = re.search(r"Pull\s*=\s*(GPIO_\w+)", code)
        sem["pull"] = m.group(1) if m else None
        m = re.search(r"Speed\s*=\s*(GPIO_SPEED_FREQ_\w+)", code)
        sem["speed"] = m.group(1) if m else None
        sem["has_init"] = "HAL_GPIO_Init" in code
        sem["has_deinit"] = "HAL_GPIO_DeInit" in code
        return sem

    def verify_gpio_init(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """对照校验：单区块 gpio_init 渲染 vs functional led_blink 的 init 段。

        返回 {"match": bool, "block": {...}, "sample": {...}, "diff": [...]}。
        这是「整体=证明样本、单区块=拼装主体」的最小闭环：拼装结果和样本语义对齐。
        """
        # 拼装主体：单区块 gpio_init（参数化）
        block_params = {
            "port": (params or {}).get("port", "F"),
            "pin_mask": (params or {}).get("pin_mask", "GPIO_PIN_9"),
        }
        block_code = self.render_init("gpio", block_params)
        block_sem = self._gpio_semantics(block_code)

        # 证明样本：functional led_blink（led_port/led_pin）
        from knowledge.template_forge.functional_templates import FunctionalTemplateStore

        store = FunctionalTemplateStore()
        sample_params = {
            "led_port": (params or {}).get("led_port", "F"),
            "led_pin": (params or {}).get("led_pin", "9"),
            "delay_ms": (params or {}).get("delay_ms", "500"),
        }
        rendered = store.render("led_blink", sample_params)
        sample_code = rendered.get("init", "")
        sample_sem = self._gpio_semantics(sample_code)

        diff = []
        for key in ("port", "pin", "mode", "pull", "speed", "has_init"):
            if block_sem.get(key) != sample_sem.get(key):
                diff.append(f"{key}: 单区块={block_sem.get(key)} vs 样本={sample_sem.get(key)}")

        return {
            "match": not diff,
            "block": block_sem,
            "sample": sample_sem,
            "diff": diff,
        }

    @staticmethod
    def _periph_semantics(peripheral: str, code: str) -> dict[str, Any]:
        """从一段外设 init 代码提取关键语义点（关键 HAL 调用是否出现）。

        铺开侧和 functional 样本的代码文本不同（变量名/函数名/时钟位置），但关键 HAL
        调用（功能完整性）必须一致——这是 6 外设对照校验的依据。
        """
        sem: dict[str, Any] = {}
        for call in _KEY_HAL_CALLS.get(peripheral, []):
            sem[call] = call in code
        return sem

    def verify_periph_spread(self, peripheral: str) -> dict[str, Any]:
        """对照校验：铺开结果（单区块基础 + functional 增量）vs functional 样本语义一致。

        铺开侧 = render_periph_init_from_bundle 的 init_body（基础）+ increments（增量）
        + msp_code（时钟/引脚复用）合并；样本侧 = functional 模板的 init 段。
        关键 HAL 调用集合必须一致，否则铺开「丢功能」（增量保留/模式替换失效）。

        返回 {"match": bool, "spread": {...}, "sample": {...}, "diff": [...]}。
        """
        sample_entry = _PERIPH_SAMPLE.get(peripheral)
        if sample_entry is None:
            return {"match": True, "spread": {}, "sample": {}, "diff": []}
        sample_tid, sample_params = sample_entry
        from knowledge.template_forge.functional_templates import FunctionalTemplateStore

        store = FunctionalTemplateStore()
        rendered = store.render(sample_tid, sample_params)
        bundle = dict(rendered)
        bundle["peripheral"] = peripheral
        br = self.render_periph_init_from_bundle(peripheral, bundle)
        if br is None:
            return {"match": True, "spread": {}, "sample": {}, "diff": []}
        # 铺开侧完整代码：基础 init + 增量 + msp（时钟/引脚复用）
        spread_code = "\n".join(filter(None, [br["init_body"], br["increments"], br["msp_code"]]))
        spread_sem = self._periph_semantics(peripheral, spread_code)
        sample_sem = self._periph_semantics(peripheral, rendered.get("init", ""))
        diff = [
            f"{k}: 铺开={spread_sem[k]} vs 样本={sample_sem.get(k)}"
            for k in spread_sem
            if spread_sem[k] != sample_sem.get(k)
        ]
        return {"match": not diff, "spread": spread_sem, "sample": sample_sem, "diff": diff}

    def render_periph_init_from_bundle(self, peripheral: str, bundle: dict[str, Any], chip: str = DEFAULT_CHIP) -> dict[str, Any] | None:
        """6 外设铺开（2026-08-20）：从 functional bundle 反推参数 → 单区块渲染基础 init → 增量保留。

        GPIO 已由 render_gpio_init_from_bundle 做范式，本方法把 UART/TIM/ADC/SPI/I2C/CAN
        同样改调用到单区块（变量名标准化 + 基础 init），functional 退居证明样本。

        分层（念安 8-20「增量还是按模板走 + 分层隔离 + 优先级」）：
          - 基础 init（时钟+句柄+Init+引脚复用）→ 单区块渲染标准化（htim/huart + _hal 命名）
          - 功能增量（NVIC/Receive_IT、OC 配置/PWM_Start）→ 从 functional init 保留（extract_increments）
          - 增量依赖变量（rx_byte 等）→ 从 functional globals 保留（extract_increment_globals）

        peripheral 无铺开配置（或 DMA 等辅助外设）时返回 None，调用方回退 functional 老路。

        返回：{init_func, init_body(基础), deinit_func, deinit_body, msp_code, globals(句柄),
               increments(增量), inc_globals(增量变量声明)}。
        """
        from knowledge.template_forge.periph_derive import (
            _PERIPH_DERIVE,
            _standardize_vars,
            extract_increment_globals,
            extract_increments,
            extract_pin_mux,
        )

        # 规范化（2026-08-24 能力配置架构化）：board 模板 peripheral 带实例号
        # （ADC1/CAN1/USART1/TIM14），functional 不带（ADC/CAN/UART/TIM）——统一去实例号 +
        # USART→UART + FSMC→SRAM，否则 board 外设匹配不到 _PERIPH_DERIVE → 回退老路，
        # 能力配置（ConfigChannel/ConfigFilter）就无法从 .tmpl 唯一出口生成。
        _base = re.sub(r"\d+$", "", str(peripheral).upper())
        peripheral = {"USART": "UART", "FSMC": "SRAM"}.get(_base, _base)

        entry = _PERIPH_DERIVE.get(peripheral)
        if entry is None:
            return None
        init = str(bundle.get("init", "") or "")
        # 复杂增量回退（2026-08-22 全模板编译验证揪出）：DMA 扫描（__HAL_LINKDMA）含
        # 「辅助外设句柄配置」，extract_increments 的正则无法区分 ADC/DMA 的 .Init 配置 →
        # 丢变量声明/配置 → 编译失败。回退 functional 老路（split_init_for_msp 保留完整 init）。
        # CAN 过滤器已补增量标记（CAN_FilterTypeDef + .Filter 配置），不在此回退之列。
        if "__HAL_LINKDMA" in init:
            return None
        derive_fn, init_func_fmt, deinit_func_fmt, globals_fmt = entry
        params = derive_fn(init)  # 反推用户可指定关键参数（instance + 数值），其余 meta default 兜底
        instance = params.get("instance", "1")
        # chip 贯穿（2026-08-24 修断链）：单区块渲染须带真实 chip——fill_block 的芯片自适应
        # （prescaler/period）与板卡画像驱动（RTC LSE）都依赖正确 chip。此前用默认 apm32f407vgt6，
        # RTC 铺开时匹配不到探索者板（meta.mcu=stm32f407zgt6）→ LSE 判断回退 LSI。
        code = self.render_init(peripheral.lower(), params, chip)
        # TIM 模式替换：单区块 tim_init 写死 Base_Init，按 functional 反推的模式换 Init/DeInit
        # （PWM 功能须 HAL_TIM_PWM_Init，否则 HAL_TIM_PWM_ConfigChannel 拿不到 PWM 句柄状态）
        if peripheral == "TIM":
            init_call, deinit_call = _TIM_MODE_INIT.get(params.get("tim_mode", "base"), _TIM_MODE_INIT["base"])
            code = code.replace("HAL_TIM_Base_Init", init_call).replace("HAL_TIM_Base_DeInit", deinit_call)
        init_func = init_func_fmt.format(instance=instance)
        deinit_func = deinit_func_fmt.format(instance=instance)
        init_body_full = self._extract_func(code, init_func)
        deinit_body = self._extract_func(code, deinit_func)
        from knowledge.template_forge.project_slicer import split_init_for_msp

        mx_init, msp_code = split_init_for_msp(init_body_full, peripheral)
        # TIM 的引脚复用块从 functional 保留（单区块 tim_init 缺引脚复用段——基础定时器
        # 不需要引脚，PWM/IC/OC 才需要），标准化后进 msp（复合外设引脚复用 → hal_msp.c）
        if peripheral == "TIM":
            pin_mux = extract_pin_mux(peripheral, init)
            if pin_mux:
                msp_code = (msp_code + "\n" + pin_mux).strip("\n") if msp_code else pin_mux
        # 功能增量（NVIC/Receive_IT、OC 配置/PWM_Start）从 functional 保留 + 变量名标准化
        increments = extract_increments(peripheral, init)
        inc_globals = extract_increment_globals(peripheral, str(bundle.get("globals", "") or ""))
        # extra_code（中断回调等完整函数）变量名标准化：回调引用的句柄/缓冲跟着标准化，
        # 否则铺开后句柄是标准名（huart），回调却引用功能特定名（uartirq_huart）→ 未定义。
        extra = _standardize_vars(peripheral, str(bundle.get("extra_code", "") or ""))
        # loop 段（业务逻辑，main 的 while(1) 内）变量名标准化：业务逻辑引用的句柄跟着
        # 标准化（如 uart_print 的 HAL_UART_Transmit(&uart_huart1) → &huart1），否则编译失败。
        loop = _standardize_vars(peripheral, str(bundle.get("loop", "") or ""))
        return {
            "init_func": init_func,
            "init_body": mx_init,
            "deinit_func": deinit_func,
            "deinit_body": deinit_body,
            "msp_code": msp_code,
            "globals": globals_fmt.format(instance=instance),  # 标准句柄声明，替代 functional 功能特定句柄名
            "increments": increments,     # 功能增量（拼接到 init_body 后，分层隔离）
            "inc_globals": inc_globals,   # 增量变量声明（rx_byte 等）
            "extra": extra,               # 标准化的 extra_code（回调变量名已对齐）
            "loop": loop,                 # 标准化的 loop（业务逻辑句柄已对齐）
        }



def verify_gpio_init(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """便捷入口：单区块 vs functional 的 GPIO 初始化对照校验。"""
    return BlockAssembler().verify_gpio_init(params)


if __name__ == "__main__":
    r = BlockAssembler().verify_gpio_init({"port": "F", "pin_mask": "GPIO_PIN_9"})
    print("对照校验:", "通过" if r["match"] else "不一致")
    print("  单区块:", r["block"])
    print("  样本  :", r["sample"])
    if r["diff"]:
        print("  差异  :", r["diff"])
