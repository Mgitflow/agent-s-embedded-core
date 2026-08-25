# 验证方法（VERIFICATION）

> 回答「怎么证明这套骨架是对的」。分两层：**骨架自检**（不依赖内容，空车能开）+
> **完整生成验证**（填入内容，文字 → 编译 → 上板）。开源只带第一层，第二层给方法 + 接口。

---

## 一、骨架自检（开源，随仓库带）

```bash
python scripts/self_check.py
```

测 5 项（当前全过）：

| 项 | 验证什么 | 当前结果 |
|---|---|---|
| 契约结构 | `CodeSkillOutput` 字段完整 | PASS |
| 校验规则 | 106 条外设校验规则齐全 | PASS |
| 核心模块 import | 23 个核心模块可 import | PASS |
| 接口契约 | 抽象接口 20 个 | PASS |
| assemble_routed 空车跑通 | 缺内容时优雅降级，不崩溃 | PASS |

**自检边界**：只测「不依赖内容」的骨架（契约 / 规则 / 编排逻辑 / 接口）。
完整生成需要内容数据，见下。

## 二、完整生成验证（需要内容数据）

填入真实芯片包 + 功能模板后，复现「文字 → 生成 → 编译」：

```bash
# 1. 放内容：把真实芯片包放到 skills/chips/<chip>/，功能模板放到 forge_templates/
# 2. 文字生成（骨架入口）
python -c "from knowledge.template_forge.functional_assembler import FunctionalAssembler; \
           r = FunctionalAssembler().assemble_routed('点灯', chip='stm32f407zgt6')"
# 3. 真编译（需 arm-none-eabi-gcc + STM32Cube_FW）
python scripts/compile_check.py --text "点灯" --chip stm32f407zgt6
```

判定标准：`assemble_routed` 返回完整工程文件树 + `compile_check` 编译通过（`firmware.hex` 生成）。

## 三、上板验证（最硬，需开发板）

编译过 ≠ 引脚对（SPI 引脚错也编译过，上板才读 FF）。上板三步：

1. 烧录 `firmware.hex`（STM32_Programmer / OpenOCD）
2. 运行态观测：串口回传（`--uart`）或读寄存器（`mode=HOTPLUG`，避免复位污染）
3. 行为观测：灯亮 / 键响应 / 蜂鸣响 / PWM 呼吸

> 上板是揪「引脚错误」的唯一手段——这是「看质量」的核心，不是「看代码生成没生成」。

## 四、空车能开的「降级待办」

当前骨架在**无内容数据**时，`infrastructure/config.py` 模块级调用 `chip_gateway.default_chip()`
扫芯片目录，空仓扫不到芯片 → `KeyError 'STM32F4xx'`。影响范围：

- `infrastructure/config.py` / `chip_gateway.py` / `chip_family.py` / `board_resolver.py`
- `knowledge/template_forge/hal_parser.py` / `board_simple.py` / `functional_assembler.py`
- `knowledge/loaders/mx_skeleton.py`

**改造方向**（预留接口降级，待做）：`chip_gateway` 在 `skills/chips/` 无真实芯片时，
降级到内置「示意芯片」（`_chip_template` 展开的最小默认），`default_chip()` 返回示意而非 KeyError。
改完后空车可「加载示意模板跑通完整生成」，做到真正「能开、能换肉」。
