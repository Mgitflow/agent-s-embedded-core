# 功能模板设计规范（Template Spec）—— 开源骨架的「模板库说明书」

> 这份文档告诉你：**功能模板是什么、长什么样、怎么新加一个。**
> 开源后，别人拿到骨架，靠这份文档就能自己往模板库里塞新功能，不用猜。

---

## 一、模板是什么（一句话）

一个功能模板 = **一段「有始有终」的外设功能代码**，切成三段塞进标准工程：

```
init      → 塞进 MX_xxx_Init()（外设初始化，main 里调用一次）
loop      → 塞进 main() 的 while(1)（业务逻辑，反复跑）
deinit    → 塞进 MX_xxx_DeInit()（收尾，反序调用）
globals   → 塞进全局变量区（init 和 loop 共享的句柄/缓冲/结果）
extra_code → 塞进 USER CODE 区（中断回调等完整函数）
```

**核心比喻（念安「汉堡」）**：`完整工程 = 固定框架（面包）+ init/loop/deinit（夹层）+ 收尾`。
框架是 `mx_skeleton.py` 生成的 15 文件标准工程，模板只负责「夹层」。

---

## 二、一个模板的完整结构（以 crc_compute 为例）

```jsonc
{
  "id": "crc_compute",          // 模板唯一 id（文件名 = id.json）
  "version": "v2",              // 范式版本
  "peripheral": "CRC",          // 外设名（决定外设文件分组 + MspInit 归属）
  "init_func": "MX_CRC_Init",   // main 里调用的配置函数名（可含 ${instance} 占位符）
  "deinit_func": "MX_CRC_DeInit",
  "keywords": ["crc", "校验"],  // 触发词（识别套式 match 用，长词优先）
  "description": "CRC 校验计算",
  "depends": ["crc"],           // 依赖的外设（生成 HAL 模块启用宏）
  "globals": "CRC_HandleTypeDef crc_hcrc;\nuint32_t data[${crc_len}] = {0xDEADBEEF};\nuint32_t ${crc_var} = 0;",
  "init": "  __HAL_RCC_CRC_CLK_ENABLE();\n  crc_hcrc.Instance = CRC;\n  if (HAL_CRC_Init(&crc_hcrc) != HAL_OK)\n  {\n    Error_Handler();\n  }",
  "loop": "    uint32_t crc_value = HAL_CRC_Calculate(&crc_hcrc, (uint32_t*)data, ${crc_len});\n    ${crc_var} = crc_value;\n    HAL_Delay(${crc_interval});",
  "deinit": "  HAL_CRC_DeInit(&crc_hcrc);",
  "params": {
    "crc_buf":  { "type": "string", "required": true,  "default": "(uint32_t*)data" },
    "crc_len":  { "type": "uint16", "required": false, "default": 16 },
    "crc_var":  { "type": "string", "required": false, "default": "crc_result" },
    "crc_interval": { "type": "uint16", "required": false, "default": 1000 }
  }
}
```

### 字段速查表

| 字段 | 必填 | 含义 |
|---|---|---|
| `id` | ✅ | 模板唯一 id，= 文件名（不含 .json） |
| `peripheral` | ✅ | 外设名（GPIO/TIM/UART/SPI/I2C/ADC/DAC/DMA/RTC/CAN/SDIO/IWDG/WWDG/CRC/RNG/USB） |
| `init_func` / `deinit_func` | ✅ | 配置函数名，可含 `${instance}`（如 `MX_USART${uart_instance}_UART_Init`） |
| `keywords` | ✅ | 触发词，`match()` 用它识别需求（长词优先匹配） |
| `init` / `loop` / `deinit` | ✅ | 三段代码（见下「关键约定」） |
| `globals` | ✅ | 全局变量（句柄 + 跨函数数据），`${}` 占位符可参数化 |
| `params` | ✅ | 参数 schema，`default` 兜底（用户没指定时用） |
| `extra_code` | 选 | 中断回调等完整函数 |
| `depends` | 选 | 依赖外设（生成 HAL 模块启用宏） |
| `description` | 选 | 一句话说明 |

---

## 三、关键约定（铁律 · 写模板必须遵守）

1. **跨函数变量放 `globals`，绝不放 `init`** —— `init` 塞进 `MX_xxx_Init()`（局部作用域），
   `loop` 塞进 `main()`（另一个作用域）。init 里声明的局部变量，loop 引用会 `undeclared`。
   （2026-08-22 全模板编译验证揪出：11 个模板踩了这个坑，变量声明从 init 挪到 globals 才修好）

2. **句柄 + 数据缓冲 + 结果变量，全部进 `globals`** —— 例如 `uint32_t data[16] = {0};`、
   `uint8_t tx_data[8] = {0};`，init 只做「配置句柄 + HAL_xxx_Init」。

3. **`init` 里的局部变量（`GPIO_InitTypeDef xxx = {0};`）只在本函数用** —— 用完即弃，
   不跨函数。

4. **变量名用 `${param}` 占位符** —— 参数化，`params` 里给 `default`；`param_filler` 自动填默认值。

5. **`extra_code`（中断回调）里的变量名要与 `globals` 对齐** —— 回调引用全局句柄/缓冲，
   别写未声明的临时变量（tim_input_capture 曾踩 `cap_value` 未声明）。

6. **只增不减** —— 模板库只加不改（审计铁律）；修 bug 是例外，改完跑全量验证。

---

## 四、怎么新加一个模板（4 步）

1. **写 JSON**：在 `forge_templates/functional/<id>.json` 按上面结构写（照抄一个同类模板最快）。

2. **登记工艺契约**：`process_contract.py` 的 `PROCESS_CONTRACT` 加一条——
   ```python
   "<id>": { "must_calls": ["HAL_xxx_Init", "HAL_xxx_xxx"], "peripheral": "XXX", "desc": "..." }
   ```
   （`must_calls` = 这个功能「必须出现」的 HAL 调用，工艺监测器据此校验）

3. **同步共享库**：`cp forge_templates/functional/<id>.json <共享库>/chip_portraits/<芯片>/templates/`

4. **验证编译**：
   ```bash
   python scripts/forge_all_templates_check.py --only <id>   # 单个
   python scripts/forge_all_templates_check.py              # 全量 27 个
   python scripts/forge_health_check.py                     # 健康巡查（含工艺契约/同步）
   ```

---

## 五、验证命令速查

| 命令 | 验证什么 |
|---|---|
| `python scripts/forge_all_templates_check.py` | 27 个模板逐个真编译（按 id 直接组装，绕过 match 歧义） |
| `python scripts/forge_health_check.py` | 健康巡查（模板数/工艺契约/知识库同步/真编译） |
| `python scripts/compile_check.py "点灯"` | 识别套式端到端（自然语言 → 真编译 elf/hex/bin） |
| `python scripts/blueprint_reconcile.py` | 三层对账（功能区块 + 文件 + 预计效果） |
