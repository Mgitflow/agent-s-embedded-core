"""引脚分配器：全局引脚占用表 + 候选排序 + 自动避让（首选被占→下一个候选），并把分配结果生成 CubeMX 风格 AF 复用段注入模板。"""

from __future__ import annotations

import logging
from typing import Any

from knowledge.template_forge.chip_portrait_adapter import DEFAULT_CHIP, ChipPortraitAdapter

_log = logging.getLogger(__name__)

# GPIO 通用引脚池（点灯/按键/EXTI 等纯 GPIO 功能优先分配）
_GPIO_POOL = ["PA5", "PA6", "PA7", "PB0", "PB1", "PC13", "PD2", "PE0", "PE1", "PE2"]


class PinAllocator:
    """引脚分配器：全局占用表 + 候选排序 + 自动避让（占位机制）。"""

    def __init__(self, adapter: ChipPortraitAdapter | None = None, chip: str = DEFAULT_CHIP) -> None:
        self._adapter = adapter or ChipPortraitAdapter(chip=chip)
        self._occupied: dict[str, str] = {}  # pin -> owner（模板/信号）
        self._allocations: dict[str, str] = {}  # signal -> pin
        self._gpio_allocations: dict[str, str] = {}  # owner -> pin（GPIO 池）
        self._conflicts: list[str] = []  # 避让日志（要标明）
        self._remapped: set[str] = set()  # 已注入 AFIO remap 的外设前缀（f103，去重）
        self._afio_clk_enabled: bool = False  # AFIO 时钟是否已注入（全局一次）

    # ---- 查询 ----

    def is_occupied(self, pin: str) -> bool:
        return pin.upper() in self._occupied

    def owner_of(self, pin: str) -> str | None:
        tmp = self._occupied.get(pin.upper())
        return tmp if isinstance(tmp, str) else ""

    def allocated_pins(self) -> dict[str, str]:
        """当前占用表快照（pin → owner）。"""
        return dict(self._occupied)

    def conflict_log(self) -> list[str]:
        return list(self._conflicts)

    def has_conflicts(self) -> bool:
        return bool(self._conflicts)

    # ---- 占用 ----

    def occupy(self, pin: str, owner: str) -> bool:
        """登记占用。返回 True=占用成功；False=已被别人占用。"""
        key = pin.upper()
        if key in self._occupied and self._occupied[key] != owner:
            self._conflicts.append(f"{owner}: 引脚 {key} 已被 {self._occupied[key]} 占用")
            return False
        self._occupied[key] = owner
        return True

    def release(self, pin: str) -> None:
        self._occupied.pop(pin.upper(), None)

    # ---- 信号分配（含避让） ----

    def allocate(self, signal: str, owner: str, preferred: str | None = None) -> str | None:
        """按信号分配引脚（**占位机制核心**）。

        规则：
          1. 同一信号已分配过 → 返回原引脚（不重复占）
          2. 用户首选（preferred）未被占 → 用首选
          3. 首选被占 → **自动避让**到下一个候选（记录冲突日志）
          4. 全部候选被占 → 记录无可选，返回 None

        Returns: 分配的引脚（大写，如 "PA9"）或 None。
        """
        sig = signal.upper()
        if sig in self._allocations:
            return self._allocations[sig]
        if preferred:
            pref = str(preferred).upper()
            if not self.is_occupied(pref):
                self.occupy(pref, owner)
                self._allocations[sig] = pref
                return pref
            self._conflicts.append(
                f"{owner}: {sig} 首选 {pref} 已被 {self.owner_of(pref) or '其他功能'} 占用，自动避让"
            )
        for cand in self._adapter.get_signal_candidates(sig):
            pin = cand["pin"]
            if not self.is_occupied(pin):
                self.occupy(pin, owner)
                self._allocations[sig] = pin
                tmp = pin
                return tmp if isinstance(tmp, str) else ""
        self._conflicts.append(f"{owner}: {sig} 无可选引脚（候选全部被占）")
        return None

    def allocate_gpio(self, owner: str, preferred: str | None = None) -> str | None:
        """GPIO 通用引脚分配（点灯/按键/EXTI 等无信号复用的功能）。

        规则：用户首选未被占 → 首选；否则从空闲池按序取第一个。
        """
        if owner in self._gpio_allocations:
            return self._gpio_allocations[owner]
        if preferred:
            pref = str(preferred).upper()
            if not self.is_occupied(pref):
                self.occupy(pref, owner)
                self._gpio_allocations[owner] = pref
                return pref
            self._conflicts.append(
                f"{owner}: 引脚 {pref} 已被 {self.owner_of(pref) or '其他功能'} 占用，自动避让"
            )
        for pin in _GPIO_POOL:
            if not self.is_occupied(pin):
                self.occupy(pin, owner)
                self._gpio_allocations[owner] = pin
                return pin
        self._conflicts.append(f"{owner}: GPIO 池全部被占")
        return None

    # ---- 复用段生成（分配结果 → CubeMX 风格 GPIO 代码） ----

    def build_pin_mux(self, signal: str, pin: str, var_prefix: str) -> str:
        """生成单个信号的标准 GPIO 复用代码块（CubeMX 风格）。

        Example:
            build_pin_mux("USART1_TX", "PA9", "uart")
            -> "  __HAL_RCC_GPIOA_CLK_ENABLE();\\n"
               "  GPIO_InitTypeDef uart_tx_gpio_init = {0};\\n"
               "  uart_tx_gpio_init.Pin = GPIO_PIN_9;\\n"
               "  uart_tx_gpio_init.Mode = GPIO_MODE_AF_PP;\\n"
               "  ... HAL_GPIO_Init(GPIOA, &uart_tx_gpio_init);"

        ADC/DAC 信号用 GPIO_MODE_ANALOG（无 AF）。
        """
        pin = pin.upper()
        if not pin.startswith("P") or len(pin) < 3:
            return ""
        port = pin[1]          # PA9 → A
        pin_no = pin[2:]       # PA9 → 9
        if not pin_no.isdigit():
            return ""
        # F1 的 GPIO_InitTypeDef 无 Alternate 字段（AF 复用隐式，Mode=AF_PP 即可）；
        # F4/G4 需显式 Alternate = GPIO_AFx_XXX。材料驱动（family.json 的 gpio_alternate）。
        from infrastructure.chip_family import get_family

        is_f1 = not get_family(getattr(self._adapter, "_chip", "")).gpio_alternate
        # 变量名含完整信号（SCL/SDA/SCK/MISO 区分）——防同模板多信号重复声明
        sig_key = signal.lower().replace("_", "")
        var = f"{var_prefix}_{sig_key}_gpio_init"
        lines = [f"  __HAL_RCC_GPIO{port}_CLK_ENABLE();", f"  GPIO_InitTypeDef {var} = {{0}};"]
        # f103 AFIO 重映射（遗漏①落地）：选重映射引脚时，须先配置 AFIO_MAPR
        # 重映射位（__HAL_AFIO_REMAP_XXX），否则引脚不通。AFIO 时钟 + 宏每个外设只注入一次
        # （重复 SET_BIT 幂等但冗余，去重更干净）。放 GPIO init 之前（先 remap 再配 GPIO）。
        remap_macros = self._adapter.get_remap_macros(signal, pin)
        remap_prefix: list[str] = []
        if remap_macros and is_f1:
            # AFIO 时钟全局一次；remap 宏每个外设一次（重复 SET_BIT 幂等但冗余）
            if not self._afio_clk_enabled:
                remap_prefix.append("  __HAL_RCC_AFIO_CLK_ENABLE();")
                self._afio_clk_enabled = True
            peri = signal.rsplit("_", 1)[0] if "_" in signal else signal
            if peri not in self._remapped:
                remap_prefix.append(f"  {remap_macros[0]}();")
                self._remapped.add(peri)
        lines = remap_prefix + lines
        lines.append(f"  {var}.Pin = GPIO_PIN_{pin_no};")
        if self._adapter.is_analog_signal(signal):
            lines.append(f"  {var}.Mode = GPIO_MODE_ANALOG;")
        else:
            af = self._adapter.get_af_for_signal(signal)
            lines.append(f"  {var}.Mode = GPIO_MODE_AF_PP;")
            lines.append(f"  {var}.Pull = GPIO_NOPULL;")
            lines.append(f"  {var}.Speed = GPIO_SPEED_FREQ_HIGH;")
            if not is_f1:
                af_macro = f"GPIO_AF{af}_{signal.rsplit('_', 1)[0]}" if af else "GPIO_AF0"
                lines.append(f"  {var}.Alternate = {af_macro};")
        lines.append(f"  HAL_GPIO_Init(GPIO{port}, &{var});")
        return "\n".join(lines) + "\n"

    def resolve_template_pins(
        self,
        template_id: str,
        seg_params: dict[str, Any],
        pin_reqs: dict[str, str],
        owner: str | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """按模板的引脚需求声明分配引脚并生成复用段。

        Args:
            template_id: 功能模板 id（如 "uart_print"）
            seg_params:  该模板的参数（含用户显式指定）
            pin_reqs:    模板引脚需求（参数键 → 信号模板或 "@GPIO"）
                         例: {"tx_pin": "USART{uart_instance}_TX", "led_pin": "@GPIO"}
            owner:       实例标识（多实例场景：led_blink#1 / led_blink#2），
                         缺省 = template_id。「名字@引脚」连体：owner 即「名字」，
                         两个都叫 LED 的用不同 owner 区分，各自独立占角（不互相复用引脚）。

        Returns:
            (新参数（含分配引脚）, 复用段代码, 冲突日志)
        """
        owner = owner or template_id
        filled = dict(seg_params)
        # 补模板 schema 默认值（信号模板 format 需要，与渲染默认一致）
        try:
            from knowledge.template_forge.functional_templates import FunctionalTemplateStore

            tpl = FunctionalTemplateStore().get(template_id)
            if tpl:
                for key, spec in (tpl.get("params") or {}).items():
                    if key not in filled and isinstance(spec, dict):
                        filled[key] = spec.get("default")
        except Exception:  # noqa: BLE001 —— 模板缺失不影响分配
            pass
        mux_parts: list[str] = []
        new_conflicts: list[str] = []
        for param_key, signal_tpl in pin_reqs.items():
            if signal_tpl == "@GPIO":
                # GPIO 通用引脚：用户可能只给引脚号（9），port 默认 A → 拼成 PA9
                preferred = filled.get(param_key)
                port_key = param_key.replace("_pin", "_port")
                port = filled.get(port_key, "A")
                if preferred and not str(preferred).startswith("P"):
                    preferred = f"P{port}{preferred}"
                pin = self.allocate_gpio(owner, preferred)
                if pin:
                    # 拆回模板期望形态：PA9 → led_pin=9 + led_port=A
                    filled[param_key] = str(pin)[2:] if str(pin).startswith("P") else str(pin)
                    filled[port_key] = str(pin)[1]
                continue
            # 信号模板：{uart_instance} 等占位用参数填充
            try:
                signal = signal_tpl.format(**{k: v for k, v in filled.items() if v is not None})
            except (KeyError, ValueError) as exc:
                new_conflicts.append(f"{template_id}: 信号模板 {signal_tpl} 缺参数: {exc}")
                continue
            preferred = filled.get(param_key)
            pin = self.allocate(signal, owner, preferred)
            if pin:
                filled[param_key] = pin
                mux_parts.append(self.build_pin_mux(signal, pin, template_id.split("_")[0]))
        # 派生 port/pin_no（模板 GPIO_PIN_x 生成需要）
        for key in list(filled.keys()):
            if key.endswith("_pin") and filled[key]:
                self._derive_pin_parts(filled, key[:-4])
        new_conflicts.extend(self._conflicts[len(new_conflicts):])
        return filled, "\n".join(mux_parts), new_conflicts

    @staticmethod
    def _derive_pin_parts(filled: dict[str, Any], prefix: str) -> None:
        """从 {prefix}_pin（PA9）派生 {prefix}_port（A）和 {prefix}_pin_no（9）。

        修正：**强制重派生**——引脚参数是权威，分配器避让后
        引脚变了，port/pin_no 必须跟着更新（否则模板复用段还是旧引脚）。
        """
        pin = filled.get(f"{prefix}_pin")
        if not pin or not str(pin).startswith("P"):
            return
        filled[f"{prefix}_port"] = str(pin)[1]
        filled[f"{prefix}_pin_no"] = str(pin)[2:]


def allocate_pins_for_combination(
    template_ids: list[str],
    params: dict[str, Any],
    pin_reqs: dict[str, dict[str, str]],
    chip: str = DEFAULT_CHIP,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """组合拼装的引脚预分配入口。

    按模板顺序逐功能分配引脚（先分配的先占，后分配的避让），
    返回 (template_id → 分配后参数, 冲突日志)。

    Example:
        template_ids=["led_blink","uart_print"], params={"led_pin":"5","uart_instance":"1"}
        -> 分配结果: led_blink 占 PA5，uart_print 自动取 PA9/PA10
    """
    allocator = PinAllocator(chip=chip)
    result: dict[str, dict[str, Any]] = {}
    for tid in template_ids:
        seg = dict(params or {})
        reqs = pin_reqs.get(tid, {})
        if reqs:
            filled, _mux, _conf = allocator.resolve_template_pins(tid, seg, reqs)
            seg = filled
        result[tid] = seg
    return result, allocator.conflict_log()
