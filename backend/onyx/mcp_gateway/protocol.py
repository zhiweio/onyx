from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.lowlevel.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import ContentBlock, EmbeddedResource, ImageContent, TextContent, Tool
from starlette.types import Receive, Scope, Send

from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.mcp_gateway import get_provider_by_slug, update_provider__no_commit
from onyx.mcp_gateway.engine import invoke_tool
from onyx.mcp_gateway.upstream import list_upstream_tools
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import (
    CURRENT_TENANT_ID_CONTEXTVAR,
    get_current_tenant_id,
)

logger = setup_logger()

_tools_cache: dict[str, list[Tool]] = {}


async def _tools_for_slug(slug: str) -> list[Tool]:
    cached = _tools_cache.get(slug)
    if cached is not None:
        return cached
    with get_session_with_current_tenant() as db_session:
        provider = get_provider_by_slug(db_session, slug)
        if provider is None or not provider.enabled:
            return []
        discovered = await list_upstream_tools(provider)
        from datetime import datetime, timezone

        update_provider__no_commit(
            db_session,
            provider,
            tools_list_refreshed_at=datetime.now(timezone.utc),
        )
        db_session.commit()
    tools = [
        Tool(
            name=item.name,
            description=item.description,
            inputSchema=item.inputSchema,
            annotations=item.annotations,
        )
        for item in discovered
    ]
    _tools_cache[slug] = tools
    return tools


def invalidate_tools_cache(slug: str | None = None) -> None:
    if slug is None:
        _tools_cache.clear()
        return
    _tools_cache.pop(slug, None)


def _content_from_result(payload: dict[str, Any]) -> Sequence[ContentBlock]:
    raw = payload.get("content")
    if not isinstance(raw, list) or not raw:
        structured = payload.get("structuredContent")
        text = "" if structured is None else str(structured)
        return [TextContent(type="text", text=text or "")]
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
                    EmbeddedResource.model_validate({"type": "resource", "resource": resource})
                )
    return blocks or [TextContent(type="text", text="")]


def build_provider_server(slug: str) -> Server[Any]:
    server: Server[Any] = Server(f"onyx-mcp-gateway-{slug}")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return await _tools_for_slug(slug)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[ContentBlock]:
        resolved = await invoke_tool(
            provider_slug=slug,
            tool_name=name,
            arguments=arguments or {},
        )
        return _content_from_result(resolved.result)

    return server


def build_session_manager(slug: str) -> StreamableHTTPSessionManager:
    return StreamableHTTPSessionManager(
        app=build_provider_server(slug),
        json_response=True,
        stateless=True,
    )


class ProviderASGIApp:
    """ASGI wrapper that binds tenant context then serves Streamable HTTP."""

    def __init__(self, slug: str, session_manager: StreamableHTTPSessionManager) -> None:
        self.slug = slug
        self.session_manager = session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        tenant = headers.get("x-onyx-tenant-id") or get_current_tenant_id()
        token = CURRENT_TENANT_ID_CONTEXTVAR.set(tenant)
        try:
            await self.session_manager.handle_request(scope, receive, send)
        finally:
            CURRENT_TENANT_ID_CONTEXTVAR.reset(token)


@asynccontextmanager
async def run_session_managers(
    managers: Sequence[StreamableHTTPSessionManager],
) -> AsyncIterator[None]:
    from contextlib import AsyncExitStack

    async with AsyncExitStack() as stack:
        for manager in managers:
            await stack.enter_async_context(manager.run())
        yield
