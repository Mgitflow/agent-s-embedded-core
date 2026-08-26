"""工程切片器：把渲染后的功能 bundle 切成标准 CubeMX 工程结构。

职责单一（解耦）：只做「bundle → 外设 .c 函数体 + hal_msp.c 时钟/引脚复用」的
切片与归组。模板存储/匹配/渲染归 functional_templates.FunctionalTemplateStore，
本模块不碰。

切片规则（严格 CubeMX，）：
  - 时钟使能 __HAL_RCC_xxx_CLK_ENABLE() → hal_msp.c 的 HAL_xxx_MspInit
  - 引脚复用块（GPIO_InitTypeDef → HAL_GPIO_Init）→ 复合外设进 msp，纯 GPIO 进 gpio.c
  - 外设句柄配置 + HAL_xxx_Init → 外设 .c 的 MX_xxx_Init
"""
from __future__ import annotations

import logging
import re
from typing import Any

from knowledge.template_forge.chip_portrait_adapter import DEFAULT_CHIP

_log = logging.getLogger(__name__)


def split_init_for_msp(init_body: str, peripheral: str) -> tuple[str, str]:
    """把渲染后的 init 体拆成 (mx_init_body, msp_code)。

    CubeMX 严格结构：
      - 时钟使能 `__HAL_RCC_xxx_CLK_ENABLE()` → hal_msp.c 的 HAL_xxx_MspInit
      - GPIO 引脚复用块（GPIO_InitTypeDef 声明 → HAL_GPIO_Init）：
          * 纯 GPIO 功能（peripheral == "GPIO"）→ gpio.c 的 MX_GPIO_Init
          * 复合外设（UART/TIM/... 的引脚复用）→ hal_msp.c 的 HAL_xxx_MspInit
      - 其余（外设句柄配置 + HAL_xxx_Init）→ 外设 .c 的 MX_xxx_Init

    Returns: (mx_init_body, msp_code)，均为去首尾空白的代码段。
    """
    mx_lines: list[str] = []
    msp_lines: list[str] = []
    in_gpio_block = False
    gpio_block_to_mx = False
    for line in init_body.split("\n"):
        stripped = line.strip()
        # ① 时钟使能 → 总是 msp（最高优先级，GPIO 块内时钟也拆走）
        #    DMA 例外：STM32Cube_FW 1.28.3 的 HAL_DMA_Init 不调 HAL_DMA_MspInit（注释明确
        #    「Prior to HAL_DMA_Init() the clock must be enabled」），时钟使能若拆到 msp 就
        #    没人调 → DMA2 时钟没使能、拷贝失败。故 DMA 时钟留在 init 体（上板）。
        if re.search(r"__HAL_RCC_\w+_CLK_ENABLE\s*\(", stripped):
            if peripheral == "DMA":
                mx_lines.append(line)
            else:
                msp_lines.append(line)
            continue
        # ② GPIO 块状态机（「」：多段 GPIO 块——spi_flash 的
        #    SCK/MISO/MOSI + CS 片选复用 GPIO_InitStruct 变量，第二段无 GPIO_InitTypeDef
        #    声明，靠 GPIO_InitStruct. 赋值重新进入 GPIO 块，否则 CS 块被误归外设 .c）
        if "GPIO_InitTypeDef" in stripped or re.match(r"\s*GPIO_InitStruct\s*\.", line):
            in_gpio_block = True
            gpio_block_to_mx = peripheral == "GPIO"
        if in_gpio_block:
            (mx_lines if gpio_block_to_mx else msp_lines).append(line)
            if "HAL_GPIO_Init" in stripped:
                in_gpio_block = False
            continue
        # ③ 其余 → 外设 .c
        mx_lines.append(line)
    # strip("\n") 只去首尾换行，保留函数体首行前导缩进（.strip() 会吃掉首行 2 空格）
    return "\n".join(mx_lines).strip("\n"), "\n".join(msp_lines).strip("\n")


