# 模板生产底座（Template Forge Base）— 影子工程 V2 S3 的知识支撑

> 重构。位置：`knowledge/template_forge/`
> 定位：**识别套式（assemble_routed）的模板知识底座**（forge_engine 旧套已归档）。

## 〇、四源资源全利用（资源都是弄好的，要会用）

| 资源 | 位置 | 用途 | 适配器 |
|---|---|---|---|
| **HL 库**（26 万行） | `reference/hal/` | HAL API 骨架 + 全库 API 名校验（防模板写错函数名） | `hal_parser.py` + `resource_adapter.py` |
| **芯片肖像** | `skills/chips/apm32f407vgt6/` | af_map 引脚/AF 自动适配（说"串口"→PA9/PA10/AF7）、standards 质量规则、profile 时钟 | `chip_portrait_adapter.py` |
| **共享知识库** | `AGENT_SHARED_KB/archived/`（默认 `<项目父目录>/shared_knowledge/`） | ST 官方 HAL 写法聚合（生成代码带官方参考注释） | `resource_adapter.py` |
| **符号索引** | `knowledge/symbol_index.py` | Serena 2889 符号（真实 HAL 库） | `resource_adapter.py` |

## 一、模板的两层形态（""比喻）

```
完整工程代码 = 上层面包（固定框架）
            + 夹层（功能逻辑：init / loop / deinit）
            + 下层面包（收尾）
```

| 层 | 形态 | 内容 | 位置 |
|---|---|---|---|
| **外设模板** | 外设 × 场景 | GPIO/UART/TIM 初始化段（只有 init） | `forge_templates/<peri>/`（14 外设 × 3 场景 = 42 个） |
| **功能模板** | 功能 × MX 配置函数 | **26 个全外设功能**——点灯/重置/PWM/舵机/串口/ADC/SPI/I2C/DAC/DMA/RTC/CAN/SD/看门狗/CRC/RNG，v2 范式（init_func/deinit_func + peripheral + extra_code） | `forge_templates/functional/`（26 个，v2 版本化） |

**功能模板才是"汉堡"**——每块备齐"蔬菜酱汁肉片"（初始化 + 主循环 + 收尾），
按外设分组成 `MX_xxx_Init()` 配置函数，搭进 mx_skeleton 的标准工程骨架。
外设模板只是夹层的零件。

功能模板清单（26 个，覆盖芯片全部外设）：
```
GPIO:  led_blink 点灯 / button_read 按键 / gpio_exti 外部中断 / gpio_multi_out 流水灯
TIM:   pwm_output 呼吸灯 / pwm_servo 舵机 / tim_periodic 定时器中断 / tim_input_capture 输入捕获
UART:  uart_print 串口打印 / uart_interrupt 中断接收 / uart_dma DMA 收发
SPI:   spi_master 主机收发
I2C:   i2c_scan 总线扫描 / i2c_sensor 传感器读写
ADC:   adc_read 单通道 / adc_dma_scan 多通道 DMA
DAC:   dac_output 波形输出
DMA:   dma_mem_copy 内存拷贝
RTC:   rtc_calendar 日历时钟
CAN:   can_communication 总线通信
SDIO:  sd_card SD 卡读写
IWDG:  iwdg_refresh 独立看门狗 / system_reset 系统重置
WWDG:  wwdg_refresh 窗口看门狗
CRC:   crc_compute 校验
RNG:   rng_random 硬件随机数
```

## 二、功能模板库（FunctionalTemplateStore）

```python
from knowledge.template_forge.functional_templates import FunctionalTemplateStore

store = FunctionalTemplateStore()
store.match("做一个呼吸灯")        # -> "pwm_output"（关键字识别，长=具体优先）
store.match_from_plan(plan)      # -> 从意图 dict/对象提取文本匹配
bundle = store.render("led_blink", {"led_pin": "5"})
# -> {globals, init, loop, deinit, init_func, deinit_func, peripheral, extra_code}
#    v2 范式：init_func="MX_GPIO_Init"、deinit_func="MX_GPIO_DeInit"（配置函数名），
#    init/deinit 是裸函数体（不再内联），中断回调拆到 extra_code
store.archive_all()              # -> 归档到 forge_templates/functional/（只增不减）
```

当前功能模板 **26 个**（覆盖芯片全部外设，见上方清单）——从 JSON 单一权威源加载：
`forge_templates/functional/*.json`（v2 字段：version/peripheral/init_func/deinit_func/
globals/init/loop/deinit/extra_code/params，py 只留逻辑）。

关键字智商规则：**长关键字优先**——"呼吸灯" > "灯"，PWM 呼吸灯不会被点灯模板抢走。

## 三、拼装器（FunctionalAssembler）

