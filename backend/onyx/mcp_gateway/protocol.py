"""MCP protocol surface of the gateway.

One `Server` per catalog entry, mounted at `/p/{slug}`. Tenant context comes
from the verified token the API server minted, which the ASGI wrapper puts on
the scope — never from a request header.
"""

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from mcp.server.lowlevel.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    CallToolResult,
    ContentBlock,
    EmbeddedResource,
    ImageContent,
    TextContent,
    Tool,
)
from starlette.types import Receive, Scope, Send

from onyx.cache.factory import get_cache_backend
from onyx.cache.interface import CACHE_TRANSIENT_ERRORS
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.mcp_catalog import get_catalog_entry_by_slug
from onyx.mcp_gateway.engine import invoke_tool
from onyx.mcp_gateway.upstream import UpstreamTarget, list_upstream_tools
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import CURRENT_TENANT_ID_CONTEXTVAR

logger = setup_logger()

# Tool lists are per tenant and per entry. The previous process-global dict was
# keyed by slug alone, which leaked one tenant's tool list to another; the cache
# backend prefixes keys with the tenant, so that cannot happen here.
_TOOLS_CACHE_PREFIX = "mcp_gateway:tools:"
_TOOLS_CACHE_TTL_SECONDS = 900

TENANT_SCOPE_KEY = "onyx_tenant_id"
USER_EMAIL_SCOPE_KEY = "onyx_user_email"
_USER_EMAIL: ContextVar[str | None] = ContextVar("onyx_gateway_user_email", default=None)


def _tools_cache_key(slug: str) -> str:
    return f"{_TOOLS_CACHE_PREFIX}{slug}"


def _read_cached_tools(tenant_id: str, slug: str) -> list[Tool] | None:
    try:
        raw = get_cache_backend(tenant_id=tenant_id).get(_tools_cache_key(slug))
    except CACHE_TRANSIENT_ERRORS:
        logger.debug("MCP gateway tool cache read failed", exc_info=True)
        return None
    if not raw:
        return None
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    try:
        return [Tool.model_validate(item) for item in items]
    except Exception:
        logger.debug("Discarding unreadable cached MCP tool list", exc_info=True)
        return None


def _write_cached_tools(tenant_id: str, slug: str, tools: list[Tool]) -> None:
    try:
        get_cache_backend(tenant_id=tenant_id).set(
            _tools_cache_key(slug),
            json.dumps([tool.model_dump(mode="json") for tool in tools]),
            ex=_TOOLS_CACHE_TTL_SECONDS,
        )
    except CACHE_TRANSIENT_ERRORS:
        logger.debug("MCP gateway tool cache write failed", exc_info=True)


def invalidate_tools_cache(tenant_id: str, slug: str) -> None:
    try:
        get_cache_backend(tenant_id=tenant_id).delete(_tools_cache_key(slug))
    except CACHE_TRANSIENT_ERRORS:
        logger.debug("MCP gateway tool cache delete failed", exc_info=True)


async def tools_for_slug(tenant_id: str, slug: str) -> list[Tool]:
    cached = _read_cached_tools(tenant_id, slug)
    if cached is not None:
        return cached

    with get_session_with_current_tenant() as db_session:
        entry = get_catalog_entry_by_slug(db_session, slug)
        if entry is None or not entry.enabled:
            return []
        target = UpstreamTarget.from_entry(entry)
        entry_id = entry.id

    discovered = await list_upstream_tools(target)
    tools = [
        Tool(
            name=item.name,
            description=item.description,
            inputSchema=item.inputSchema,
            annotations=item.annotations,
        )
        for item in discovered
    ]

    with get_session_with_current_tenant() as db_session:
        refreshed = get_catalog_entry_by_slug(db_session, slug)
        if refreshed is not None and refreshed.id == entry_id:
            refreshed.tools_list_refreshed_at = datetime.now(timezone.utc)
            db_session.commit()

    _write_cached_tools(tenant_id, slug, tools)
    return tools


def _content_from_result(payload: dict[str, Any]) -> Sequence[ContentBlock]:
    raw = payload.get("content")
    if not isinstance(raw, list) or not raw:
        structured = payload.get("structuredContent")
        text = "" if structured is None else json.dumps(structured, ensure_ascii=False)
        return [TextContent(type="text", text=text)]

    blocks: list[ContentBlock] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        block_type = item.get("type")
        if block_type == "text":
            blocks.append(TextContent(type="text", text=str(item.get("text") or "")))
        elif block_type == "image":
            blocks.append(
                ImageContent(
                    type="image",
                    data=str(item.get("data") or ""),
                    mimeType=str(item.get("mimeType") or "image/png"),
                )
            )
        elif block_type == "resource":
            resource = item.get("resource")
            if isinstance(resource, dict):
                blocks.append(
                    EmbeddedResource.model_validate(
                        {"type": "resource", "resource": resource}
                    )
                )
    return blocks or [TextContent(type="text", text="")]


def call_result_from_payload(payload: dict[str, Any]) -> CallToolResult:
    """Rebuild the original MCP result, including structuredContent."""
    try:
        return CallToolResult.model_validate(payload)
    except Exception:
        structured = payload.get("structuredContent")
        return CallToolResult(
            content=list(_content_from_result(payload)),
            structuredContent=structured if isinstance(structured, dict) else None,
            isError=bool(payload.get("isError")),
        )


def build_provider_server(slug: str) -> Server[Any]:
    server: Server[Any] = Server(f"onyx-mcp-gateway-{slug}")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tenant_id = CURRENT_TENANT_ID_CONTEXTVAR.get()
        if tenant_id is None:
            return []
        return await tools_for_slug(tenant_id, slug)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        resolved = await invoke_tool(
            catalog_slug=slug,
            tool_name=name,
            arguments=arguments or {},
            user_email=_USER_EMAIL.get(),
        )
        return call_result_from_payload(resolved.result)

    return server


def build_session_manager(slug: str) -> StreamableHTTPSessionManager:
    return StreamableHTTPSessionManager(
        app=build_provider_server(slug),
        json_response=True,
        stateless=True,
    )


class ProviderASGIApp:
    """Binds the tenant from the verified token, then serves Streamable HTTP."""

    def __init__(
        self, slug: str, session_manager: StreamableHTTPSessionManager
    ) -> None:
        self.slug = slug
        self.session_manager = session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        tenant_id = scope.get(TENANT_SCOPE_KEY)
        if not isinstance(tenant_id, str):
            # The auth middleware always sets this. Reaching here means a
            # routing mistake, and guessing a tenant would be worse than 500.
            raise RuntimeError("MCP gateway request reached a provider unauthenticated")
        raw_email = scope.get(USER_EMAIL_SCOPE_KEY)
        email = raw_email if isinstance(raw_email, str) else None
        token = CURRENT_TENANT_ID_CONTEXTVAR.set(tenant_id)
        email_token = _USER_EMAIL.set(email)
        try:
            await self.session_manager.handle_request(scope, receive, send)
        finally:
            _USER_EMAIL.reset(email_token)
            CURRENT_TENANT_ID_CONTEXTVAR.reset(token)


@asynccontextmanager
async def run_session_managers(
    managers: Sequence[StreamableHTTPSessionManager],
) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        for manager in managers:
            await stack.enter_async_context(manager.run())
        yield
