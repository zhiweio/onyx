"""Minimal stateless MCP server over HTTP for the platform tool catalog.

Implements the JSON-RPC methods opencode's remote MCP client needs:
``initialize``, ``notifications/initialized``, ``tools/list`` and
``tools/call`` — one POST per request, no server-side session state
(stateless mode). This deliberately avoids the MCP SDK dependency; the
M6 gateway will add the official SDK for *client* connections to
enterprise servers, while this server surface stays self-contained.
"""

from __future__ import annotations

from typing import Any

from onyx.server.features.build.tools.base import (
    ToolContext,
    ToolInvocation,
)
from onyx.server.features.build.tools.registry import PlatformToolRegistry

_MCP_PROTOCOL_VERSION = "2025-06-18"
_SERVER_INFO = {"name": "onyx-platform-tools", "version": "1.0.0"}


class McpJsonRpcError(Exception):
    """JSON-RPC error with a code, per the MCP spec."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_MCP_PARSE_ERROR = -32700
_MCP_METHOD_NOT_FOUND = -32601
_MCP_INVALID_REQUEST = -32602
_MCP_INTERNAL_ERROR = -32603


def handle_mcp_jsonrpc(
    body: dict[str, Any],
    registry: PlatformToolRegistry,
    ctx: ToolContext,
    session_id: str | None,
) -> dict[str, Any] | None:
    """Handle one JSON-RPC request. Returns the response, or None for
    notifications (which carry no ``id``)."""
    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}
    try:
        if not isinstance(method, str):
            raise McpJsonRpcError(_MCP_INVALID_REQUEST, "method must be a string")
        result: dict[str, Any] | None
        if method == "initialize":
            result = _initialize()
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": registry.definitions()}
        elif method == "tools/call":
            result = _tools_call(params, registry, ctx, session_id)
        elif method == "ping":
            result = {}
        else:
            raise McpJsonRpcError(_MCP_METHOD_NOT_FOUND, f"unknown method {method}")
    except McpJsonRpcError as exc:
        if request_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": exc.code, "message": exc.message},
        }
    except Exception as exc:
        if request_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": _MCP_INTERNAL_ERROR, "message": f"internal error: {exc}"},
        }
    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _initialize() -> dict[str, Any]:
    return {
        "protocolVersion": _MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": _SERVER_INFO,
    }


def _tools_call(
    params: dict[str, Any],
    registry: PlatformToolRegistry,
    ctx: ToolContext,
    session_id: str | None,
) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise McpJsonRpcError(_MCP_INVALID_REQUEST, "params.name is required")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise McpJsonRpcError(
            _MCP_INVALID_REQUEST, "params.arguments must be an object"
        )
    invocation = ToolInvocation(tool=name, arguments=arguments, session_id=session_id)
    result = registry.call(invocation, ctx)
    payload: dict[str, Any] = {"content": result.content, "isError": False}
    if result.terminate:
        # MCP has no terminate flag; surface it in structuredContent for the
        # runtime plugin/bridge to act on.
        payload["structuredContent"] = {"terminate": True}
    return payload


def error_response_parse() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": _MCP_PARSE_ERROR, "message": "invalid JSON body"},
    }