26 个功能 bundle → `bundles_to_project_slices` 按外设分组 → mx_skeleton 标准工程：
```
main.c:        HAL_Init → SystemClock_Config → MX_xxx_Init() 调用（只调不定义）
外设 .c:       gpio.c / usart.c / tim.c ...（MX_xxx_Init 函数体，同名合并）
hal_msp.c:     时钟使能 __HAL_RCC_*_CLK_ENABLE + 引脚复用（严格 CubeMX）
loop:          while(1) 主循环（点灯/呼吸/打印/采样逻辑）
```

### 完整工程包（真正可用的工艺级代码，，标准工程化）

`assemble_routed`（识别套式）→ `build_standard_project`：功能模板按外设分组，产出**标准 CubeMX 工程**
（不止 main.c，含外设独立文件 + hal_msp.c）：
```
<project>/Core/Inc/    main.h / stm32f4xx_hal_conf.h / stm32f4xx_it.h
<project>/Core/Src/    main.c / gpio.c / usart.c / tim.c / ...（按外设）
                       stm32f4xx_hal_msp.c（时钟使能 + 引脚复用）/ stm32f4xx_it.c / system_stm32f4xx.c
<project>/Core/Startup/ startup_stm32f407xx.s
<project>/STM32F407VGTx_FLASH.ld / project_info.md
<project>/Makefile + Drivers/（HAL/CMSIS/DEVICE 驱动复制）
```

**变量唯一化铁律**：26 个模板内部变量全部带模板前缀（led_gpio_init/uart_huart/
pwm_tim/...），多模板组合时 C 变量零冲突——这是"组合后能编译"的保障。
**严格 CubeMX 分工**：时钟使能/引脚复用进 `hal_msp.c`（HAL_xxx_MspInit），
外设 .c 只做句柄配置 + HAL_xxx_Init。

## 四、识别套式（assemble_routed）+ 双通道竞争

```
识别套式:  identify_routines 识别需求 → board 简单逻辑模板优先 → functional 补缺 → 缺失报告
双通道:    A 脚本识别套式模板直出 / B LLM 选模板混合（并行竞争 + 最终巡查）
```

```python
from knowledge.template_forge.functional_assembler import FunctionalAssembler

FunctionalAssembler().assemble_routed("我要点灯")      # 识别套式统一入口
FunctionalAssembler().identify_routines("点灯+按键")   # 识别需求（board 命中 + functional 补缺）
```

**芯片肖像适配**：assemble_multi/assemble_routed 渲染前自动补引脚/AF/时钟——
"串口打印" → PA9/PA10/AF7 自动注入；用户指定优先，肖像兜底。
**资源增强**：渲染后 API 名校验（全 HAL 库白名单，拼错函数名即拦）+ 四源知识注释注入。

## 四·五、引脚占位机制（PinAllocator，OccupancyGrid 落点，）

脚本自动识别引脚可能"瞎识别"、可能撞车——**占位机制**保证：
只要前一个功能占了某个引脚，后面自动识别时这个引脚就不能再占。

```
锻造路径（单功能/组合/完整工程）→ 渲染前逐功能分配引脚：
  ① 模板声明引脚需求（PIN_REQUIREMENTS：uart_print → USART{n}_TX/RX；led_blink → @GPIO）
  ② 候选带排序（get_signal_candidates：default 优先 + 字母序）
     "这一类有几个、都是哪些、哪个优先" 全部声明清楚
  ③ 前占后避：首选被占 → 自动避让到下一个候选，冲突日志标注 [PINS]
  ④ 复用段生成：分配结果 → CubeMX 风格 GPIO AF 复用代码，注入 init 段
     （模板保持四段：句柄/时钟/参数/校验；第五段引脚复用运行时动态生成——
      分配器避让可能跨端口，按实际引脚逐信号生成才天然正确）
```

```python
from knowledge.template_forge.pin_allocator import PinAllocator

al = PinAllocator()
al.allocate("USART1_TX", "uart_print", "PA9")   # 先占 PA9
al.allocate("TIM1_CH1", "pwm_output", "PA5")    # PA5 空闲 → 用
al.allocate("TIM1_CH1", "pwm_output", "PA5")    # 已被占 → 自动避让到 PA8
# conflict_log(): ["pwm_output: TIM1_CH1 首选 PA5 已被 ... 占用，自动避让"]
```

铁律：**先分配先占，后分配自动避让**；避让过程必须标明（[PINS] 日志），
用户/LLM 能看见"PA9 被占 → 换 PB6"，杜绝静默撞车。

## 四·六、参考范本 + 模板核验（通用模板单拎出来做完美范本）