def bundle_to_mx_slots(bundle: dict[str, Any]) -> dict[str, list[str]]:
    """单个 render 结果 → MX 范式 main.c 插槽片段（范式化改造核心归一化）。

    把 render() 的产物（init/loop/deinit/globals + init_func/deinit_func）转成
    generate_main_c 需要的插槽，兼容新旧两态：

      v2（MX 范式）：init_func/deinit_func 是配置函数名，init/deinit 是**裸函数体**
        → 包裹成 void MX_xxx_Init(void)/MX_xxx_DeInit(void) 配置函数，main 只调
        MX_xxx_Init()。
      v1（旧内联）：无 init_func/deinit_func，init 是裸语句（main 内联），
        deinit 是**完整函数**（原样 append）。

    Returns:
        {"inits": [...], "protos": [...], "func_defs": [...]}
        - inits      : main 里「Initialize peripherals」区的内容（MX_xxx_Init(); 或内联体）
        - protos     : Private function prototypes 区的 void MX_xxx_Init(void);
        - func_defs  : USER CODE 4 区的配置函数定义（init + deinit）
    """
    init_func = str(bundle.get("init_func", "") or "").strip()
    deinit_func = str(bundle.get("deinit_func", "") or "").strip()
    init_body = str(bundle.get("init", "") or "")
    deinit_body = str(bundle.get("deinit", "") or "")

    inits: list[str] = []
    protos: list[str] = []
    func_defs: list[str] = []

    if init_body.strip():
        if init_func:
            inits.append(f"  {init_func}();")
            protos.append(f"void {init_func}(void);")
            func_defs.append(f"void {init_func}(void)\n{{\n{init_body}\n}}")
        else:
            inits.append(init_body)  # 旧模板：main 内联

    if deinit_body.strip():
        if deinit_func:
            func_defs.append(f"void {deinit_func}(void)\n{{\n{deinit_body}\n}}")
        else:
            func_defs.append(deinit_body)  # 旧模板：完整函数原样 append

    return {"inits": inits, "protos": protos, "func_defs": func_defs}


def bundles_to_mx_slots(bundles: list[dict[str, Any]]) -> dict[str, list[str]]:
    """多个 bundle → MX 插槽，同名配置函数合并（CubeMX 语义：同外设归一个 Init）。

    处理撞名：led_blink / button_read / gpio_exti / gpio_multi_out 都是 MX_GPIO_Init，
    组合时若各自生成同名函数会重复定义编译失败。这里按 init_func/deinit_func 名
    分组，同名函数的 init/deinit 体合并进同一个 `void MX_xxx_Init(void)`。

    v1 旧模板（无 init_func 内联 / deinit 完整函数）仍按 bundle_to_mx_slots 规则
    兜底（迁移过渡期兼容）。
    """
    init_bodies: dict[str, list[str]] = {}
    deinit_bodies: dict[str, list[str]] = {}
    inline_inits: list[str] = []  # v1 无 init_func 的内联体
    legacy_deinit_fns: list[str] = []  # v1 完整函数原样 append

    for b in bundles:
        init_func = str(b.get("init_func", "") or "").strip()
        deinit_func = str(b.get("deinit_func", "") or "").strip()
        init_body = str(b.get("init", "") or "")
        deinit_body = str(b.get("deinit", "") or "")

        if init_body.strip():
            if init_func:
                init_bodies.setdefault(init_func, []).append(init_body)
            else:
                inline_inits.append(init_body)
        if deinit_body.strip():
            if deinit_func:
                deinit_bodies.setdefault(deinit_func, []).append(deinit_body)
            else:
                legacy_deinit_fns.append(deinit_body)

    inits = inline_inits + [f"  {fn}();" for fn in init_bodies]
    protos = [f"void {fn}(void);" for fn in init_bodies]
    func_defs: list[str] = []
    for fn, bodies in init_bodies.items():
        # 合并同名函数体时去重变量声明（GPIO_InitStruct 等局部变量，多模板共用同一 Init）
        merged: list[str] = []
        seen_decls: set[str] = set()
        for body in bodies:
            merged.append(_strip_dup_decls(body, seen_decls))
        func_defs.append(f"void {fn}(void)\n{{\n" + "\n\n".join(merged) + "\n}")
    for fn, bodies in deinit_bodies.items():
        func_defs.append(f"void {fn}(void)\n{{\n" + "\n\n".join(bodies) + "\n}")
    func_defs.extend(legacy_deinit_fns)
    # 附加代码（中断回调/软件 I2C 辅助函数等完整函数）原样 append 进 USER CODE 4。
    # 对称修复：多模板共用相同 helpers（eeprom+imu 的 iic_start/stop 等完全相同）→
    # 按内容去重，只 append 一次，避免函数重复定义编译失败。
    seen_extras: set[str] = set()
    for b in bundles:
        extra = str(b.get("extra_code", "") or "").strip()
        if extra and extra not in seen_extras:
            seen_extras.add(extra)
            func_defs.append(extra)

    return {"inits": inits, "protos": protos, "func_defs": func_defs}


