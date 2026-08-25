# agent-s-embedded-core

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Version](https://img.shields.io/badge/Version-v1.0.0-orange.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![Self-Check](https://img.shields.io/badge/Self--Check-5%2F5-brightgreen.svg)
![Deterministic](https://img.shields.io/badge/Deterministic-First-red.svg)

> **一句文字，生成可烧录的 STM32 工程。**
> 文字 → 识别套式 → 模板锻造 → 106 条校验 → 真编译。

---

## 这是什么

一套**确定性代码生成骨架**：给它「点灯」，它产出 `MX_GPIO_Init` + `main.c` + `startup.s` + `linker.ld`，编译通过，上板能跑。

主线**不强制依赖 LLM**——同一输入，同一输出。

## 为什么用 MX 做参照

MX 是行业标准，也是 80% 嵌入式开发者的日常。对多数人来说，能跑通一个 demo 就已经满足了——不需要 RTOS 适配，不需要深度功耗优化，默认引脚就挺好。

这不是批评，是现实。

但 MX 有一个隐含前提：**你的项目应该被 ST 的默认值定义。** 默认引脚、默认时钟、默认中断优先级。对只想「跑通 demo」的人来说，够用；对想突破「调库」、走向「懂芯片」的人来说，MX 的默认值是边界。

**这个项目的选择：用 MX 做地板，不用 MX 做天花板。**

- MX 的 HAL 调用规范？**继承**——行业共识，不重新发明轮子。
- MX 的默认引脚分配？**打破**——芯片肖像与开发板定型并列，引脚你定，不是 ST 定。
- MX 的「一键生成即完工」？**拒绝**——生成只是开始，106 条校验 + 真编译 + 上板验证才是终点。

## 为什么血肉留白

**不是藏着不给，是无法统一。**

你的项目跑 FreeRTOS，我的跑裸机；你的板子晶振 8MHz，我的 25MHz；你的 LED 在 PF9，我的在 PA5。强行塞一套「完整」的默认配置，反而谁都用不上——只懂 HAL 的人拿到 RTOS 适配层会懵，做工业控制的人拿到消费级参数会骂。

所以这是**成长型项目**：大一新生填一个 GPIO 模板就能点灯，工作三年的工程师可以自定义时钟树、改写链接脚本、注入防御代码。

**同一副骨架，不同的血肉，长出完全不同的形态。**

> 它不是工具，是一棵树。树干是定好的，你给它浇水（填芯片肖像）、修枝（写功能模板）、塑形（定引脚规则），它长成什么样，取决于你的手艺。**上限取决于你——下限也是。**

## 核心特性

| 特性 | 说明 |
|:---|:---|
| 🎯 **确定性优先** | 识别 → 模板锻造 → 106 校验 → 真编译，同一输入同一输出 |
| 🧩 **材料驱动** | 芯片肖像 / 功能模板 / 手册全是 JSON、YAML，加能力 = 加材料，不改骨架 |
| 🔒 **106 条校验** | 19 类外设工艺标准，拦截引脚冲突、时钟顺序、喂狗位置 |
| 🛠️ **真编译** | arm-none-eabi-gcc 真编译，编译不过就是错 |
| 🏗️ **开发板 / 芯片并列** | 板载定型引脚 vs 芯片默认引脚，井水不犯河水 |
| 🔗 **连接能力** | 原子 + 分层思路，把「点灯」拼成「外设 + 引脚 + 按键」——二创空间 |

## 快速开始

### ① 骨架自检（clone 即跑，空车能开）

```bash
python scripts/self_check.py
```

预期 `5/5 通过`（契约结构 / 106 校验规则 / 核心模块 import / 接口契约 / assemble_routed 空车跑通）。

### ② 跑最小示例（无需工具链）

```bash
python examples/run_example.py
```

仓库自带最小材料包（`stm32f407zgt6` 最小肖像 + `example_led` 模板）。纯 Python，不依赖 arm-gcc / HAL 库 / 烧录器。输出「点灯」→ 识别 → 18 文件工程 → 打印真实 `MX_GPIO_Init` 代码。

### ③ 一条龙（生成 → 编译 → 烧录，需 ST 工具链）

```bash
python scripts/build_flash.py "点灯"              # 编译 + 烧录
python scripts/build_flash.py "点灯" --no-flash   # 只编译，不烧录
```

工具链需自行安装（本仓不内置：体积大 + 版权）：

- `arm-none-eabi-gcc`（STM32CubeIDE 自带）
- `STM32Cube_FW_F4` HAL 库（st.com 免费下载）
- `STM32_Programmer_CLI`（st.com 免费下载）

脚本自动探测，缺什么提示什么，不静默。

## 如何填肉

骨架是空车。**加芯片 / 加外设 = 加材料，不改代码。**

### 加一颗芯片

`skills/chips/<chip>/` 下放四个文件：

| 文件 | 作用 |
|:---|:---|
| `manifest.yaml` | 芯片族 / 内核 / 主频 / HAL 库名 |
| `profile.json` | 芯片画像（RAM/Flash、时钟树、外设能力） |
| `pin_map.json` | 引脚映射（如 `PA5` → GPIO） |
| `af_map.json` | 复用功能映射（如 `USART1_TX` → `PA9`） |

格式见 `skills/chips/_chip_template/`（空模板 + 注释）和 `docs/DATA_SPEC.md`，可参考 `skills/chips/stm32f407zgt6/`。

### 加一个外设模板

`knowledge/template_forge/forge_templates/functional/<name>.json`：

```json
{
  "id": "my_led",
  "keywords": ["点灯", "led"],
  "peripheral": "GPIO",
  "init": "/* 初始化代码 */",
  "loop": "/* 主循环（可选） */",
  "deinit": ""
}
```

`keywords` 用于识别，`init / loop / deinit` 是代码块。填完运行 `python examples/run_example.py` 即可识别新词、生成新代码。

**填肉就是试错。** 模板错？校验器拦。引脚错？编译报。上板读 FF？回来改 portrait。骨架降低试错成本，不保证一次做对。

## 开源边界

| 开什么 | 不开什么 |
|:---|:---|
| 确定性骨架（编排 / 106 校验 / 编译链路） | 芯片肖像 / 功能模板 / 手册数据（护城河） |
| 契约接口（数据怎么接入） | LLM 指挥层（可选外挂，可剥离） |
| 血肉格式说明 + 空模板 | 测试脚本（无血肉，测试无意义） |
| 骨架自检脚本 | 上板验证的完整数据 |

## 现状与边界

V1.0 初版框架，以下不完整，需自行补全：

- 完整生成需完整芯片肖像（示例仅含最小肖像）
- `src/api/server.py` 开源仓仅接口参考（依赖智能层，需从原项目补）
- `functional_assembler.py` 836 行，待拆分
- 异常处理有意 fail-closed，`except Exception` 是兜底设计

## 铁律

1. **开发板与芯片并列。** 芯片给默认引脚，开发板给定型引脚，井水不犯河水。
2. **血肉 = 材料，骨架 = 编排。** 加能力 = 加材料 + 新实现，不改骨架。

详见 `docs/ARCHITECTURE.md`。

## 关于

由念安维护。大一，集成电路技术专业，第一个开源项目。

MIT License © 2026 agent-s-embedded-core contributors
