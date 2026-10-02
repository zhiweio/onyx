from typing import Any

from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as MCPLibTool

from onyx.db.models import MCPCatalogEntry
from onyx.mcp_gateway.auth_adapters import apply_auth
from onyx.server.features.mcp.client import (
    call_mcp_tool_raw_async,
    discover_mcp_tools_async,
    unwrap_exception_group,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


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


class UpstreamTarget:
    """Everything needed to call an upstream, detached from the DB session.

    The upstream call can take minutes. Holding an ORM object across it would
    hold a pooled connection with it, so the caller snapshots the entry into
    this before releasing the session.
    """

    def __init__(self, url: str, headers: dict[str, str], transport: Any) -> None:
        self.url = url
        self.headers = headers
        self.transport = transport

    @classmethod
    def from_entry(cls, entry: MCPCatalogEntry) -> "UpstreamTarget":
        url, headers = apply_auth(entry)
        return cls(url=url, headers=headers, transport=entry.transport)


def _error_payload(message: str) -> dict[str, Any]:
    return serialize_call_result(
        CallToolResult(
            content=[TextContent(type="text", text=message)],
            isError=True,
        )
    )


# Upstream account/balance failures look like tool errors to the agent, which
# then honestly reports data as "unavailable" without anyone noticing the
# deployment key is out of credit. Surface them loudly at the gateway.
_BALANCE_ERROR_MARKERS = (
    "insufficient balance",
    "余额不足",
    "payment required",
    "exceeded your current quota",
)


def _warn_on_balance_error(result: dict[str, Any], tool_name: str) -> None:
    try:
        text = str(result.get("content") or result)
    except Exception:
        return
    lowered = text.lower()
    if any(marker in lowered for marker in _BALANCE_ERROR_MARKERS):
        logger.warning(
            "Upstream MCP tool %s returned an account/balance error — the "
            "deployment credential for this server likely needs a top-up or "
            "entitlement fix: %s",
            tool_name,
            text[:200],
        )


async def call_upstream(
    target: UpstreamTarget,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = await call_mcp_tool_raw_async(
            target.url,
            tool_name,
            arguments,
            connection_headers=target.headers,
            transport=target.transport,
        )
    except Exception as error:
        inner = unwrap_exception_group(error)
        logger.exception("Upstream MCP call failed for %s", tool_name)
        return _error_payload(str(inner))
    serialized = serialize_call_result(result)
    _warn_on_balance_error(serialized, tool_name)
    return serialized


async def list_upstream_tools(target: UpstreamTarget) -> list[MCPLibTool]:
    return await discover_mcp_tools_async(
        target.url,
        connection_headers=target.headers,
        transport=target.transport,
    )
