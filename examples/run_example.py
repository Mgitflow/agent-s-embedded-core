"""最小可运行示例：演示「文字 → 识别 → 渲染」核心链路。

跑一次：
    python examples/run_example.py

你会看到「点灯」被识别到 example_led 模板，渲染出 GPIO 点灯代码——这就是骨架的核心链路，
不碰任何护城河内容数据。

完整「生成工程」（文字 → 可烧录工程）需要填入完整芯片肖像，见 docs/DATA_SPEC.md。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledge.template_forge.functional_templates import FunctionalTemplateStore


def main() -> int:
    store = FunctionalTemplateStore()
    text = "点灯"
    tid = store.match(text)

    print("=" * 60)
    print(f"输入文字：{text}")
    print(f"识别命中：{tid or '(未命中)'}")
    print("=" * 60)

    if tid is None:
        print("未识别到模板。请确认 forge_templates/functional/ 下有模板。")
        return 1

    r = store.render(tid, {})
    print(f"外设：{r['peripheral']}")
    print("渲染出的 init 代码：")
    print("-" * 60)
    print(r["init"].rstrip())
    print("-" * 60)
    print()
    print("这是「识别 → 渲染」链路的最小演示。")
    print("完整「生成工程」需填入完整芯片肖像（见 docs/DATA_SPEC.md）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
