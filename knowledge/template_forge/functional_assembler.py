"""功能模板拼装器：把功能模板 init/loop/deinit 三段按序搭进 mx_skeleton 框架（汉堡组装），产出有始有终的工程级代码。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from infrastructure.config import DEFAULT_CHIP_NAME
from knowledge.template_forge.chip_portrait_adapter import DEFAULT_CHIP
from knowledge.template_forge.functional_templates import PIN_REQUIREMENTS, FunctionalTemplateStore
from knowledge.template_forge.pin_allocator import PinAllocator

_log = logging.getLogger(__name__)


class FunctionalAssembler:
    """功能模板拼装器：三段式（init/loop/deinit）→ 完整工程代码。"""

    def __init__(self, store: FunctionalTemplateStore | None = None) -> None:
        self._store = store or FunctionalTemplateStore()

    # ---- 主入口 ----

    def assemble(
        self,
        template_id: str,
        params: dict[str, Any] | None = None,
        skeleton_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """拼装完整工程代码。

        引脚占位机制（2026-08-09 念安拍板）：单功能路径也走 PinAllocator——
        渲染前按模板 PIN_REQUIREMENTS 分配引脚（用户指定优先，肖像兜底），
        缺复用段的模板自动注入 CubeMX 风格 GPIO 段（补全"照着范本打"的
        第五段——句柄/时钟/参数/校验/引脚复用）。

        Returns:
            {"main_c": "...", "sections": {...}, "conflicts": [...]} 或 None（模板缺失）
        """
        tpl = self._store.get(template_id)
        if tpl is None:
            return None
        # 引脚占位分配 + 复用段生成
        seg_params = dict(params or {})
        mux_code = ""
        conflicts: list[str] = []
        reqs = PIN_REQUIREMENTS.get(template_id, {})
        if reqs:
            from knowledge.template_forge.chip_portrait_adapter import DEFAULT_CHIP

            chip = skeleton_context.get("chip") if skeleton_context else None
            allocator = PinAllocator(chip=chip or DEFAULT_CHIP)
            seg_params, mux_code, _conf = allocator.resolve_template_pins(template_id, seg_params, reqs)
            conflicts = allocator.conflict_log()
        sections = self._store.render(template_id, seg_params)
        if mux_code and "__HAL_RCC_GPIO" not in sections.get("init", ""):
            sections = dict(sections)
            sections["init"] = str(sections.get("init", "")).rstrip() + "\n" + mux_code
        main_c = self._render_main_c([sections], (skeleton_context or {}).get("chip", ""))
        return {"main_c": main_c, "sections": sections, "conflicts": conflicts}
    def assemble_from_text(self, text: str, params: dict[str, Any] | None = None) -> dict[str, str] | None:
        """从自然语言/意图文本自动匹配功能模板并拼装（脚本兜底路径）。"""
        tid = self._store.match(text)
        if tid is None:
            return None
        # 默认值自动填充层（念安 8-21）：识别层 + 电气填数 + 电气默认打底，统一入口
        from knowledge.template_forge.param_filler import ParameterFiller

        merged = ParameterFiller().fill([tid], params, text)
        return self.assemble(tid, merged)

    # ---- 多功能组合（复杂逻辑核心，2026-08-09 念安拍板） ----

    def _render_functional_bundles(
        self,
        text: str,
        chip: str,
        template_ids: list[str],
        params: dict[str, Any] | None = None,
        relations: dict[str, Any] | None = None,
        reserved_pins: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        """渲染 functional 模板 → bundles（引脚占位分配 + 控制关系联动）。

        从 assemble_multi 抽出的 bundle 生成层（2026-08-24 架构重构）：让 board 与
        functional 的 bundle 能统一合并（识别套式混合需求缺陷的根修）。

        reserved_pins：预先占用的引脚（board 定型引脚）。functional 的 PinAllocator
        分配时自动避让这些引脚——board + functional 混合时引脚不撞车（架构协调，非打补丁）。

        Returns:
            (bundles, used_ids, conflicts)
        """
        bundles: list[dict[str, Any]] = []
        used: dict[str, dict[str, Any]] = {}
        # 默认值自动填充层（念安 8-21「默认值打底 + 精准定位 + 差啥补啥」）：
        # 识别层抠参数（电气 + 引脚）+ 电气填数 + 电气默认打底（芯片自适应），统一入口。
        from knowledge.template_forge.param_filler import ParameterFiller

        params = ParameterFiller(chip).fill(template_ids, params, text)
        allocator = PinAllocator(chip=chip)
        # board 定型引脚预占（混合需求协调）：functional 分配引脚时避让，杜绝撞车
        if reserved_pins:
            for pin in reserved_pins:
                allocator.occupy(str(pin), "board")
        conflicts: list[str] = []
        seen_instances: dict[str, int] = {}  # 实例计数（念安 8-20「两个灯」多实例）
        for tid in template_ids:
            tpl = self._store.get(tid)
            if tpl is None:
                continue
            used[tid] = tpl
            # 实例标识：重复的 template_id 加序号（led_blink → led_blink#1/led_blink#2），
            # 让「两个都叫 LED 的」各自独立占角（连体冲突检测的「名字」，见 PinAllocator.owner）
            seen_instances[tid] = seen_instances.get(tid, 0) + 1
            owner = tid if seen_instances[tid] == 1 else f"{tid}#{seen_instances[tid]}"
            # 每个功能的参数按需取（组合时只取相关前缀参数）
            seg_params = self._slice_params(tid, params)
            # 同功能多实例显式引脚：列表参数按实例序号拆单值（念安 8-20「两个灯 PA5 和 PA3」）。
            # 第 0 个实例取第 0 个角、第 1 个实例取第 1 个角；实例数多于角数时走默认/池分配。
            inst_idx = seen_instances[tid] - 1
            for _k in list(seg_params):
                _val = seg_params[_k]
                if isinstance(_val, list):
                    seg_params[_k] = _val[inst_idx] if inst_idx < len(_val) else None
            # 引脚占位分配（前占后避）：需求声明 → 分配 → 生成复用段
            mux_code = ""
            reqs = PIN_REQUIREMENTS.get(tid, {})
            if reqs:
                seg_params, mux_code, _conf = allocator.resolve_template_pins(tid, seg_params, reqs, owner=owner)
            rendered = self._store.render(tid, seg_params)
            # ── 控制关系联动（2026-08-09：按键控制点灯 → 真接线）──
            # 控制模板（button_read）的 ${btn_action_code} 插槽 = 被控模板动作。
            # 关键：插槽替换必须在**渲染前**（渲染时 safe_substitute 会把缺失
            # 插槽清空），所以直接改 tpl 原始文本再交给 store.render。
            if relations and tid in relations:
                controls = (relations.get(tid) or {}).get("controls", [])
                if controls:
                    action_parts: list[str] = []
                    for ctl_tid in controls:
                        ctl_tpl = self._store.get(ctl_tid)
                        if ctl_tpl is None:
                            continue
                        # 被控模板用实际引脚参数渲染出动作代码
                        ctl_params = self._slice_params(ctl_tid, params)
                        ctl_reqs = PIN_REQUIREMENTS.get(ctl_tid, {})
                        if ctl_reqs:
                            ctl_params, _, _ = allocator.resolve_template_pins(ctl_tid, ctl_params, ctl_reqs)
                        try:
                            ctl_rendered = self._store.render(ctl_tid, ctl_params)
                            ctl_action = ctl_rendered.get("loop", "")
                            # 去掉独立延时（动作一次性执行，不闪烁循环）
                            ctl_action = re.sub(r"\n?\s*HAL_Delay\([^)]*\);", "", ctl_action)
                            if ctl_action.strip():
                                action_parts.append(ctl_action.strip())
                        except Exception:  # noqa: BLE001
                            pass
                    if action_parts:
                        action_code = "\n".join(action_parts)
                        # 直接改原始模板文本（渲染前替换插槽）
                        tpl = dict(tpl)
                        for sec in ("loop", "init", "deinit"):
                            cur = tpl.get(sec, "")
                            if "${btn_action_code}" in cur:
                                tpl[sec] = cur.replace("${btn_action_code}", action_code).replace(
                                    "/* 按键按下：${btn_action} */", "/* 按键按下：触发控制动作 */"
                                )
                        # 用改过的模板重新渲染（store.render 支持外部模板对象）
                        rendered = self._render_with_template(tpl, seg_params)
            # 模板缺引脚复用段 → 追加（补全工程完整性；自带复用段不重复）
            if mux_code and "__HAL_RCC_GPIO" not in rendered.get("init", ""):
                rendered = dict(rendered)
                rendered["init"] = str(rendered.get("init", "")).rstrip() + "\n" + mux_code
            bundles.append(rendered)
        if not used:
            return [], [], conflicts
        conflicts.extend(allocator.conflict_log())
        return bundles, list(used.keys()), conflicts

    def assemble_multi(
        self,
        text: str,
        params: dict[str, Any] | None = None,
        template_ids: list[str] | None = None,
        chip: str = DEFAULT_CHIP,
        relations: dict[str, Any] | None = None,
        logic_code: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """多功能组合拼装：'既要点灯又要串口打印' → 多模板段合并 → 完整工程。

        匹配策略：
          - template_ids 显式给出 → 按序组合
          - 否则从 text 用 store.match_all 识别多个功能（点灯+串口+...）
        合并规则（有始有终）：
          - init 段：按功能顺序拼接（各自初始化）
          - loop 段：合并进 while(1)（多个功能轮询）
          - deinit 段：按反序拼接（后初始化先收尾）
        **引脚占位机制**（2026-08-09 念安拍板）：
          逐功能用 PinAllocator 分配引脚——先分配的先占，后分配的
          自动避让（首选被占 → 下一个候选），杜绝撞车；冲突日志
          进返回值的 "conflicts"（念安：要标明）。
        **逻辑关系注入**（2026-08-09 接通 prompt_composer 断点）：
          relations = {模板: {"controls": [...], "reports": [...]}}
          logic_code = {"a_controls_b": "C 代码片段"}
          识别"按键控制点灯"这类关系 → 控制逻辑注入 loop 段（条件触发）。
        """
        if not template_ids:
            template_ids = self._store.match_all(text) if text else []
        if not template_ids:
            return None

        bundles, used_ids, conflicts = self._render_functional_bundles(
            text, chip, template_ids, params, relations
        )
        if not bundles:
            return None

        combined: dict[str, Any] = {}
        if any(b.get("globals") for b in bundles):
            combined["globals"] = "\n".join(str(b["globals"]) for b in bundles if b.get("globals"))
        if any(b.get("init") for b in bundles):
            combined["init"] = "\n".join(str(b["init"]) for b in bundles if b.get("init"))
        if any(b.get("loop") for b in bundles):
            combined["loop"] = "\n".join(str(b["loop"]) for b in bundles if b.get("loop"))
        # 逻辑关系兜底注入（2026-08-09 复查修正）：
        # 只注入**可编译**的逻辑片段——含占位注释（/* xxx 触发条件 */）或
        # 未渲染插槽（${）的伪代码一律丢弃（真接线已在渲染循环内完成）。
        if logic_code:
            logic_parts = []
            for v in logic_code.values():
                if not v:
                    continue
                if "${" in v:  # 未渲染插槽 = 伪逻辑
                    continue
                if "触发条件" in v:  # 占位触发条件壳 = 伪逻辑
                    continue
                logic_parts.append(v)
            if logic_parts and bundles:
                bundles[-1] = dict(bundles[-1])
                # strip("\n") 只去首尾换行，保留 loop 首行前导缩进（.strip() 会吃首行 4 空格）
                bundles[-1]["loop"] = (str(bundles[-1].get("loop", "") or "") + "\n" + "\n".join(logic_parts)).strip("\n")
                combined["loop"] = str(bundles[-1]["loop"])
        deinit_bodies = [str(b["deinit"]) for b in bundles if b.get("deinit")]
        if deinit_bodies:
            combined["deinit"] = "\n\n".join(reversed(deinit_bodies))  # 反序收尾（旧视图，函数定义顺序无关）
        # 函数名并行列表（供 CLine/整合器 MX 包裹：init_funcs/deinit_funcs 与 bundles 顺序一致）
        combined["init_funcs"] = [str(b.get("init_func", "") or "") for b in bundles]
        combined["deinit_funcs"] = [str(b.get("deinit_func", "") or "") for b in bundles]
        main_c = self._render_main_c(bundles, chip)
        return {
            "main_c": main_c,
            "sections": combined,
            "bundles": bundles,
            "templates": used_ids,
            "conflicts": conflicts,
        }

    def assemble_board_project(
        self,
        text: str,
        chip: str = DEFAULT_CHIP_NAME,
        project_name: str = "agent_forge_board",
    ) -> dict[str, Any] | None:
        """开发板简单逻辑模板 → 简化 main.c 工程（念安 8-20「简单逻辑模板」= 快速出活）。

        本方法走 board.json 的简单逻辑模板（定型引脚/有效电平，照开发板手册填），
        渲染成 MX_xxx_Init 函数体 + loop，生成**单文件 main.c**（能编译、能上板跑，
        不拆外设文件）。

        触发（念安 8-20 拍板「复用 chip、不加 board」）：chip → board.json →
        simple_templates → 匹配需求 → 定型代码。非开发板芯片（无简单逻辑模板）→ 返回
        None（调用方回落 functional 通用 / assemble_routed）。
        """
        from knowledge.template_forge.board_simple import render_board_simple

        simple = render_board_simple(text, chip)
        if simple is None:
            return None
        bundle = self._simple_to_bundle(simple)
        main_c = self._render_main_c([bundle], chip)
        return {
            "files": {f"{project_name}/Core/Src/main.c": main_c},
            "project_name": project_name,
            "templates": [str(simple.get("id", ""))],
            "conflicts": [],
        }

    @staticmethod
    def _simple_to_bundle(simple: dict[str, Any]) -> dict[str, Any]:
        """简单逻辑模板渲染结果 → bundle（init_func/deinit_func 推断 + helpers→extra_code）。

        定型代码包成 bundle，走 _render_main_c（bundles_to_mx_slots 不重新渲染，
        直接套用定型 init/loop）。
        """
        peripheral = str(simple.get("peripheral", "GPIO"))
        # init_func/deinit_func 优先用模板显式声明的（如 MX_USART1_UART_Init 带实例号），
        # 否则按 peripheral 推断（GPIO → MX_GPIO_Init，其他 → MX_{PERIPH}_Init）。
        if simple.get("init_func"):
            init_func = str(simple["init_func"])
            deinit_func = str(simple.get("deinit_func") or "")
        elif peripheral == "GPIO":
            init_func, deinit_func = "MX_GPIO_Init", "MX_GPIO_DeInit"
        else:
            init_func, deinit_func = f"MX_{peripheral}_Init", f"MX_{peripheral}_DeInit"
        return {
            "peripheral": peripheral,
            "defense": simple.get("defense", ""),
            "init_func": init_func,
            "deinit_func": deinit_func,
            "init": simple.get("init", ""),
            "deinit": simple.get("deinit", ""),
            "loop": simple.get("loop", ""),
            "globals": simple.get("globals", ""),
            # helpers（软件 I2C 辅助函数等完整函数）→ extra_code 原样 append 进 USER CODE 4
            "extra_code": simple.get("helpers", ""),
            # 关闭动作（有源器件「关」）：启动门 toggle 到关闭沿时复位（蜂鸣器停/灯灭）
            "off": simple.get("off", ""),
            # 来源标记（2026-08-25 上板揪出 SPI Flash 读 FF FF FF）：board 定型模板 vs
            # functional 通用模板。board 定型 init 的引脚照手册填死（探索者 SPI1=PB3/PB4/PB5），
            # 组装层据此「直接套用定型 init」、不被 chip_portrait 默认引脚（PA5/PA6/PA7）覆盖。
            "source": "board",
        }

    def _render_board_bundles(
        self,
        text: str,
        chip: str,
        tids: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str], set[str], list[str]]:
        """渲染 board 模板 → bundles（+ 定型引脚冲突重查 + 板载复用检测）。

        从 assemble_board_multi 抽出的 bundle 生成层（2026-08-24 架构重构）：让 board 与
        functional 的 bundle 能统一合并（识别套式混合需求缺陷的根修）。

        Returns:
            (bundles, used_ids, occupied_pins, conflicts)
            occupied_pins：board 定型引脚集合（供 functional PinAllocator 预占避让）。
        """
        from knowledge.template_forge.board_simple import (
            extract_template_pins,
            match_all_simple,
            render_simple_template,
            resolve_board_simple,
        )

        templates = resolve_board_simple(chip)
        if not templates:
            return [], [], set(), []
        if tids is None:
            tids = match_all_simple(text, templates)
        else:
            tids = [t for t in tids if t in templates]  # 过滤 LLM 输出的非法 id
        if not tids:
            return [], [], set(), []

        bundles: list[dict[str, Any]] = []
        used_ids: list[str] = []
        conflicts: list[str] = []
        occupied: dict[str, str] = {}  # 定型引脚 → 模板 id（冲突重查）
        for tid in tids:
            simple = render_simple_template(tid, templates)
            if simple is None:
                continue
            # 定型引脚冲突重查（复用/撞车：同一次组合里两个模板用同一引脚）
            for pin in sorted(extract_template_pins(str(simple.get("init", "")))):
                if pin in occupied and occupied[pin] != tid:
                    conflicts.append(f"{tid}: 定型引脚 {pin} 已被 {occupied[pin]} 占用（冲突）")
                else:
                    occupied[pin] = tid
            bundles.append(self._simple_to_bundle(simple))
            used_ids.append(tid)
        if not bundles:
            return [], [], set(), []

        # 开发板复用冲突（pin_zone_view 底座接线，2026-08-21）：组合内模板的定型引脚，
        # 若在 board.json 里被多个板载资源复用（跳线/分时切换），告警提示用户注意选择。
        try:
            import json as _json

            from infrastructure.board_resolver import resolve_board_json
            from knowledge.template_forge.pin_zone_view import pin_owners

            board_path = resolve_board_json(Path(__file__).resolve().parents[2], chip)
            if board_path:
                board = _json.loads(board_path.read_text(encoding="utf-8"))
                owners = pin_owners(board)
                for pin in sorted(occupied):
                    if pin in owners and len(owners[pin]) > 1:
                        conflicts.append(f"开发板复用: {pin} 被 {'/'.join(owners[pin])} 复用（跳线/分时切换）")
        except Exception:  # noqa: BLE001 —— 复用检测失败不阻断生成
            pass

        return bundles, used_ids, set(occupied.keys()), conflicts

    def assemble_board_multi(
        self,
        text: str,
        chip: str = DEFAULT_CHIP_NAME,
        project_name: str = "agent_forge_board",
        tids: list[str] | None = None,
        enable_trace: bool = False,
    ) -> dict[str, Any] | None:
        """开发板多需求组合（三期「二次开发」）：'点灯+按键+串口' → 多模板段合并 → main.c。

        二次开发（念安 8-20「现有模板基础上插新逻辑 + 冲突重查」）：
        - 多需求识别：match_all_simple 识别文本里的多个功能（更长关键词优先去重）
        - 多模板组合：多个简单逻辑模板的 init/loop 合并进一个 main.c
        - 定型引脚冲突重查：简单逻辑模板引脚定型（照手册填），逐模板提取 init 里的
          定型引脚，检查是否被前面模板占用——冲突进 conflicts（念安：要标明）。

        与 assemble_board_project（单需求）区别：支持多需求；与 assemble_multi
        （functional 通用 + PinAllocator 动态分配）区别：开发板定型引脚只查冲突、
        不动态避让（引脚被开发板定死了，不能换）。

        tids（2026-08-21 念安「A/C 通道顶替」）：显式模板 id 覆盖自动匹配。
        C 通道（LLM 自主设计）由 LLM 判断需求后显式指定 template_ids，脚本按 id
        组合（区别于 B 通道的脚本自动 match_all_simple）；None = 脚本自动识别。
        """
        # P5 接线（2026-08-22）：用 resolve 严格解析芯片——系列级歧义/未知芯片在此
        # fail-closed 报错（不静默回退默认），解析结果规范化后贯穿全链路。
        from infrastructure.chip_gateway import resolve

        chip = resolve(chip).chip_name

        bundles, used_ids, _occupied_pins, conflicts = self._render_board_bundles(text, chip, tids)
        if not bundles:
            return None

        # 完整工程（2026-08-22 念安「业务层也要外设独立文件 + MSP 回调」）：
        # bundles → bundles_to_project_slices → build_standard_project，对外直接返回
        # 标准 CubeMX 完整工程（14 文件：外设独立 gpio.c/usart.c + hal_msp.c + startup + linker），
        # 不再是「业务层 main.c 单文件」（单文件只在 compile_check 内部临时生成）。
        from knowledge.loaders.mx_skeleton import MxSkeleton
        from knowledge.loaders.profile_manager import ProfileManager
        from knowledge.template_forge.project_slicer import bundles_to_project_slices

        slices = bundles_to_project_slices(bundles, chip)
        profile = ProfileManager().get_profile(chip)
        files = MxSkeleton(profile).build_standard_project(slices, project_name, enable_trace=enable_trace)
        return {
            "files": files,
            "project_name": project_name,
            "templates": used_ids,
            "conflicts": conflicts,
            "bundles": bundles,  # 向后兼容（compile_check 等仍可拿 bundles 走自定义链路）
        }

    def identify_routines(self, text: str, chip: str = DEFAULT_CHIP_NAME) -> dict[str, Any]:
        """识别套式（三期第三步，最高层）：识别需求 → 路由模板 → 缺啥补啥报告。

        念安 8-20 三期顺序「引脚分区 → 二次开发 → 识别套式」，识别套式是最高层调度，
        依赖二次开发的多模板组合能力（引脚分区为底座）。

        返回：
        - board_matched       : 命中的开发板简单逻辑模板（优先，定型代码快速出活）
        - functional_fallback : 开发板缺、functional 通用模板能补的（缺啥补啥）
        - has_board           : 是否开发板场景（chip 有 board.json + 简单逻辑模板）

        去重：functional 命中的模板，若与 board 同名（led_blink/uart_print/adc_read
        等开发板已覆盖）则不回落。
        """
        from knowledge.template_forge.board_simple import match_all_simple, resolve_board_simple

        board_templates = resolve_board_simple(chip)
        board_matched = match_all_simple(text, board_templates) if board_templates else []

        # 级联解析（2026-08-24 念安「全局初始化 vs 特殊逻辑」）：
        # 级联模板（cascade 字段）是「特殊逻辑」，不独立成功能，须级联到提供
        # cascade.reads 变量的宿主模板（outputs 含该变量）上。宿主不在场 →
        # fail-closed 报缺宿主（级联单元 loop 引用未声明全局变量会编译失败，不能静默）。
        cascade_conflicts: list[str] = []
        resolved_board: list[str] = []
        for tid in board_matched:
            tpl = board_templates.get(tid) if board_templates else None
            cascade = tpl.get("cascade") if tpl else None
            if not cascade:
                resolved_board.append(tid)
                continue
            reads = str(cascade.get("reads", "") or "")
            host = None
            for other in board_matched:
                if other == tid:
                    continue
                otpl = board_templates.get(other) if board_templates else None
                if otpl and reads and reads in (otpl.get("outputs") or []):
                    host = other
                    break
            if host:
                resolved_board.append(tid)  # 级联成立：宿主在场
            else:
                cascade_conflicts.append(f"{tid}: 级联缺宿主（需要提供 {reads} 的外设，如 ADC 采样）")
        board_matched = resolved_board

        # functional 通用模板（缺啥补啥的候选：26 个，比开发板 20 个更全）
        functional_matched = self._store.match_all(text) if text else []

        # 去重：functional 命中但 board 已覆盖 → 不回落。
        # 判定 = 模板同名，或关键词重叠（board key_press 的「按键」与 functional
        # button_read 的「按键」重叠 → 同功能；board pwm_breath 的「pwm」与
        # functional pwm_output 的「pwm」重叠 → 同功能）。
        board_ids = set(board_matched)
        board_kws: set[str] = set()
        for tid in board_matched:
            tpl = board_templates.get(tid)
            if tpl:
                board_kws.update(kw.lower() for kw in tpl.get("match", []))
        fallback: list[str] = []
        for tid in functional_matched:
            if tid in board_ids:
                continue
            tpl = self._store.get(tid)
            if tpl is None:
                continue
            tpl_kws = {kw.strip().lower() for kw in tpl.get("keywords", [])}
            # 去重（2026-08-24 对称面补全）：board_simple.match_all_simple 用「短关键词
            # 被更长关键词包含 → 跳过」规则，此处 functional 去重原本只用「精确交集」
            # （tpl_kws & board_kws），两层规则不一致 → 「指示灯」命中 board led_indicator，
            # 但 functional led_blink 的「灯」因「灯」∉{指示灯...} 漏网，生成多余的
            # PA6 点灯逻辑。修：functional 关键词若被 board 已命中关键词「包含」
            # （kw in bk，含相等），说明 board 的长词已覆盖该功能 → 不回落。
            if any(kw in bk for kw in tpl_kws for bk in board_kws):
                continue  # board 已覆盖（关键词被包含 = 同功能）
            fallback.append(tid)

        # 对称面去重（2026-08-25 上板揪出）：「adc 多通道」同时命中 board adc_read
        # （宽泛 match「adc」）和 functional adc_dma_scan（精确「adc 多通道」）→ 两个
        # ADC 模板都渲染 → adc_gpio 局部变量重复定义、编译失败。
        # 根修：functional 命中了「同外设、更精确」的模板（functional 词真包含 board
        # 词）时，board 宽泛命中让位。之前只有「functional 让位 board」（kw in bk），
        # 缺这个对称面（board 让位 functional）。
        if fallback:
            fallback_kws: dict[str, set[str]] = {}
            for tid in fallback:
                tpl = self._store.get(tid)
                if tpl is None:
                    continue
                periph = re.sub(r"\d+$", "", str(tpl.get("peripheral", "") or ""))
                fallback_kws.setdefault(periph, set()).update(
                    kw.strip().lower() for kw in (tpl.get("keywords") or [])
                )
            board_keep: list[str] = []
            for tid in board_matched:
                tpl = board_templates.get(tid)
                if tpl is None:
                    board_keep.append(tid)
                    continue
                periph = re.sub(r"\d+$", "", str(tpl.get("peripheral", "") or ""))
                fkws = fallback_kws.get(periph, set())
                bws = {kw.lower() for kw in (tpl.get("match") or [])}
                if any(bk in kw and bk != kw for bk in bws for kw in fkws):
                    continue  # board 让位：functional 更精确（词真包含 board 词）
                board_keep.append(tid)
            board_matched = board_keep

        # 自动带串口（functional requires_uart，对齐 board 的 match_all_simple 机制，2026-08-24）：
        # 命中的 functional 模板声明 requires_uart（有结果要回传，如 rtc_calendar/adc_read/i2c_scan），
        # 自动附加 uart_print，让读到的结果能串口打出来、上板能看见——不靠用户手动组合「+ 串口打印」。
        if "uart_print" not in fallback and "uart_print" not in board_ids:
            for tid in fallback:
                tpl = self._store.get(tid)
                if tpl and tpl.get("requires_uart"):
                    fallback.append("uart_print")
                    break

        # 控制关系识别（2026-08-21 prompt_composer 接线，消灭孤岛）：
        # 「按键控制点灯」这类复合需求，识别控制/上报关系，注入 functional 补缺分支。
        relations: dict[str, Any] = {}
        try:
            from knowledge.template_forge.prompt_composer import PromptComposer

            composed = PromptComposer().compose(text)
            if composed:
                relations = composed.get("relations") or {}
        except Exception:  # noqa: BLE001 —— 控制关系识别失败不影响路由
            relations = {}

        return {
            "board_matched": board_matched,
            "functional_fallback": fallback,
            "has_board": bool(board_templates),
            "relations": relations,
            "cascade_conflicts": cascade_conflicts,
        }

    def assemble_routed(
        self,
        text: str,
        chip: str | None = None,
        project_name: str = "agent_forge_board",
        tids: list[str] | None = None,
        enable_trace: bool = False,
    ) -> dict[str, Any] | None:
        """识别套式统一入口：board 优先，functional 补缺，缺啥报告。

        1. identify_routines 识别需求
        2. board 命中 → assemble_board_multi（开发板定型代码）
        3. board 缺、functional 有 → assemble_multi（通用补缺）
        4. 都没有 → 返回缺失报告（missing，不静默失败）

        chip 语义（2026-08-25 念安定调「降级处理」）：
        - 指定 chip → resolve 严格校验 + 贴芯片画像（引脚/AF/时钟）= 完整工程。
        - 没指定 chip（None/空串）→ 纯通用降级：不 resolve 具体芯片，返回「纯通用」
          模板（functional 通用，芯片特有引脚/AF/时钟不贴）。搜寻逻辑的降级——没搜到
          芯片就不贴芯片特有。

        tids（2026-08-21 念安「A/C 通道顶替」）：显式模板 id 透传给 assemble_board_multi，
        C 通道 LLM 指定模板时用；None = 脚本自动识别（B 通道）。
        """
        # 纯通用降级（2026-08-25 念安定调）：没指定芯片/板子 → 不 resolve 具体芯片，
        # 返回「纯通用」模板（functional 通用，芯片特有引脚/AF/时钟不贴）。
        if not chip:
            return self._assemble_generic(text, project_name)

        # P5 接线（2026-08-22）：入口 resolve 严格校验——系列级歧义/未知芯片在此 fail-closed，
        # 替代 identify_routines/get_profile 的宽松回退（"未找到芯片画像，使用默认"静默降级）。
        from infrastructure.chip_gateway import resolve

        chip = resolve(chip).chip_name
        routines = self.identify_routines(text, chip)
        board_matched = routines["board_matched"]
        fallback = routines["functional_fallback"]
        relations = routines.get("relations") or {}
        cascade_conflicts = routines.get("cascade_conflicts") or []

        # 架构重构（2026-08-24 念安「混合需求 functional 被漏」根修）：
        # 旧逻辑「board 命中就 return，functional 补缺被忽略」→ 改为 board + functional
        # bundles 合并后统一生成标准工程。functional 渲染时预占 board 定型引脚（reserved_pins），
        # 让 PinAllocator 自动避让，杜绝 board/functional 引脚撞车——架构协调，非打补丁。
        all_bundles: list[dict[str, Any]] = []
        used_templates: list[str] = []
        conflicts: list[str] = []
        occupied_pins: set[str] = set()

        if board_matched:
            board_tids = tids if tids else board_matched  # 显式 tids（A/C 通道）优先，否则自动识别
            board_bundles, board_ids, occupied_pins, board_conflicts = self._render_board_bundles(
                text, chip, tids=board_tids
            )
            all_bundles.extend(board_bundles)
            used_templates.extend(board_ids)
            conflicts.extend(board_conflicts)

        if fallback:
            # 控制关系联动（2026-08-21 prompt_composer 接线）：按键控制点灯 → 控制逻辑注入 loop
            func_bundles, func_ids, func_conflicts = self._render_functional_bundles(
                text, chip, fallback, relations=relations, reserved_pins=occupied_pins
            )
            all_bundles.extend(func_bundles)
            used_templates.extend(func_ids)
            conflicts.extend(func_conflicts)

        # 级联缺宿主（fail-closed）进 conflicts——级联单元读不到宿主输出变量，
        # 单独生成必然编译失败，须显式报告，不能静默丢。
        conflicts.extend(cascade_conflicts)

        if not all_bundles:
            # 都没有 → 缺失报告（带上级联缺宿主等已收集冲突，精确原因透出，不能静默丢）
            return {
                "files": {},
                "project_name": project_name,
                "templates": [],
                "conflicts": conflicts,
                "missing": f"未识别到可用模板覆盖的需求：{text[:60]}",
            }

        # 完整工程（2026-08-22 念安「业务层也要外设独立文件 + MSP 回调」）：
        # board + functional 合并后统一走 bundles_to_project_slices → build_standard_project，
        # 对外返回标准 CubeMX 完整工程。
        from knowledge.loaders.mx_skeleton import MxSkeleton
        from knowledge.loaders.profile_manager import ProfileManager
        from knowledge.template_forge.project_slicer import bundles_to_project_slices

        slices = bundles_to_project_slices(all_bundles, chip)
        profile = ProfileManager().get_profile(chip)
        files = MxSkeleton(profile).build_standard_project(slices, project_name, enable_trace=enable_trace)
        routed = "board" if board_matched else "functional"
        if board_matched and fallback:
            routed = "mixed"
        return {
            "files": files,
            "project_name": project_name,
            "templates": used_templates,
            "conflicts": conflicts,
            "bundles": all_bundles,
            "routed": routed,
        }

    def _assemble_generic(self, text: str, project_name: str) -> dict[str, Any]:
        """纯通用降级（念安 2026-08-25 定调）：没指定芯片/板子 → 不 resolve 具体芯片。

        返回「纯通用」模板：functional 通用模板，芯片特有参数（引脚/AF/时钟）不贴，
        用模板默认值/占位符。搜寻逻辑的降级——没搜到芯片，就不贴芯片特有。

        与正常路径的区别：不走 board（没指定开发板）、不 resolve chip（没指定芯片）、
        不调 ParameterFiller/PinAllocator 的芯片自适应（没画像可贴），直接渲染模板默认。
        """
        routines = self.identify_routines(text, chip="")
        fallback = routines["functional_fallback"] or []
        conflicts = list(routines.get("cascade_conflicts") or [])
        if not fallback:
            return {
                "generic": True,
                "project_name": project_name,
                "templates": [],
                "conflicts": conflicts,
                "missing": f"未识别到通用模板覆盖的需求：{text[:60]}",
            }
        bundles: list[dict[str, Any]] = []
        for tid in fallback:
            tpl = self._store.get(tid)
            if tpl is None:
                continue
            rendered = self._store.render(tid, {})
            bundles.append({"id": tid, **rendered})
        return {
            "generic": True,
            "project_name": project_name,
            "templates": fallback,
            "bundles": bundles,
            "conflicts": conflicts,
            "routed": "generic",
        }

    def _render_with_template(self, tpl: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        """用外部模板对象渲染（控制联动改过插槽后，绕过 store 缓存）。

        2026-08-09：${btn_action_code} 这类联动插槽必须在渲染前替换，
        渲染后 safe_substitute 会把缺失插槽清空，无处可填。
        """
        from string import Template as StrTemplate

        out: dict[str, Any] = {}
        for sec in ("globals", "init", "loop", "deinit"):
            raw = tpl.get(sec, "")
            if not raw:
                continue
            try:
                out[sec] = StrTemplate(raw).safe_substitute(params)
            except (ValueError, KeyError):
                out[sec] = raw
        # MX 范式字段透传（v2 模板配置函数名，v1 模板为空）
        out["init_func"] = tpl.get("init_func", "")
        out["deinit_func"] = tpl.get("deinit_func", "")
        return out

    @staticmethod
    def _slice_params(template_id: str, params: dict[str, Any]) -> dict[str, Any]:
        """组合时按模板参数 schema 取相关参数（避免串参数污染）。

        例：params={led_pin:5, uart_instance:1} 组合 led_blink+uart_print 时，
        led_blink 只取 led_* 前缀参数，uart_print 只取 uart_*/print_*。
        """
        store = FunctionalTemplateStore()
        tpl = store.get(template_id)
        if tpl is None:
            return {}
        schema = tpl.get("params", {})
        # 参数名前缀（取 schema 键的前缀）
        sliced: dict[str, Any] = {}
        for key, value in params.items():
            if key in schema or any(key.startswith(prefix) for prefix in _param_prefixes(template_id)):
                sliced[key] = value
        # 通用参数（instance/pin/port 等无前缀基础键）
        for key in ("instance", "pin", "port", "channel"):
            if key in params:
                sliced[key] = params[key]
        return sliced

    # ---- 汉堡拼装 ----

    @staticmethod
    def _render_main_c(bundles: list[dict[str, Any]], chip: str = "") -> str:
        """单文件 main.c：generate_main_c 骨架 + 函数体塞 USER CODE 4（2026-08-18 删硬编码后统一）。

        用 generate_main_c 骨架（PLL 从 profile 读，跨芯片正确）+ 函数体塞 USER CODE 4，
        保证健康检查（check_main_c / must_calls）兼容。
        """
        from infrastructure.config import DEFAULT_CHIP_NAME
        from knowledge.loaders.mx_skeleton import MxSkeleton
        from knowledge.loaders.profile_manager import ProfileManager
        from knowledge.template_forge.project_slicer import _strip_dup_decls, bundles_to_mx_slots

        slots = bundles_to_mx_slots(bundles)
        profile = ProfileManager().get_profile(chip or DEFAULT_CHIP_NAME)
        skeleton = MxSkeleton(profile)
        # loop 体合并去重（对称修复：init 体在 bundles_to_mx_slots 已去重，loop 体
        # 也须去重同名局部变量——两个模板 loop 各声明 uint8_t data 合并进 while(1) 会重复定义）
        loop_bodies: list[str] = []
        seen_loop_decls: set[str] = set()
        for b in bundles:
            loop = str(b.get("loop", "") or "")
            if loop:
                loop_bodies.append(_strip_dup_decls(loop, seen_loop_decls))
        # globals 合并去重（对称修复：全局句柄 UART_HandleTypeDef huart1 同名重复定义；
        # 函数原型 iic_start 等非变量声明不受影响，保留）
        globals_lines: list[str] = []
        seen_globals_decls: set[str] = set()
        for b in bundles:
            g = str(b.get("globals", "") or "")
            if g:
                globals_lines.append(_strip_dup_decls(g, seen_globals_decls))
        main_c = skeleton.generate_main_c(
            peripheral_handles=globals_lines,
            peripheral_inits=slots["inits"],
            peripheral_init_protos=slots["protos"],
            main_loop_body=loop_bodies,
        )
        if slots["func_defs"]:
            footer = "\n\n/* USER CODE BEGIN 4 */\n" + "\n\n".join(slots["func_defs"]) + "\n/* USER CODE END 4 */\n"
            main_c += footer
        return main_c


def _param_prefixes(template_id: str) -> list[str]:
    """功能模板的参数前缀（按模板名推断 led_blink → led_）。"""
    base = template_id.split("_")[0] if "_" in template_id else template_id
    return [f"{base}_", "print_", "delay_", "baud_", "period_", "pulse_", "tim_", "adc_", "btn_", "iwdg_", "reset_", "debounce_"]


def assemble_functional(template_id: str, params: dict[str, Any] | None = None) -> str | None:
    """便捷入口：拼装完整工程代码。"""
    result = FunctionalAssembler().assemble(template_id, params)
    return result["main_c"] if result else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 无 LLM 兜底路径：自然语言 → 匹配 → 拼装
    assembler = FunctionalAssembler()
    result = assembler.assemble_from_text("帮我写一个点灯程序，PA5 口", {"led_pin": "5"})
    if result:
        print(result["main_c"])
    else:
        print("(拼装失败)")
