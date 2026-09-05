from typing import Any

from mcp.types import CallToolResult, Tool as MCPLibTool

from onyx.db.models import MCPGatewayProvider
from onyx.mcp_gateway.auth_adapters import apply_auth
from onyx.server.features.mcp.client import (
    call_mcp_tool_raw_async,
    discover_mcp_tools_async,
)


def serialize_call_result(result: CallToolResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def is_error_result(payload: dict[str, Any]) -> bool:
    return bool(payload.get("isError"))


def is_empty_result(payload: dict[str, Any]) -> bool:
    content = payload.get("content")
    if isinstance(content, list) and not content:
        structured = payload.get("structuredContent")
        return not structured
    if isinstance(content, list):
        texts = [
            block.get("text")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if texts and all(not (text or "").strip() for text in texts):
            return True
    return False


async def call_upstream(
    provider: MCPGatewayProvider,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    url, headers = apply_auth(provider)
    result = await call_mcp_tool_raw_async(
        url,
        tool_name,
        arguments,
        connection_headers=headers,
        transport=provider.transport,
    )
    return serialize_call_result(result)


async def list_upstream_tools(provider: MCPGatewayProvider) -> list[MCPLibTool]:
    url, headers = apply_auth(provider)
    return await discover_mcp_tools_async(
        url,
        connection_headers=headers,
        transport=provider.transport,
    )
