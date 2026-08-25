"""最小可运行示例：文字「点灯」→ 完整生成 STM32 工程。

跑一次：
    python examples/run_example.py

看到「点灯」→ 识别 example_led 模板 → 生成 18 文件完整工程（main/gpio/startup/Makefile/链接脚本）。
用的是「stm32f407zgt6 最小肖像」——真芯片名，但只抠了点灯需要的最小字段（PA5 + 最小时钟），
不是完整 407 引脚（完整肖像是护城河，见 docs/DATA_SPEC.md）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledge.template_forge.functional_assembler import FunctionalAssembler


def main() -> int:
    text = "点灯"
    chip = "stm32f407zgt6"
    r = FunctionalAssembler().assemble_routed(text, chip=chip)
    files = r.get("files", {})

    print("=" * 60)
    print(f"输入文字：{text}    芯片：{chip}")
    print(f"识别命中：{r.get('templates')}")
    print(f"生成文件：{len(files)} 个（完整工程）")
    print("=" * 60)

    if not files:
        print("未生成工程。请确认 forge_templates/functional/ 下有模板。")
        return 1

    for k in sorted(files):
        print(f"  {k}")

    gpio = files.get("agent_forge_board/Core/Src/gpio.c", "")
    print()
    print("生成的 gpio.c 点灯代码（节选）：")
    print("-" * 60)
    for line in gpio.splitlines():
        if "MX_GPIO_Init" in line or "GPIO_InitStruct" in line:
            print("  " + line.strip())
    print("-" * 60)
    print()
    print("这是「文字 → 完整工程」的最小演示。")
    print("完整芯片肖像（全部引脚/外设）见 docs/DATA_SPEC.md，填入即可生成真实外设。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
