"""功能模板库（汉堡夹层）：定义 init→loop→deinit 三段有始有终的完整功能模板，内部变量用模板唯一前缀保证组合零冲突。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# 功能模板库目录（2026-08-19 拔插式：从 config.TEMPLATES_DIR 取，AGENT_S_TEMPLATES_DIR 可替换）
try:
    from infrastructure.config import TEMPLATES_DIR

    _FUNC_DIR = Path(TEMPLATES_DIR) / "functional"
except Exception:  # noqa: BLE001 —— 兜底：config 不可用时退回项目内路径
    _FUNC_DIR = Path(__file__).resolve().parent / "forge_templates" / "functional"


# ────────────────────────── 数量词识别（多实例）──────────────────────────
# 念安 8-20「两个灯」多实例：数量词（两个/2个）修饰的功能重复 N 次，
# 配合 PinAllocator 的「实例标识@引脚」连体冲突检测，区分「两个都叫 LED 的」。
_CN_NUM = {"两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_QUANT_RE = re.compile(r"([两二三四五六七八九十\d]+)\s*(?:个|盏|颗|路|组|只)")


def _parse_quantity(word: str) -> int:
    """数量词 → 数字（两个→2 / 2个→2 / 十→10）。"""
    if word.isdigit():
        return int(word)
    return _CN_NUM.get(word, 1)


def _expand_quantifiers(text: str, tids: list[str]) -> list[str]:
    """数量词识别：两个灯 → [led_blink, led_blink]（多实例）。

    简化规则（核心场景）：数量词 > 1 且仅命中单一功能 → 该功能重复 N 次。
    多功能 + 数量词（两个灯 + 一个按键）的精确关联属三期「优先识别套式」。
    """
    if not text or len(tids) != 1:
        return tids
    m = _QUANT_RE.search(text)
    if not m:
        return tids
    qty = _parse_quantity(m.group(1))
    return tids * qty if qty > 1 else tids


# ────────────────────────── 引脚需求声明 ──────────────────────────
# 2026-08-09 念安拍板：脚本自动识别引脚可能瞎配/撞车 → 占位机制。
# 每个有引脚的模板声明它需要的芯片信号（PinAllocator 按此分配+避让）：
#   "参数键": "信号模板"（{instance}/{channel} 等占位由用户参数填充）
#   "参数键": "@GPIO"  （纯 GPIO 功能：点灯/按键/EXTI，走 GPIO 池分配）
# 信号模板 → ChipPortraitAdapter.get_signal_candidates 取候选（带排序）：
#   候选数量、都是哪些、哪个优先（default 排最前）全部声明清楚。
PIN_REQUIREMENTS: dict[str, dict[str, str]] = {
    "uart_print": {
        "tx_pin": "USART{uart_instance}_TX",
        "rx_pin": "USART{uart_instance}_RX",
    },
    "uart_interrupt": {
        "tx_pin": "USART{uart_instance}_TX",
        "rx_pin": "USART{uart_instance}_RX",
    },
    "uart_dma": {
        "tx_pin": "USART{uart_instance}_TX",
        "rx_pin": "USART{uart_instance}_RX",
    },
    "pwm_output": {"pwm_pin": "TIM{tim_instance}_CH{channel}"},
    "pwm_servo": {"servo_pin": "TIM{tim_instance}_CH{channel}"},
    "tim_input_capture": {"cap_pin": "TIM{tim_instance}_CH{channel}"},
    "spi_master": {
        "spi_sck": "SPI{spi_instance}_SCK",
        "spi_miso": "SPI{spi_instance}_MISO",
        "spi_mosi": "SPI{spi_instance}_MOSI",
    },
    "i2c_scan": {
        "i2c_scl": "I2C{i2c_instance}_SCL",
        "i2c_sda": "I2C{i2c_instance}_SDA",
    },
    "i2c_sensor": {
        "i2c_scl": "I2C{i2c_instance}_SCL",
        "i2c_sda": "I2C{i2c_instance}_SDA",
    },
    "adc_read": {"adc_pin": "ADC{adc_instance}_IN{adc_channel}"},
    "adc_dma_scan": {"adc_pin": "ADC{adc_instance}_IN{adc_ch1}"},
    "dac_output": {"dac_pin": "DAC_OUT{channel}"},
    # 纯 GPIO 功能（无信号复用，走 GPIO 池）
    "led_blink": {"led_pin": "@GPIO"},
    "button_read": {"btn_pin": "@GPIO"},
    "gpio_exti": {"exti_pin": "@GPIO"},
    "gpio_multi_out": {"led_pins_mask": "@GPIO"},
}


# ────────────────────────── 功能模板定义 ──────────────────────────

# 每个模板用 $ 参数化（string.Template 标准库渲染）
# init/loop/deinit 三段：填进 mx_skeleton main.c 框架的对应位置
FUNCTIONAL_TEMPLATES: dict[str, dict[str, Any]] = {

}


class FunctionalTemplateStore:
    """功能模板库：关键字匹配 + 模板读取 + 版本归档。

    模板来源：基础 6 个（FUNCTIONAL_TEMPLATES）+ **JSON 单一权威源**
    （forge_templates/functional/*.json，2026-08-09 起统一；旧 ext 三梯队
    文件已归档至 org-archive/agent-s-template-forge-20260814/，不再引用）。
    """

    def __init__(self, func_dir: Path | str | None = None) -> None:
        self._func_dir = Path(func_dir or _FUNC_DIR)
        self._templates: dict[str, dict[str, Any]] = {}
        self._merge_builtin()
        self._load_disk()
        self._index_keywords()

    def _merge_builtin(self) -> None:
        """加载模板数据（2026-08-09 架构升级：**JSON 单一权威源**）。

        模板数据统一存 forge_templates/functional/*.json（含 globals 段），
        不再维护在 py dict（批量修改源码易坏，教训 2026-08-09）。
        内置 py dict 仅作无 JSON 时的 fallback。
        """
        if FUNCTIONAL_TEMPLATES:
            self._templates.update(FUNCTIONAL_TEMPLATES)
        if self._func_dir.exists():
            for path in sorted(self._func_dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    tid = data.get("id")
                    if tid:
                        self._templates[tid] = data
                except (OSError, json.JSONDecodeError) as exc:
                    _log.debug("FuncStore: JSON 模板加载失败 %s: %s", path, exc)

    def _load_disk(self) -> None:
        """从磁盘加载归档模板（functional/*.json）。

        只增不减 + 版本优先：磁盘上有而**内置没有**的模板才加载（外部新增归档）；
        内置已有的用内置版（更新版优先，避免旧归档覆盖新代码）。
        """
        if not self._func_dir.exists():
            return
        for path in sorted(self._func_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tid = data.get("id")
                if tid and tid not in self._templates:
                    self._templates[tid] = data
            except (OSError, json.JSONDecodeError) as exc:
                _log.debug("FuncStore: 模板加载失败 %s: %s", path, exc)

    def _index_keywords(self) -> None:
        """建立关键字 → 模板 id 索引（小写化，支持多词）。"""
        self._kw_index: dict[str, str] = {}
        for tid, tpl in self._templates.items():
            for kw in tpl.get("keywords", []):
                key = kw.strip().lower()
                if key:
                    self._kw_index[key] = tid

    # ---- 匹配（脚本的智商） ----

    def match(self, text: str) -> str | None:
        """按关键字匹配功能模板。

        优先级：**更长关键字（更具体）优先**——"呼吸灯" > "灯"，
        避免泛关键字（灯/打印）抢走具体功能（PWM 呼吸灯/串口打印）。
        多模板命中取模板定义顺序前者。返回模板 id 或 None。
        """
        if not text:
            return None
        lowered = text.lower()
        # 1. 全词/子串命中收集（带关键字长度，长=具体）
        hits: list[tuple[int, str]] = []  # (kw_len, template_id)
        for kw, tid in self._kw_index.items():
            if kw in lowered:
                hits.append((len(kw), tid))
        if not hits:
            return None
        # 2. 只保留"最长关键字"那一档（最具体），同档按模板定义顺序
        max_len = max(h[0] for h in hits)
        top = [tid for ln, tid in hits if ln == max_len]
        for tid in self._templates:
            if tid in top:
                return tid
        return top[0]

    def match_from_plan(self, plan: Any) -> str | None:
        """从 plan（dict/对象）提取文本片段匹配功能。"""
        texts: list[str] = []
        if isinstance(plan, dict):
            for key in ("intent", "user_input", "description", "reason", "action"):
                v = plan.get(key)
                if isinstance(v, str):
                    texts.append(v)
            # params 里也可能有线索
            params = plan.get("params") or {}
            for v in params.values():
                if isinstance(v, str):
                    texts.append(v)
        else:
            for key in ("intent", "user_input", "description", "reason", "action"):
                v = getattr(plan, key, None)
                if isinstance(v, str):
                    texts.append(v)
        combined = " ".join(t for t in texts if t)
        return self.match(combined)

    def match_all(self, text: str) -> list[str]:
        """识别文本中的**多个**功能（组合用）。

        策略（长关键字先占位 + 同族去重）：
          1. 长关键字优先占位："呼吸灯"被 PWM 占后，"灯"无法再抢
          2. 同外设族（depends[0]）已有命中 → 泛化版让位
          3. 返回模板 id 列表（按模板定义顺序）
        """
        if not text:
            return []
        working = text.lower()
        # 收集所有命中（长度降序）
        hits: list[tuple[int, str, str]] = []  # (kw_len, template_id, keyword)
        for tid, tpl in self._templates.items():
            for kw in tpl.get("keywords", []):
                key = kw.strip().lower()
                if key and key in working:
                    hits.append((len(key), tid, key))
        hits.sort(key=lambda x: -x[0])

        occupied: set[str] = set()
        occupied_ranges: list[tuple[int, int]] = []  # (start, end) 已占区间
        for _kw_len, tid, key in hits:
            pos = working.find(key)
            if pos == -1:
                continue
            # 与已占区间重叠则跳过（子串冲突：呼吸灯占位后，灯不可再抢）
            if any(pos < end and pos + len(key) > start for start, end in occupied_ranges):
                continue
            # 同族泛化去重：同一族（depends[0]）且关键词有子串包含关系 → 泛化版让位
            # （「采样」⊂「多通道采样」才让位；「点灯」vs「按键」无包含关系不去重）
            if self._same_peri_family_conflict(tid, key, occupied):
                continue
            occupied.add(tid)
            occupied_ranges.append((pos, pos + len(key)))
            # 划掉关键字位置（防止后续重复）
            working = working[:pos] + " " * len(key) + working[pos + len(key):]
        # 按模板定义顺序输出；数量词识别（念安 8-20「两个灯」多实例）→ 重复该功能
        result = [tid for tid in self._templates if tid in occupied]
        return _expand_quantifiers(text, result)

    def _same_peri_family_conflict(self, tid: str, key: str, occupied: set[str]) -> bool:
        """同外设族 + 关键词子串包含 → 当前泛化版让位给更具体的。

        2026-08-17 修复：原判据只看 depends[0] 相同就去重，误伤「点灯+按键」
        （同 gpio 族但功能完全不同）。新判据要求**关键词有子串包含关系**
        （「采样」⊂「多通道采样」）才构成泛化→具体，才去重。
        """
        family = (self._templates.get(tid, {}).get("depends") or [None])[0]
        if family is None or not occupied:
            return False
        for other in occupied:
            if other == tid:
                continue
            other_family = (self._templates.get(other, {}).get("depends") or [None])[0]
            if other_family != family:
                continue
            # 同族：仅当关键词有子串包含关系（泛化 vs 具体）才去重
            for ok in self._templates.get(other, {}).get("keywords", []):
                ok_l = ok.lower()
                if key in ok_l or ok_l in key:
                    return True
        return False

    # ---- 模板读取 ----

    def get(self, template_id: str) -> dict[str, Any] | None:
        tpl = self._templates.get(template_id)
        if tpl is None:
            return None
        return dict(tpl)  # 浅拷贝防外部污染

    def list_templates(self) -> list[str]:
        return list(self._templates.keys())

    def list_keywords(self) -> dict[str, str]:
        return dict(self._kw_index)

    def render(self, template_id: str, params: dict[str, Any]) -> dict[str, Any]:
        """渲染模板三段（init/loop/deinit/globals），返回 {段名: 代码}。

        globals = 句柄全局声明（CubeMX 风格：init 填、deinit 用，作用域全局）。
        system_level = 系统保命声明（材料驱动，非代码硬编码外设名）。
        """
        from string import Template as StrTemplate

        tpl = self.get(template_id)
        if tpl is None:
            raise KeyError(f"功能模板不存在: {template_id}")
        # 参数补齐（meta 默认值）
        filled = dict(params)
        for key, cfg in tpl.get("params", {}).items():
            if key not in filled and "default" in cfg:
                filled[key] = cfg["default"]
        result: dict[str, Any] = {}
        # 外设名（外设文件分组 + hal_msp.c 归属；v2 模板必备，v1 兜底从 depends 推断）
        result["peripheral"] = str(tpl.get("peripheral", "") or "")
        # 防御需求声明（2026-08-23 念安「按环节绑定」）：功能模板声明这个环节需要哪些
        # 防御件，组装层按声明注入对应文件——不是全局默认开，是绑到具体环节。
        result["defense"] = ",".join(str(d) for d in (tpl.get("defense", []) or []))
        # 2026-08-17 MX 范式：init_func/deinit_func 是配置函数名（main 只调用，函数体独立定义）。
        # 可含 ${instance} 占位符（CubeMX 风 MX_USART${uart_instance}_UART_Init），随 init 一起参数化。
        for key in ("init_func", "deinit_func"):
            raw = str(tpl.get(key, "") or "")
            if not raw:
                result[key] = ""
                continue
            try:
                result[key] = StrTemplate(raw).substitute(filled)
            except KeyError:
                result[key] = StrTemplate(raw).safe_substitute(filled)
        for section in ("globals", "init", "loop", "deinit", "extra_code"):
            raw = tpl.get(section, "")
            if not raw:
                result[section] = ""
                continue
            try:
                result[section] = StrTemplate(raw).substitute(filled)
            except KeyError:
                result[section] = StrTemplate(raw).safe_substitute(filled)
        # 系统保命声明（念安 2026-08-24「改全面」）：模板声明 system_level=true → loop 是保命逻辑
        # （看门狗喂狗/系统软复位），组装层据此提升到应用层无条件跑，不被启动门门控。
        # 材料驱动，不再靠 project_slicer 硬编码外设名判断「谁是保命」。
        result["system_level"] = bool(tpl.get("system_level"))
        # 无源回传 / 有源关闭动作（念安 2026-08-25）：requires_uart（有结果要串口回传）与
        # off（有源器件「关」动作）也透传到 bundle，project_slicer 据此分「无条件区 vs
        # 启动门门控区」——requires_uart 且无 off 的无源回传（RNG/CRC/DMA/定时器/DAC）
        # 上电即回传，不被启动门挡住（自动测试无按键）。
        result["requires_uart"] = bool(tpl.get("requires_uart"))
        result["off"] = str(tpl.get("off", "") or "")
        # 芯片级联（连接效果）：functional 模板也可声明 cascade（宿主 = 同阵营外设），
        # 与开发板级联共用同一套渲染机制（camp=chip 标识芯片阵营，2026-08-25）。
        cascade = tpl.get("cascade")
        result["cascade"] = cascade
        if cascade:
            from knowledge.template_forge.cascade import render_cascade

            result["init"], result["loop"], result["off"] = render_cascade(
                result["init"], result["loop"], result["off"], cascade
            )
        return result

    # ---- 归档 ----

    def archive(self, template: dict[str, Any], out_dir: Path | str | None = None) -> Path:
        """归档模板到磁盘（functional/<id>.json，只增不减）。"""
        out = Path(out_dir or self._func_dir)
        out.mkdir(parents=True, exist_ok=True)
        tid = template.get("id", "unknown")
        path = out / f"{tid}.json"
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def archive_all(self, out_dir: Path | str | None = None) -> int:
        """归档全部内置模板。返回归档数量。"""
        count = 0
        for _tid, tpl in self._templates.items():
            self.archive(tpl, out_dir)
            count += 1
        return count



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store = FunctionalTemplateStore()
    print("功能模板:", store.list_templates())
    print("关键字数:", len(store.list_keywords()))
    print("匹配'点灯':", store.match("帮我写一个点灯的程序"))
    print("匹配'PWM 呼吸灯':", store.match("做一个 PWM 呼吸灯"))
    print("匹配'串口打印日志':", store.match("串口打印日志"))
    print("匹配'复位系统':", store.match("系统复位"))
    print("匹配'无功能':", store.match("今天天气不错"))
    bundle = store.render("led_blink", {"led_port": "A", "led_pin": "5"})
    print("=== led_blink init ===")
    print(bundle["init"])
    print("=== led_blink loop ===")
    print(bundle["loop"])
