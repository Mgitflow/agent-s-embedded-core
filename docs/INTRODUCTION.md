# 仓库介绍（INTRODUCTION）

> 这个仓库是什么、为什么这么设计、能产出什么——一段话讲清楚。

## 一、一句话

**确定性 STM32 代码生成骨架**：你给它一句「点灯」「spi flash 读取id」「光敏 蜂鸣器报警」，
它走「识别 → 模板锻造 → 106 条校验 → 真编译」产出**可烧录的完整工程**，主线不强制依赖 LLM（LLM 可选兜底）。

## 二、核心逻辑

```
输入文字 ──识别套式──> 命中模板 ──模板锻造──> 完整工程 ──106校验──> 真编译 ──> firmware.hex
   "点灯"      keywords     参数填充      main/gpio/spi   规则引擎     arm-gcc      可烧录
              "点灯"→led    ${xxx}→PF9     .c 一套       拦截错误     真编译        上板跑通
```

- **识别套式**：文字里的关键词 → 命中哪个外设模板（`keywords` 字段）。
- **模板锻造**：模板里的 `${xxx}` 参数占位符，按芯片肖像 / 开发板定型填成真实引脚和参数。
- **106 条校验**：拦截引脚冲突、时钟顺序、喂狗位置等 19 类外设错误。
- **真编译**：arm-none-eabi-gcc 真编译，编译不过就是错（不是「看起来对」）。

## 三、为什么这么设计（三个决策）

**① 骨架 ≠ 血肉（材料驱动）**：代码只定义「怎么编」，不定义「编什么」。芯片肖像、功能模板、
手册数据都是「材料」（JSON/YAML），加能力 = 加材料，不改骨架。所以本仓开源骨架、留血肉示意。

**② 开发板与芯片并列（不是包含）**：芯片肖像给「芯片默认引脚」（CubeMX 抠），开发板给
「板载定型引脚」（正点原子 BSP 抠），井水不犯河水。血泪教训：板子定型 init 必须「直接套用、
不重新渲染」，否则芯片默认引脚覆盖定型引脚，编译过但上板读不出数。

**③ 确定性主线 + LLM 可选兜底**：识别→模板→校验→编译主线不强制依赖 LLM，同一输入同一输出。
LLM 不是被杜绝，而是作为可选兜底（云端 API + 记忆）挂在外面、可剥离——实测纯模板直出与 LLM 混合
并列最优，LLM 完整生成最差。所以 LLM 层留在原项目，不进本仓。

**④ 连接能力 = 二创空间（上限取决于你）**：项目给的是最底层的原子——一个外设一个模板，铺开、
逐个贴；识别 = 词 → 外设 + 引脚。高级的「连接」不是项目自带的，而是你用这些原子 + 「分层怎么连」
的思路自己拼的：把「点灯」改成「外设 + 引脚 + 按键」，或像看门狗那样把「启动 + 观察 + 重置」串成
一条链、再用一个词代替。这就是二创——**我保证下限，上限取决于你**。

## 四、成品展示（原项目真实生成产物）

输入「点灯」（探索者开发板）→ 确定性生成的 `gpio.c`：

```c
void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    HAL_GPIO_MspInit(GPIOF);
    GPIO_InitStruct.Pin = GPIO_PIN_9;          /* 探索者 LED0 = PF9（板载定型，非芯片默认） */
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOF, &GPIO_InitStruct);
}
```

上板验证（原项目实测，文字 → 生成 → 编译 → 烧录 → 观测一条龙）：

| 外设 | 结果 |
|---|---|
| 串口打印 | `hello agent-s` 循环输出 |
| SPI Flash 读 ID | `68 40 18`（真实 JEDEC ID，W25Q128） |
| 外部 SRAM 读写 | `0x5555 OK` |
| ADC 采样 | 3814-3826 稳定 |
| 点灯 / 按键 / PWM / 蜂鸣器 | 引脚全对（PF9 / PE3-4 / TIM14@PF9 / PF8） |

## 五、怎么用（三步）

```bash
# 1. 自检（空车能开，不依赖血肉）
python scripts/self_check.py        # 5/5 通过

# 2. 填血肉（最小原型，见各 _chip_template / _example 的 README）
#    把真实芯片肖像放 skills/chips/<chip>/，功能模板放 forge_templates/<name>.json

# 3. 生成（骨架入口，填了血肉就能跑）
python -c "from knowledge.template_forge.functional_assembler import FunctionalAssembler; \
           print(FunctionalAssembler().assemble_routed('点灯', chip='stm32f407zgt6'))"
```

## 六、仓库地图

```
contracts/     契约层（数据类 + 抽象接口，血肉由此接入）
engine/        编排 + 106 校验规则 + 编译流水线
infrastructure/ 配置 / 芯片族 / 编译 / 引脚解析
knowledge/template_forge/   模板锻造编排（识别 → 组装 → 切片，纯代码）
knowledge/loaders/          CubeMX 数据生成器（抠引脚 / 重映射）
skills/chips|boards/        血肉最小原型（空模板 + 字段说明）
src/api + src/studio        入口 + 骨架五件套
scripts/self_check.py       骨架自检
docs/                       架构 / 格式 / 验证 / 本介绍
```
