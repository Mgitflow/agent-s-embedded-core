# 功能模板目录 · 最小原型

每个外设一个 JSON 模板。**最少**几个字段：

| 字段 | 作用 |
|---|---|
| `id` | 模板唯一标识 |
| `keywords` | 识别套式（文字 → 模板的匹配词，**固定模板匹配的关键**） |
| `peripheral` | 外设名 |
| `init` | 初始化代码（`${xxx}` 为参数占位符） |

> 这是最小原型。原项目有 14 字段（version/init_func/depends/globals/loop/deinit/params/
> requires_uart），见 `docs/DATA_SPEC.md` §6 参考——**你不必照搬**。骨架 `functional_assembler`
> 通过 `FunctionalTemplateStore` 加载此目录，换你自己的模板（字段够用即可）不改代码。
