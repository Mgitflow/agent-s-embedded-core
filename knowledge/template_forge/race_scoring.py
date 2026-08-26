"""双通道竞争评分与废弃区：对 A/B 两路产出统一打分择优，分低者丢废弃区可追溯，标尺与 benchmark 同源。"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_DISCARDED_DIR = _ROOT / "data" / "discarded"


def score_code(code: str, template_used: str = "", expected: list[str] | None = None) -> dict[str, Any]:
    """统一标尺打分（与 benchmark 同源）。expected = 期望功能模板 id 列表。"""
    code = code or ""
    m: dict[str, Any] = {}
    # 1. 完整性：完整工程结构标志
    has_main = "int main" in code or "int main(" in code
    has_init = bool(re.search(r"(HAL_Init|MX_\w+_Init|SystemClock_Config)", code))
    has_loop = bool(re.search(r"while\s*\(\s*1\s*\)|for\s*\(\s*;;", code))
    has_error = "Error_Handler" in code
    m["complete"] = sum([has_main, has_init, has_loop, has_error])
    # 2. API 真实性（HAL 白名单粗检）
    hal_calls = set(re.findall(r"\b(HAL_\w+)\s*\(", code))
    bad_api = [c for c in hal_calls if not _api_exists(c)]
    m["api_real"] = len(bad_api) == 0
    m["bad_api"] = bad_api[:3]
    # 3. 意图匹配
    matched = 0
    for tid in expected or []:
        peri = tid.split("_")[0].upper()
        if peri in code.upper() or tid in template_used:
            matched += 1
    m["intent_match"] = matched / max(len(expected or []), 1)
    # 4. 编译性（结构推断，仅作诊断字段；B/C 完整工程已被 health_check ⑩ 真编译验证）
    m["compileable"] = has_main and has_error
    # 5. 代码量
    m["lines"] = len(code.splitlines())
    # 6. 总分（评分合理化）：
    #   - 去重复计分：原 compileable（has_main&&has_error）与 complete 里的 has_main/has_error 重复给分
    #   - intent_match 权重 5→10：评分应区分「能编译的垃圾」和「真正实现功能」，
    #     对齐「端到端通 ≠ 达到预期通」的口径——功能正确性权重应高于结构完整
    m["score"] = (
        (10 if m["api_real"] else 0)   # API 真实性（HAL 白名单粗检）
        + m["complete"] * 3            # 结构完整（has_main/has_init/has_loop/has_error 各 3）
        + m["intent_match"] * 10       # 意图匹配（功能做对了没，权重翻倍）
    )
    return m


def _api_exists(call: str) -> bool:
    """HAL API 存在性粗检（resource_adapter 全库白名单）。

    修复：validate_api_names 用正则 `\\b(HAL_\\w+)\\s*\\(` 提取调用，
    必须带括号才匹配——此前传裸 API 名（无括号）匹配不到、恒判「存在」，
    假 API 检测完全失效（score_code 的 api_real 假绿）。补 "(" 再校验。
    """
    try:
        from knowledge.template_forge.resource_adapter import ResourceAdapter

        return ResourceAdapter().validate_api_names(call + "(", "") == []
    except Exception:  # noqa: BLE001 —— fail-closed：校验器异常按「API 未知」处理，不静默放行
        return False  # 修复：此前返回 True（放行），校验器坏则所有 API 判存在、评分失真


def archive_discarded(entry: str, text: str, code: str, score: float, reason: str) -> Path | None:
    """落选产物丢废弃区（data/discarded/日期-需求-分数.json，不删可追溯）。

    entry = 通道名（a/b/c）；text = 需求原文；score = 该通道得分；
    reason = 落选原因（分数低于 winner / 超时未参与）。
    """
    try:
        _DISCARDED_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", text)[:24] or "req"
        path = _DISCARDED_DIR / f"{ts}_{safe}_{entry}_{int(score)}.json"
        path.write_text(
            json.dumps(
                {
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "entry": entry,
                    "text": text,
                    "score": round(float(score), 1),
                    "reason": reason,
                    "code_len": len(code or ""),
                    "code": (code or "")[:20000],  # 归档截断保护
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path
    except Exception:  # noqa: BLE001 —— 归档失败不阻断
        return None
