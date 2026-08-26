"""MCP 能力桥：把 Agent-S 核心能力暴露为标准 MCP 工具（JSON-RPC 2.0 over HTTP POST /mcp）。"""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_log = logging.getLogger("mcp_bridge")


def _tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": "code_gen",
            "description": "嵌入式代码生成（识别套式：开发板简单逻辑模板优先 + 通用功能模板补缺）",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirement": {"type": "string", "description": "用户需求文本"},
                },
                "required": ["requirement"],
            },
        },
        {
            "name": "compile_check",
            "description": "对代码片段执行编译检查，返回编译报告",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要检查的 C 代码"},
                },
                "required": ["code"],
            },
        },
    ]


class McpBridge:
    """MCP 能力桥：注册处理器，暴露标准 MCP 工具。"""

    def __init__(self, handlers: dict[str, Any] | None = None) -> None:
        # handlers: {"code_gen": callable(requirement: str) -> dict, ...}
        self._handlers = handlers or {}

    def tools_list(self) -> dict[str, Any]:
        tools = []
        for schema in _tool_schemas():
            if schema["name"] in self._handlers:
                tools.append(schema)
        return {"tools": tools}

    def tools_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"unknown tool: {name}"}
        try:
            result = handler(**arguments)
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
        except Exception as e:  # noqa: BLE001
            _log.warning("MCP tool %s failed: %s", name, e)
            return {"error": str(e)}

    def dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        method = payload.get("method", "")
        params = payload.get("params", {}) or {}
        if method == "tools/list":
            return self.tools_list()
        if method == "tools/call":
            return self.tools_call(params.get("name", ""), params.get("arguments", {}) or {})
        return {"error": f"unsupported method: {method}"}


def make_mcp_handler(bridge: McpBridge) -> type:
    """构造 HTTP handler（供 ThreadingHTTPServer 使用）。"""

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._reply({"error": "invalid JSON"})
                return
            result = bridge.dispatch(payload)
            self._reply(result)

        def _reply(self, data: dict[str, Any]) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            _log.debug(fmt, *args)

    return _Handler


def serve(bridge: McpBridge, host: str = "127.0.0.1", port: int = 8102) -> ThreadingHTTPServer:
    """启动 MCP 桥（默认 8102，81 系列子机端口段，修正注释；SE 主服务 8006/身份 8106）。"""
    server = ThreadingHTTPServer((host, port), make_mcp_handler(bridge))
    _log.info("MCP bridge listening on http://%s:%d/mcp", host, port)
    return server
