# 骨架分层架构

## 一句话

确定性代码生成骨架 = **编排流程（不变）** + **材料数据（可变）**。代码只定义「怎么编」，不定义「编什么」。

## 分层图

```
┌─────────────────────────────────────────────────────┐
│  编排骨架（稳定，开源）                                │
│                                                     │
│  识别套式 ──> 模板锻造 ──> 106 校验 ──> 真编译         │
│    │             │            │            │        │
│    │        组装/切片     规则引擎      arm-gcc       │
│    │        (slicer)    (validators)  (compiler)    │
└────┼─────────────┼────────────┼────────────┼────────┘
     │             │            │            │
     ▼             ▼            ▼            ▼
┌─────────────────────────────────────────────────────┐
│  材料层（数据 + 知识，私有，留示意）                     │
│                                                     │
│  芯片肖像      功能模板       手册数据       golden     │
│  pin_map      forge_        electrical    基准       │
│  af_map       templates     handbook      （私有）    │
│  profile      （14 字段）    （私有）                  │
│  （示意）      （示意）                                │
└─────────────────────────────────────────────────────┘
```

## 各层职责

| 层 | 模块 | 职责 | 依赖血肉？ |
|---|---|---|---|
| 契约层 | `contracts/` | 数据类（CodeSkillOutput）+ 抽象接口 | 否 |
| 校验层 | `engine/validators/` | 106 条外设校验规则（工艺标准） | 否 |
| 编排层 | `knowledge/template_forge/` | 识别套式 → 模板锻造 → 组装 → 切片 | 部分（读芯片肖像） |
| 编译层 | `infrastructure/` + `engine/compiler/` | 引脚解析 / Makefile / 编译流水线 | 部分（读芯片族） |
| 入口层 | `src/api/` | server + 门卫（唯一对外入口） | 否 |
| 生成器 | `knowledge/loaders/` | 从 CubeMX 抠引脚 / 重映射（格式生成） | 是（生成数据） |

## 两条铁律

### 1. 开发板与芯片并列（不是包含）

```
芯片（STM32F407ZGT6）──芯片默认引脚（MX 抠，PA5/PA6/PA7）
        │
        ├── 并列 ── 开发板（探索者）──板载定型引脚（正点原子 BSP 抠，PB3/PB4/PB5）
        │
        └── 提到「芯片/通用外设」→ 走芯片那套；提到「开发板」→ 走板子那套
```

血泪教训（原项目上板回归）：板子定型 init 必须「直接套用、不重新渲染」，否则芯片默认引脚会覆盖定型引脚，编译过但上板读不出数。

### 2. 血肉 = 材料，骨架 = 编排

- 接口 = 抽象协议（Protocol / 抽象基类 / schema），实现可替换。
- 数据 / 知识 / 经验 = 材料（json / yaml），不写死在代码里。
- 加能力 = 加材料 + 新实现，不改推理 / 编排骨架。

## 关键接口（血肉接入点）

| 入口 | 抽象接口 | 血肉接入方式 |
|---|---|---|
| 芯片扫描 | `infrastructure/chip_gateway.py` | 扫 `skills/chips/*/` 目录，自动注册芯片肖像 |
| 引脚分配 | `knowledge/template_forge/chip_portrait_adapter.py` | 读 `profile.json` 的 `pin_map` / `af_map` |
| 模板加载 | `knowledge/template_forge/functional_templates.py` | 读 `forge_templates/*.json` |
| 开发板解析 | `infrastructure/board_resolver.py` | 读 `skills/boards/*/board.json` |

> 这些入口默认走「示意模板」，拿到真实血肉后**不改代码**即可替换——即「做好随时替换的准备」。
> 完整字段格式见 `docs/DATA_SPEC.md`。