# 变量声明行（合并同名函数体去重用）：类型名 变量名[数组] = 初始化;
# 类型白名单：HAL 句柄类型（GPIO_InitTypeDef/UART_HandleTypeDef/CAN_TxHeaderTypeDef 等，
# 任意前缀）+ 基础类型（uint8_t/int/char/volatile 修饰）。短类型 int 放在 intN_t 之后避免抢前缀。
_TYPE = (
    r"(?:volatile\s+|const\s+|static\s+)*"
    r"(?:[A-Za-z_]\w*_(?:InitTypeDef|HandleTypeDef|TxHeaderTypeDef)"
    r"|uint(?:8|16|32|64)_t|int(?:8|16|32|64)_t"
    r"|int|char|float|double|bool|size_t"
    r"|GPIO_PinState|HAL_StatusTypeDef)"
)
_DECL_RE = re.compile(rf"^(\s*)({_TYPE}\s+\w+(?:\s*\[[^\]]*\])?)\s*(?:=\s*[^;]+)?\s*;\s*$")


def _strip_dup_decls(body: str, seen: set[str]) -> str:
    """去掉 body 里重复的局部变量声明（同一函数内重复声明会编译失败）。

    合并同名 MX_xxx_Init 函数体时，多个模板各自声明了 GPIO_InitStruct 等局部变量，
    只保留第一个，后续同名声明跳过（变量已声明，后续直接复用）。
    """
    lines: list[str] = []
    for line in body.splitlines():
        m = _DECL_RE.match(line)
        if m:
            decl = m.group(2)
            if decl in seen:
                continue  # 重复声明，跳过
            seen.add(decl)
        lines.append(line)
    return "\n".join(lines)


def build_functional_bundle(template_id: str, params: dict[str, Any]) -> dict[str, str] | None:
    """便捷入口：渲染功能模板三段。失败返回 None。"""
    from knowledge.template_forge.functional_templates import FunctionalTemplateStore

    try:
        return FunctionalTemplateStore().render(template_id, params)
    except (KeyError, ValueError) as exc:
        _log.debug("FuncStore render 失败: %s", exc)
        return None


