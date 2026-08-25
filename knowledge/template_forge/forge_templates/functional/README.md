# 功能模板目录

每个外设一个 JSON 模板，14 字段（见 `docs/DATA_SPEC.md` §6）：

`id` / `version` / `peripheral` / `init_func` / `deinit_func` / `keywords` /
`description` / `depends` / `globals` / `init` / `loop` / `deinit` / `params` / `requires_uart`

- `keywords` 是识别套式（文字 → 模板的匹配词），是「固定模板匹配」的关键。
- `init` 里的 `${xxx}` 是参数占位符，由骨架 `param_filler` 按 `params` 定义填充。
- 本目录 `_example.json` 是空模板，真实模板数据是**内容护城河，不开源**。

> 骨架 `functional_assembler` 通过 `FunctionalTemplateStore` 加载此目录，
> 换成你自己的模板 JSON（保持 14 字段），**不改代码**即可接入新外设。
