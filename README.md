# agent-s-embedded-core

> **确定性 STM32 代码生成骨架（开源版）** —— 文字 → 识别套式 → 模板锻造 → 106 条校验 → 真编译，全链路不依赖 LLM。

这是一副**能开的空车**：骨架（编排 + 校验 + 编译链路 + 契约接口）全交出去，血肉（芯片肖像 / 功能模板 / 手册数据）留在原项目，每个血肉格子贴了「格式标签 + 空模板」。你 clone 下来照着标签填自己的肉，就能跑起来——**内容是私有的，格式是大家的**。

## 开源边界（一句话）

| 开什么 | 不开什么 |
|---|---|
| 确定性骨架（编排 / 106 校验 / 编译链路） | 芯片肖像 / 功能模板 / 手册数据（护城河） |
| 契约接口（数据怎么接入） | LLM 指挥层（可剥离，实测「用 LLM 不如不用」） |
| 血肉格式说明 + 空模板 | 测试脚本（无血肉，测试无意义） |
| 骨架自检脚本 | 上板验证的完整数据 |

## 仓库结构

```
agent-s-embedded-core/
├── contracts/            契约层：数据类 + 抽象接口（血肉由此接入）
├── engine/               编排 + 校验：rule_engine + 19 外设 validator（106 规则）
│   ├── validators/       外设校验规则（工艺标准）
│   └── compiler/         编译流水线
├── infrastructure/       配置 / 芯片族 / 编译 / 引脚解析
├── knowledge/
│   ├── template_forge/   模板锻造编排（识别 → 组装 → 切片，纯代码）
│   │   └── forge_templates/functional/_example.json   空功能模板（14 字段）
│   └── loaders/          数据生成器（从 CubeMX 抠引脚 / 重映射）
├── skills/
│   ├── chips/_chip_template/     空芯片包（manifest + profile 字段说明）
│   └── boards/_board_template/   空开发板（board.json 字段说明）
├── src/
│   ├── api/              唯一入口（server + 门卫）
│   └── studio/           骨架五件套（skill/context/registry/result/workspace）
├── scripts/
│   └── self_check.py     骨架自检（空车能开验证）
└── docs/
    ├── INTRODUCTION.md   仓位介绍（核心逻辑 + 成品展示，先看这个）
    ├── ARCHITECTURE.md   骨架分层架构
    ├── DATA_SPEC.md      血肉格式说明（填肉的字段参考）
    └── VERIFICATION.md   验证方法（自检 + 完整生成验证）
```

## 快速开始

```bash
python scripts/self_check.py
```

预期输出 `4/4 通过`（契约结构 / 106 校验规则 / 编排层 import / 接口契约）。

## 两条铁律（读代码前先懂）

1. **开发板与芯片是并列关系**：芯片肖像给「芯片默认引脚」，开发板给「板载定型引脚」，井水不犯河水。提到板子走板子那套，提到芯片走芯片那套。
2. **血肉 = 材料，骨架 = 编排**：代码只定义「推理框架 / 编排流程」，具体内容全由材料（JSON/YAML）驱动。加能力 = 加材料 + 新实现，不改骨架。

详见 `docs/ARCHITECTURE.md`。
