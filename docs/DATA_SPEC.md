# 血肉格式说明（DATA_SPEC）

> 开源仓库里每个血肉目录放了一个「空模板」占位。本文是**字段参考手册**——照此填真实数据，
> 骨架代码自动消费，无需改代码。所有字段以实际生产项目为准，本说明与示意模板一一对应。

---

## §1 芯片 manifest（`skills/chips/<chip>/manifest.yaml`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | str | 芯片名（目录名同此，如 `stm32f407zgt6`） |
| `display_name` | str | 显示名 |
| `vendor` | str | 厂商（含系列） |
| `type` | str | 固定 `chip` |
| `inherits` | list | 继承层（`_common` + `_series_xxx`），只覆盖芯片特定参数 |
| `layer` | int | 继承层级（芯片级 = 3） |
| `chip.family` | str | 系列（F1/F4/G4），决定 HAL 前缀与时钟基准 |
| `chip.core` | str | 内核（Cortex-M4F 等） |
| `chip.max_clock_mhz` | int | 最高主频 |
| `chip.flash_kb` / `ram_kb` / `ccm_kb` | int | 存储容量 |
| `chip.package` | str | 封装（决定引脚范围，LQFP144 等） |
| `chip.has_fpu` / `has_dsp` | bool | 特性开关 |
| `hal.library` / `version` / `reference_manual` | str | HAL 库名 / 版本 / 参考手册号（引脚权威来源） |
| `peripherals.supported` | list | 支持的外设清单 |
| `peripherals.gpio_ports` | list | 可用 GPIO 端口 |
| `files.*` | str | 指向 profile / pin_map / af_map 文件名 |

## §2 芯片画像（`profile.json`，13 顶层字段）

`meta`（芯片元信息）/ `capabilities`（能力）/ `clock_tree`（时钟树）/ `clock_bus`（总线时钟）/
`clock_requirements`（时钟需求）/ `init_order`（初始化顺序）/ `nvic_priorities`（中断优先级）/
`pin_map`（引脚映射）/ `af_map`（复用功能映射）/ `debug`（调试）/ `skeleton`（工程骨架）/
`special_pins`（特殊引脚）/ `dma`（DMA 通道）。

## §3 引脚映射（`pin_map.json`）

顶层：`schema_version` / `chip` / `package` / `comment` / `pins`。
`pins` = 每引脚一个键，值为该引脚可复用的信号清单（含 ADC/DAC/普通外设/特殊功能）。

## §4 复用功能映射（`af_map.json`）

顶层：`comment` / `af_numbers`（信号 → AF 编号）/ `default_pins`（外设 → 默认引脚）/
`full_af_map`（信号 → 全部可用引脚）。F1 系列无 AF 编号，靠 AFIO 重映射，另有 `remap_map.json`
（信号 → 引脚 → 重映射宏，从 CubeMX GPIO IP 提取）。

## §5 开发板（`skills/boards/<board>/board.json`）

| 字段 | 说明 |
|---|---|
| `meta` | 板子名 + 绑定主控 `mcu`（决定走哪套芯片肖像） |
| `oscillator` | 板载晶振（HSE/LSE 频率） |
| `leds` / `keys` | 板载 LED / 按键引脚（板级定型） |
| `onboard_peripherals` | 板载资源（SPI Flash / 外部 SRAM / 蜂鸣器等） |
| `codegen_rules` | 代码生成规则（按键启动门 / 有源器件待机） |

## §6 功能模板（`forge_templates/functional/<name>.json`，14 字段）

| 字段 | 说明 |
|---|---|
| `id` | 模板唯一标识 |
| `version` | 版本 |
| `peripheral` | 外设名（GPIO/TIM/UART/…） |
| `init_func` / `deinit_func` | 初始化 / 反初始化函数名（如 `MX_GPIO_Init`） |
| `keywords` | 识别套式（文字 → 模板匹配词，**固定模板匹配的关键**） |
| `description` | 功能描述 |
| `depends` | 依赖的其他模板 |
| `globals` | 句柄声明等全局代码 |
| `init` / `loop` / `deinit` | 初始化 / 主循环 / 反初始化代码（`${xxx}` 为参数占位符） |
| `params` | 参数定义（`param_filler` 据此填充 `${xxx}`） |
| `requires_uart` | 是否依赖串口回传 |

## §7 手册数据（`knowledge/manuals/<chip>/`）

`electrical.json`（电气参数：内存分区 / 时钟域 / 电压阈值 / 时序标准）+
`handbook/`（外设手册解读，标准值如 CPOL/CPHA/波特率/时序）。

---

> **接入原则**：以上所有入口走抽象接口（chip_gateway / profile_manager / FunctionalTemplateStore），
> 填好数据放到对应目录，骨架自动扫描识别。数据格式不对会显式报错，不会静默。
