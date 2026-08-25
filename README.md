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

它继承 STM32CubeMX 的 HAL 调用规范（行业共识，不重新发明轮子），但不复制 MX 的「一键生成即完工」——在这里，生成只是开始，106 条校验 + 真编译 + 上板验证才是终点。

主线**不强制依赖 LLM**——同一输入，同一输出。

## 为什么不是「纯 LLM 生成」

| 维度 | 纯 LLM 生成 | 本骨架 |
|:---|:---|:---|
| **确定性** | 每次可能不一样 | 同一输入，同一输出 |
| **可验证** | 黑盒，靠猜 | 106 条校验 + 真编译 |
| **引脚正确性** | 大概率错、上板露馅 | 材料化标准值 |
| **复杂外设** | 容易报废、修个没完 | 模板锻造，可复现 |
| **可托付** | 你敢让它上板吗 | 链路可查、可复现 |

## 关于「agent」这个名字

项目叫 agent-s，但主线不靠 LLM——这不是矛盾，得说清楚：

- **命名习惯，不是能力声明**：它是「agent-s 组织」的一员（组织内多个项目协同），agent 只是沿用组织前缀，不代表「依赖 AI 智能体」。
- **可以用 LLM，但不是主线**：LLM 可作为可选兜底（云端 API），但实测「用了不如不用」——纯模板直出与 LLM 混合并列最优，LLM 完整生成反而最差。
- 所以这是**确定性优先**的方向突破，不是「反 LLM」。名字是历史沿革（单人开发、与其他项目协同，不另起炉灶），能力是确定性的。

## 起点是 MX，终点是你

MX 是行业标准，也是 80% 嵌入式开发者默认的起点。对多数人来说，能跑通一个 demo 就够了——不需要 RTOS，不需要深度功耗优化。

这是现实，这个项目承认它。

但这个项目不是 MX 的复制品。它是一个**壳子**——给你确定性的骨架（识别 → 模板锻造 → 106 校验 → 真编译），壳子里装什么，由你决定：

- MX 替你定引脚 → 这个壳子让你自己定：芯片肖像与开发板定型并列，井水不犯河水
- MX 一键生成即完工 → 这个壳子说「生成只是开始」，校验 + 真编译 + 上板才是终点
- MX 把外设都配好 → 这个壳子只给骨架，血肉留白

所以 **MX 是起点，不是终点**。终点在哪、能走多远，不取决于 MX，取决于你——取决于你填的血肉、写的模板、定的规则。只填一个 GPIO，它是个点灯工具；填了完整时钟树和自定义链接脚本，它是台可深度定制的生成引擎。

**同一副壳子，取决于装它的人。**

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

### ③ 一条龙（生成 → 编译 → 烧录，需 ST 工具链 + 板子）

```bash
python scripts/build_flash.py "点灯"              # 编译 + 烧录
python scripts/build_flash.py "点灯" --no-flash   # 只编译，不烧录
```

工具链与资料需自行准备（本仓不内置：体积大 + ST 版权）：

- `arm-none-eabi-gcc`（STM32CubeIDE 自带，或 GNU Arm Embedded Toolchain）
- `STM32Cube_FW_F4` HAL 库（st.com 免费下载）
- `STM32_Programmer_CLI`（st.com 免费下载）
- ST 参考手册 RM0090 / 数据手册（st.com 免费下载，填完整芯片肖像时查引脚表、时钟树）

脚本自动探测工具链，缺什么提示什么，不静默失败。

## 如何填肉

骨架是空车。**加芯片 / 加外设 = 加材料，不改代码。**

### 加一颗芯片

`skills/chips/你的芯片名/` 下放四个文件：

| 文件 | 作用 |
|:---|:---|
| `manifest.yaml` | 芯片族 / 内核 / 主频 / HAL 库名 |
| `profile.json` | 芯片画像（RAM/Flash、时钟树、外设能力） |
| `pin_map.json` | 引脚映射（如 `PA5` → GPIO） |
| `af_map.json` | 复用功能映射（如 `USART1_TX` → `PA9`） |

格式见 `skills/chips/_chip_template/`（空模板 + 注释）和 `docs/DATA_SPEC.md`，可参考 `skills/chips/stm32f407zgt6/`。

### 加一个外设模板

`knowledge/template_forge/forge_templates/functional/你的模板名.json`：

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

`keywords` 用于识别，`init / loop / deinit` 是代码块。完整字段规范见 `knowledge/template_forge/TEMPLATE_SPEC.md`。填完运行 `python examples/run_example.py` 即可识别新词、生成新代码。

**填肉就是试错。** 模板错？校验器拦。引脚错？编译报。上板读 FF？回来改芯片肖像。骨架降低试错成本，不保证一次做对。

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

MIT License © 2026 agent-s-embedded-core contributors