**参考范本**（`reference_templates.py`，ref_f407/ref_f103）——系列级"完美模板"：
不写具体数值，就是"嵌入式公共代码就该这么写"的标准（文件头 / HAL_Init →
SystemClock_Config → 外设初始化区 → while(1) → Error_Handler；外设 init
五段式：句柄声明 → 时钟使能 → 参数配置 → Init 校验 → 引脚复用）。
**一举两用**：既是模板库一员，又是脚本核验和 LLM 指挥的**参考标准**
（上下级调研层——直接跟 LLM 说配置它可能懵，给它看范本就懂了）。

**模板核验**（`template_auditor.py` 已归档，核验职责由 `config_validator.py`
生成前校验 + `scripts/forge_health_check.py` 健康巡查顶替）：细化模板照着范本打、
按范本核验——v2 字段齐全 / 元数据 / init 五段式 / 引脚复用 / 变量前缀 / IWDG 豁免时钟。

```python
from knowledge.template_forge.reference_templates import ReferenceTemplateStore

ReferenceTemplateStore().skeleton("F407")   # 取范本（LLM/脚本参考）
```

## 四·七、生成前配置校验 + S2 双冗余（对照 CubeMX 审查机制，）

**生成前校验**（`config_validator.py`，偷学 CubeMX 审查机制）：
必填（无默认值的 required 必须给）/ 范围（数值 [min,max]，规则表 + 类型推断
`_ms/_rate/_timeout` 后缀兜底）/ 枚举（USART1-6/TIM1-14/SPI1-3 等）/ 引脚存在性
（*_pin 必须在 pin_map）。严重违规（必填缺失/引脚不存在/枚举非法）在
拼装生成前拦截（[CONFIG] 日志）；范围越界标注放行。

**S2 双冗余**（`src/skills/code_skill/dual_auditor.py`，对齐 v2.0 05_dual_redundancy）：
```
A 脚本规则（确定性）: API 真实性（26 万行 HAL 库白名单）+ C 变量重复声明
B 语义（脚本为主，LLM 意图警告附加）: 模板核心 HAL 调用实现性
裁决矩阵: PASS(A✓B✓) / RETRY(A✓B✗→重翻译) / REPAIR(A✗B✓→修复) / HUMAN(双✗/超限)
```
生成后自动审计，[AUDIT] 日志进结果；HUMAN 才阻断（需人工介入），
RETRY/REPAIR 标注放行（影子精神：审计记录，主流程照常）。
无 LLM 时 B 轨脚本降级（影子工程本意就是不靠 LLM）。

**健康巡查**（`scripts/forge_health_check.py`）：一键 8 项巡查（模板完整性/
渲染零残留/API 真实/范本核验/引脚数据/占位避让/变量唯一/知识库同步），
全绿才叫完整可托付。

## 五、现状（复查定格）

- ✅ 四源资源全利用（HL 库骨架/芯片肖像/共享库/符号索引）
- ✅ **功能模板 26 个**（全外设覆盖：GPIO/TIM/UART/SPI/I2C/ADC/DAC/DMA/RTC/CAN/SDIO/IWDG/WWDG/CRC/RNG）
- ✅ 关键字匹配：长=具体优先 + 同外设族去重（adc 多通道采样→adc_dma_scan）
- ✅ 拼装器：26 功能 → 按外设分组 → 标准 CubeMX 工程（外设 .c + hal_msp.c，工程级）
- ✅ 多功能组合（点灯+串口+喂狗 等，段合并 + 肖像适配 + API 校验）
- ✅ 识别套式（assemble_routed）+ 双通道竞争（A/B）+ 生成前配置校验 + S2 双冗余
- ✅ 归档：functional/*.json 26 个版本化（**JSON 单一权威源**，py 只留逻辑）
- ✅ **参考范本**（ref_f407/ref_f103 完美模板）+ **模板核验器**（26/26 按范本达标）
- ✅ 芯片引脚：VGT6 82 GPIO / ZGT6 114 GPIO（官方数据重建，PH0/PH1 与 OSC 合并）
- ✅ 套式数据剥离 py dict → JSON 单一权威（新旧合一清理）
- ✅ 真编译验证：armclang 26 模板编译链接通过（MDK5 AC6 + ST 固件 V1.28.3）
- ✅ 健康巡查 11 项全绿（含收藏室完整性）；测试全绿；mypy 0 债
- 📋 **收藏室总索引**：`vault/VAULT_INDEX.md`（101 件资产 × 7 区域块，明面清单）

## 六、铁律

1. **原线路零改动**：主轨 LLM 生成不动，影子副轨只做加法
2. **失败安全**：锻造/匹配失败 → 回退，绝不阻断主轨
3. **只增不减**：模板库只加不改（审计铁律），旧模板保留
4. **量无上限**：模板越多套用越准；功能模板持续扩量

*模板底座定义 v4（四源资源适配 + 组合），。*