# 外设 → (文件名, MspInit 函数名, MspInit 参数签名)。TIM 的 MspInit 名按模式动态推断。
PERIPHERAL_FILE_MAP: dict[str, tuple[str, str, str]] = {
    "GPIO": ("gpio", "HAL_GPIO_MspInit", "GPIO_TypeDef* GPIO_Handle"),  # 虚拟 MspInit（ST 无 GPIO MSP 层，MX_GPIO_Init 手动调用，结构统一）
    "UART": ("usart", "HAL_UART_MspInit", "UART_HandleTypeDef* huart"),
    "TIM": ("tim", "HAL_TIM_Base_MspInit", "TIM_HandleTypeDef* htim_base"),
    "SPI": ("spi", "HAL_SPI_MspInit", "SPI_HandleTypeDef* hspi"),
    "I2C": ("i2c", "HAL_I2C_MspInit", "I2C_HandleTypeDef* hi2c"),
    "ADC": ("adc", "HAL_ADC_MspInit", "ADC_HandleTypeDef* hadc"),
    "DAC": ("dac", "HAL_DAC_MspInit", "DAC_HandleTypeDef* hdac"),
    "DMA": ("dma", "HAL_DMA_MspInit", "DMA_HandleTypeDef* hdma"),
    "RTC": ("rtc", "HAL_RTC_MspInit", "RTC_HandleTypeDef* hrtc"),
    "CAN": ("can", "HAL_CAN_MspInit", "CAN_HandleTypeDef* hcan"),
    "SDIO": ("sdio", "HAL_SD_MspInit", "SD_HandleTypeDef* hsd"),
    "IWDG": ("iwdg", "HAL_IWDG_MspInit", "IWDG_HandleTypeDef* hiwdg"),
    "WWDG": ("wwdg", "HAL_WWDG_MspInit", "WWDG_HandleTypeDef* hwwdg"),
    "CRC": ("crc", "HAL_CRC_MspInit", "CRC_HandleTypeDef* hcrc"),
    "RNG": ("rng", "HAL_RNG_MspInit", "RNG_HandleTypeDef* hrng"),
    "USB": ("usb", "HAL_PCD_MspInit", "PCD_HandleTypeDef* hpcd"),
    "SRAM": ("sram", "HAL_SRAM_MspInit", "SRAM_HandleTypeDef* hsram"),  # FSMC 外扩 SRAM（IS62WV51216），对称面补：FSMC→SRAM 映射此前无条目 → msp_param 空 → 原型冲突
}


def _tim_msp_signature(init_body: str) -> tuple[str, str]:
    """TIM 的 MspInit 函数名/参数签名按模式推断（PWM/IC/Base）。"""
    if "HAL_TIM_PWM_Init" in init_body:
        return "HAL_TIM_PWM_MspInit", "TIM_HandleTypeDef* htim_pwm"
    if "HAL_TIM_IC_Init" in init_body:
        return "HAL_TIM_IC_MspInit", "TIM_HandleTypeDef* htim_ic"
    return "HAL_TIM_Base_MspInit", "TIM_HandleTypeDef* htim_base"


