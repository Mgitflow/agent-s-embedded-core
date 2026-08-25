# `contracts/` — 区块目录

> 本目录为 `contracts/` 区块。**结构基准见根目录 [WHITELIST.md](../WHITELIST.md)**，
> 任何增删改须先更新白名单，防止结构漂移。

| 子模块 | 职责 |
|--------|------|
| `assessment.py` | 评估层契约 |
| `code_block.py` | 外设代码块数据契约 |
| `enums.py` | 枚举类型 添加全部 14 个扩展外设 |
| `exceptions.py` | Agent-S 统一异常层次 所有业务异常由此派生，替代裸 Exce |
| `generation.py` | 代码生成层契约 |
| `interfaces.py` | 抽象接口契约 |
| `knowledge.py` | 知识层契约 |
| `knowledge_source.py` | 知识源插件接口 |
| `manifest.py` | Agent 能力注册契约。 |
| `peripheral_registry.py` | 外设统一注册表（数据契约薄包装） |
| `planning.py` | 规划层契约 |
| `reflection.py` | 审查层契约 |
