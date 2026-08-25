"""S 聊天适配：chat（非流式）/ chat_stream（SSE 流式）把代码意图转发 code_gen 技能。"""
from __future__ import annotations

import logging
from typing import Any

from .ui_adapter import _is_code_intent, _sse_event, _ui_state

logger = logging.getLogger("api.chat_adapter")

async def chat(workspace: Any, data: dict[str, Any]) -> dict[str, Any]:
    """兼容 Agent-E 的 /api/chat，将代码意图转发到 code_gen 技能。"""
    msg = data.get("message", "").strip()
    if not msg:
        return {"error": "消息为空"}

    if _is_code_intent(msg) or _ui_state["force_code"]:
        result = await workspace.run("code_gen", {
            "requirement": msg,
            "mcu": _ui_state["mcu"],
        })
        # R1 判定为非代码意图（闲聊/未知）→ 礼貌引导，不硬生成
        if result.status == "skipped":
            return {
                "reply": (
                    f"我理解你想说「{msg}」，但这看起来不是嵌入式代码需求。\n"
                    "可以描述具体外设配置，例如：配置 PA0 推挽输出 / UART1 串口 115200。"
                ),
                "emotion": {"mood": "neutral", "intensity": 0.5},
                "intent": result.data.get("intent", ""),
            }
        # 板载资源未确认 → 引导用户确认引脚（禁止猜引脚）
        if result.status == "need_board_confirm":
            return {
                "reply": result.error or (
                    f"「{msg}」涉及板载资源但 board.json 未确认引脚，"
                    "请先确认板载引脚后重试。"
                ),
                "emotion": {"mood": "neutral", "intensity": 0.5},
                "need_board_confirm": True,
            }
        # 生成前风险评估 HIGH → 引导确认（禁止盲目生成）
        if result.status == "need_confirm":
            suggestions = (result.data or {}).get("suggestions", [])
            hint = "；".join(suggestions) if suggestions else "请补充更明确的需求描述"
            return {
                "reply": f"生成前风险评估未通过：{result.error}\n建议：{hint}",
                "emotion": {"mood": "neutral", "intensity": 0.5},
                "need_board_confirm": True,
                "suggestions": suggestions,
            }
        code = result.artifacts.get("source_code", "")
        return {
            "reply": code or result.error or "\n".join(["代码生成失败"]),
            "emotion": {"mood": "neutral", "intensity": 0.5},
            "code": code,
            "approved": result.status == "success",
            "source": "Agent-S",
        }

    return {
        "reply": (
            f"Agent-S Studio 已收到：{msg}\n\n"
            "当前为技术工作室模式，专注嵌入式代码生成。"
            "请描述具体外设配置需求，例如：配置 PA0 推挽输出。"
        ),
        "emotion": {"mood": "neutral", "intensity": 0.5},
    }

async def chat_stream(workspace: Any, data: dict[str, Any]) -> Any:
    """
    兼容 /api/chat/stream（SSE）。

    真流式：代码/嵌入式意图 → 复用 code_gen 技能 stream_run（meta → token → done），
    与 /api/code/stream 同一套真流式管线，不再全量等待后切块。
    非代码意图（闲聊/引导）→ 普通回复（秒回，无需流式）。
    """
    msg = data.get("message", "").strip()
    if not msg:
        yield _sse_event({"error": "消息为空"})
        yield _sse_event({"done": True})
        return

    is_code = _is_code_intent(msg) or _ui_state["force_code"]

    # ── 真流式路径：代码意图走 code_gen.stream_run ──
    if is_code:
        skill = workspace.get_skill("code_gen")
        if skill is not None and hasattr(skill, "stream_run"):
            try:
                async for event in skill.stream_run(workspace.ctx, requirement=msg, project=False):
                    etype = event.get("type")
                    if etype == "meta":
                        yield _sse_event({"meta": event.get("plan", {})})
                    elif etype == "token":
                        yield _sse_event({"token": event["token"]})
                    elif etype == "error":
                        payload: dict[str, Any] = {"error": event.get("error", "生成失败"), "done": True}
                        if event.get("suggestions"):
                            payload["suggestions"] = event["suggestions"]
                        if event.get("need_board_confirm"):
                            payload["need_board_confirm"] = True
                        yield _sse_event(payload)
                        return
                    elif etype == "done":
                        done_payload: dict[str, Any] = {
                            "done": True,
                            "emotion": {"mood": "neutral", "intensity": 0.5},
                            "approved": event.get("approved", False),
                            "elapsed_ms": event.get("elapsed_ms", 0),
                        }
                        code = event.get("code", "")
                        if code:
                            done_payload["code"] = code
                        yield _sse_event(done_payload)
                        return
                return
            except Exception as e:  # noqa: BLE001
                logger.exception("chat_stream 流式生成异常")
                yield _sse_event({"error": str(e), "done": True})
                return

    # ── 非流式回退：非代码意图或技能不可用（内容秒回，切块无感知延迟）──
    try:
        result = await chat(workspace, data)
    except Exception as e:  # noqa: BLE001
        yield _sse_event({"error": str(e)})
        yield _sse_event({"done": True})
        return

    reply = result.get("reply", "")

    # 按短句/字符切分，模拟流式效果
    chunk_size = 4
    for i in range(0, len(reply), chunk_size):
        yield _sse_event({"token": reply[i:i + chunk_size]})

    final_payload: dict[str, Any] = {"done": True, "emotion": result.get("emotion", {"mood": "neutral", "intensity": 0.5})}
    if result.get("code"):
        final_payload["code"] = result["code"]
    yield _sse_event(final_payload)