def bundles_to_project_slices(bundles: list[dict[str, Any]], chip: str = DEFAULT_CHIP) -> dict[str, Any]:
    """多个 bundle → 按外设分组的工程切片（严格 CubeMX：时钟进 Msp、函数体进外设 .c）。

    每个 bundle 的 init 体经 split_init_for_msp 拆成 (外设 .c 函数体, hal_msp.c 代码)，
    再按外设（peripheral）归组。同名 init_func/deinit_func 合并（led_blink+button_read
    都 MX_GPIO_Init → 一个函数）。

    chip：真实芯片型号，贯穿到单区块铺开（render_periph_init_from_bundle）——fill_block
    的芯片自适应与板卡画像驱动（RTC LSE）依赖正确 chip，不可用默认 apm32f407vgt6 顶替。

    Returns:
      {
        "peripherals": {
          "<文件名>": {
            "periph": "GPIO",
            "init_bodies": {"MX_GPIO_Init": [body, ...]},   # 合并的函数体
            "deinit_bodies": {"MX_GPIO_DeInit": [body, ...]},
            "globals": ["句柄定义", ...],
            "extra_code": ["回调/附加代码", ...],
            "msp_fn": "HAL_GPIO_MspInit", "msp_param": "GPIO_TypeDef* GPIO_Handle",
            "msp_code": ["时钟使能/引脚复用代码", ...],
          },
        },
        "main_inits": ["  MX_GPIO_Init();", ...],   # 去重后的 main 调用
        "main_loop": ["loop 体", ...],
      }
    """
    periphs: dict[str, dict[str, Any]] = {}
    main_inits: list[str] = []
    seen_inits: set[str] = set()
    main_loop: list[str] = []
    # 系统保命 loop（「排版顺序」）：看门狗喂狗是「保命」逻辑，不是「业务」，
    # 不能被启动门挡住（否则上电启动看门狗却不喂狗 → 8 秒复位）。单独收集，注入应用层 App_Loop
    # 无条件区（在 App_Business_Run 门控之前跑）。
    system_loop: list[str] = []
    system_periphs: set[str] = set()
    defense_units: set[str] = set()
    # 关闭动作（有源器件的「关」）：启动门 toggle 到关闭时执行（蜂鸣器停/灯灭），
    # 单独收集，注入业务层「关闭沿」清理区（「」——按键能开能关）。
    off_body: list[str] = []

    for b in bundles:
        peripheral = str(b.get("peripheral", "") or "").strip()
        # 防御需求收集（「」）：bundle 的 defense 声明
        # （如 "filter,clamp"）→ 组装层按声明注入对应防御件文件，不是全局默认开。
        for d in str(b.get("defense", "") or "").split(","):
            d = d.strip()
            if d:
                defense_units.add(d)
        # 归一化（「」）：bundle peripheral 带实例号（USART1/SPI1/TIM14），
        # 而 PERIPHERAL_FILE_MAP 的 key 不带实例号（UART/SPI/TIM）——去实例号 + USART→UART/FSMC→SRAM，
        # 否则 fallback 生成错误的 HAL_USART1_MspInit（空参数 → handle 未声明）。
        _base = re.sub(r"\d+$", "", peripheral.upper())
        peripheral_key = {"USART": "UART", "FSMC": "SRAM"}.get(_base, _base)
        init_func = str(b.get("init_func", "") or "").strip()
        deinit_func = str(b.get("deinit_func", "") or "").strip()
        init_body = str(b.get("init", "") or "")
        deinit_body = str(b.get("deinit", "") or "")
        globals_seg = str(b.get("globals", "") or "").strip()
        extra = str(b.get("extra_code", "") or "").strip("\n")
        # strip("\n") 只去首尾换行，保留 loop 首行前导缩进（.strip() 会吃掉首行 4 空格，
        # 导致 while(1) 里第一行业务代码顶格——与 split_init_for_msp 的教训同源，对称修复）
        loop = str(b.get("loop", "") or "").strip("\n")
        # 关闭动作（off）：有源器件在启动门「关闭沿」时复位（蜂鸣器停/灯灭），
        # 「有始有终」。无 off 声明则关闭时无清理动作（纯逻辑外设无有源输出）。
        off = str(b.get("off", "") or "").strip("\n")

        # 外设名兜底（无 peripheral 字段时）
        if not peripheral:
            fname, msp_fn, msp_param = PERIPHERAL_FILE_MAP.get("GPIO", ("gpio", "", ""))
        else:
            fname, msp_fn, msp_param = PERIPHERAL_FILE_MAP.get(
                peripheral_key, (peripheral.lower(), f"HAL_{peripheral}_MspInit", "")
            )
        slot = periphs.setdefault(fname, {
            "periph": peripheral,
            "init_bodies": {}, "deinit_bodies": {}, "globals": [], "extra_code": [],
            "msp_fn": msp_fn, "msp_param": msp_param, "msp_code": [],
        })

        # TIM 的 MspInit 签名按模式动态推断
        if peripheral == "TIM":
            slot["msp_fn"], slot["msp_param"] = _tim_msp_signature(init_body)

        # init 拆分 → 外设 .c 函数体 + hal_msp.c 时钟/引脚复用
        # 改调用（定位掰正 → 6 外设铺开）：
        # GPIO 走 render_gpio_init_from_bundle（范式）；UART/TIM/ADC/SPI/I2C/CAN 走
        # render_periph_init_from_bundle（基础 init 单区块标准化 + 功能增量从 functional 保留，
        # 「增量还是按模板走 + 分层隔离 + 优先级」）；无铺开配置的外设回退 functional 老路。
        if peripheral == "GPIO":
            from knowledge.template_forge.block_assembler import BlockAssembler

            br = BlockAssembler().render_gpio_init_from_bundle(b)
            init_func = br["init_func"]
            deinit_func = br["deinit_func"]
            mx_init = br["init_body"]
            deinit_body = br["deinit_body"]
            msp_code = br["msp_code"]
            # EXTI 中断增量（NVIC 配置）拼接到基础 init 后（分层隔离，同 6 外设铺开）
            gpio_increments = br.get("increments", "")
            if gpio_increments:
                mx_init = mx_init + "\n" + gpio_increments
        else:
            if b.get("source") == "board":
                # board 定型模板（上板 SPI Flash 读 FF FF FF）：
                # 定型 init 的引脚照开发板手册填死（探索者 SPI1=PB3/PB4/PB5 重映射），
                # 直接 split_init_for_msp 拆分定型 init，不被 chip_portrait 默认引脚
                # （PA5/PA6/PA7）覆盖。globals 已是 board 模板声明的标准句柄
                # （SPI_HandleTypeDef hspi1），init_func 也是定型 MX_SPI1_Init，
                # 一并直接套用——「开发板 vs 芯片并列」铁律：提到开发板就用开发板那套。
                mx_init, msp_code = split_init_for_msp(init_body, peripheral)
            else:
                from knowledge.template_forge.block_assembler import BlockAssembler

                pbr = BlockAssembler().render_periph_init_from_bundle(peripheral, b, chip)
                if pbr is not None:
                    # 6 外设铺开：基础 init 单区块标准化（htim/huart + _hal 命名），
                    # 功能增量（NVIC/Receive_IT、OC 配置/PWM_Start）从 functional 保留。
                    init_func = pbr["init_func"]
                    deinit_func = pbr["deinit_func"]
                    mx_init = pbr["init_body"]
                    deinit_body = pbr["deinit_body"]
                    msp_code = pbr["msp_code"]
                    globals_seg = pbr["globals"]  # 标准句柄声明，替代 functional 功能特定句柄名
                    increments = pbr["increments"]
                    inc_globals = pbr["inc_globals"]
                    extra = pbr["extra"]  # 标准化的 extra_code（回调变量名已对齐）
                    loop = pbr["loop"]  # 标准化的 loop（业务逻辑句柄已对齐）
                    if increments:
                        mx_init = mx_init + "\n" + increments  # 增量拼接到基础 init 后（分层隔离）
                    if inc_globals:
                        globals_seg = globals_seg + "\n" + inc_globals  # 增量变量（rx_byte 等）追加
                else:
                    mx_init, msp_code = split_init_for_msp(init_body, peripheral)
        if mx_init:
            if init_func:
                slot["init_bodies"].setdefault(init_func, []).append(mx_init)
                if init_func not in seen_inits:
                    main_inits.append(f"  {init_func}();")
                    seen_inits.add(init_func)
            else:
                # 无 init_func（兜底）：内联进 main
                main_inits.append(mx_init)
        if msp_code:
            slot["msp_code"].append(msp_code)
        if deinit_body.strip() and deinit_func:
            # strip("\n") 只去换行，保留 deinit 函数体首行缩进
            slot["deinit_bodies"].setdefault(deinit_func, []).append(deinit_body.strip("\n"))
        if globals_seg:
            slot["globals"].append(globals_seg)
        if extra:
            slot["extra_code"].append(extra)
        if loop:
            # 系统保命（「改全面」）：模板声明 system_level=true → 保命逻辑
            # （看门狗喂狗/系统软复位），提升到应用层无条件跑，不被启动门门控。材料驱动，
            # 优先读声明；旧模板无声明时按外设名兜底（IWDG/WWDG 是既有保命外设）。
            is_system = bool(b.get("system_level")) or peripheral_key in ("IWDG", "WWDG")
            if is_system:
                system_loop.append(loop)
                system_periphs.add(fname)
            else:
                main_loop.append(loop)
        if off:
            # 关闭动作（有源器件「关」）：启动门 toggle 到关闭时执行，复位有源输出
            off_body.append(off)

    return {
        "peripherals": periphs,
        "main_inits": main_inits,
        "main_loop": main_loop,
        "system_loop": system_loop,
        "system_periphs": sorted(system_periphs),
        "off_body": off_body,
        "defense_units": sorted(defense_units),
    }
