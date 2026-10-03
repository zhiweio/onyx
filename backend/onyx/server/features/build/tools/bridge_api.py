"""Agent-facing bridge: REST + MCP endpoints for the platform tool catalog.

The sandbox reaches these through the egress proxy, which injects the
per-sandbox craft PAT (see ``sandbox_proxy/resolvers/onyx_pat.py``); the
standard permission dependency resolves that PAT to the owning user, so
tool calls execute with the user's permissions.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from onyx.auth.permissions import require_permission
from onyx.db.enums import Permission
from onyx.db.models import User
from onyx.server.features.build.configs import ENABLE_CRAFT, MCP_SESSION_TAG_HEADER
from onyx.server.features.build.tools.base import ToolContext, ToolInvocation
from onyx.server.features.build.tools.mcp_server import (
    error_response_parse,
    handle_mcp_jsonrpc,
)
from onyx.server.features.build.tools.registry import (
    PlatformToolRegistry,
    ToolBindings,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


def _require_onyx_craft_enabled_bridge() -> None:
    if not ENABLE_CRAFT:
        raise HTTPException(status_code=404)


router = APIRouter(
    # Full /build/agent-tools path: mounted at the app level, not under the
    # /build feature router (see features/build/api.py).
    prefix="/build/agent-tools",
    dependencies=[
        Depends(_require_onyx_craft_enabled_bridge),
        # The sandbox calls this bridge with a CRAFT_SANDBOX PAT, which does
        # not imply BASIC_ACCESS; USE_LLM_GATEWAY is the overlap both scopes
        # share, keeping session-cookie callers working too.
        Depends(require_permission(Permission.USE_LLM_GATEWAY)),
    ],
)


class ToolCallRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


_registry_singleton: PlatformToolRegistry | None = None


def get_platform_tool_registry() -> PlatformToolRegistry:
    """The deployment catalog (static definitions + unbound services)."""
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = PlatformToolRegistry.build(ToolBindings())
    return _registry_singleton


def set_tool_registry(registry: PlatformToolRegistry) -> None:
    """Executor/tests replace the catalog (per-session hooks, fakes)."""
    global _registry_singleton
    _registry_singleton = registry


def _request_registry(user: User) -> PlatformToolRegistry:
    """Per-request registry with user-scoped service bindings and the
    persistent audit journal.

    rag_search runs with the requesting user's ACL; a sandbox's craft PAT
    resolves to its owning user, so retrieval sees exactly that user's
    documents. Realtime tools bind the deployment-configured MCP gateway,
    search provider and crawler (each degrades to an ``unavailable``
    message when unconfigured). Every tool call lands in
    ``platform_tool_log`` for the audit report page.
    """
    from onyx.db.platform_tool_log import log_tool_call
    from onyx.server.features.build.tools.crawler import build_crawler_client
    from onyx.server.features.build.tools.job_escalation import make_start_job_hook
    from onyx.server.features.build.tools.mcp_gateway import (
        default_gateway_servers,
    )
    from onyx.server.features.build.tools.service_bindings import (
        make_user_scoped_search_fn,
    )
    from onyx.server.features.build.tools.web_search_providers import (
        build_search_provider,
        format_hits,
    )

    def _journal(entry: Any) -> None:
        from onyx.db.engine.sql_engine import get_session_with_current_tenant

        with get_session_with_current_tenant() as db_session:
            log_tool_call(
                db_session,
                user_id=user.id,
                tool=entry.tool,
                arguments=entry.arguments,
                ok=entry.ok,
                result_excerpt=entry.result_text,
                session_id=(UUID(entry.session_id) if entry.session_id else None),
            )

    search_provider = build_search_provider()

    def _web_search(query: str, max_results: int) -> str:
        if search_provider is None:
            raise RuntimeError("no provider")
        return format_hits(query, search_provider.search(query, max_results))

    crawler = build_crawler_client()

    def _crawl(url: str, wait: bool) -> str:
        if crawler is None:
            raise RuntimeError("no crawler")
        result = crawler.crawl_sync(url) if wait else crawler.poll(crawler.submit(url))
        if result.error:
            return f"[crawl] {url}: {result.error}"
        return f"[crawl] {url}\n\n{result.content}"

    gateway = default_gateway_servers(audit=_gateway_audit(user))

    def _mcp_call(server: str, tool: str, arguments: dict[str, Any]) -> str:
        return gateway.call_tool_sync(
            server=server,
            tool=tool,
            arguments=arguments,
            user_id=str(user.id),
        )

    return PlatformToolRegistry.build(
        ToolBindings(
            search_fn=make_user_scoped_search_fn(user),
            mcp_call_fn=_mcp_call,
            web_search_fn=_web_search if search_provider is not None else None,
            crawl_fn=_crawl if crawler is not None else None,
            job_hook=make_start_job_hook(user),
            journal=_journal,
        )
    )


def _gateway_audit(user: User) -> Any:
    """Persist MCP gateway calls into the same audit table."""

    def _audit(call: Any) -> None:
        from onyx.db.engine.sql_engine import get_session_with_current_tenant
        from onyx.db.platform_tool_log import log_tool_call

        with get_session_with_current_tenant() as db_session:
            log_tool_call(
                db_session,
                user_id=user.id,
                tool=f"mcp_call:{call.server}:{call.tool}",
                arguments=call.arguments,
                ok=call.ok,
                result_excerpt=call.error or "",
            )

    return _audit


def _bridge_ctx(user: User) -> ToolContext:
    return ToolContext(user_id=str(user.id), tenant_id=None)


@router.get("/definitions")
def tool_definitions(
    _user: User = Depends(require_permission(Permission.USE_LLM_GATEWAY)),
) -> dict[str, Any]:
    registry = get_platform_tool_registry()
    return {"tools": registry.definitions()}


@router.post("/call")
def call_tool(
    request: ToolCallRequest,
    user: User = Depends(require_permission(Permission.USE_LLM_GATEWAY)),
) -> dict[str, Any]:
    registry = _request_registry(user)
    invocation = ToolInvocation(
        tool=request.tool,
        arguments=request.arguments,
        session_id=request.session_id,
    )
    result = registry.call(invocation, _bridge_ctx(user))
    return {"content": result.content, "terminate": result.terminate}


@router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    user: User = Depends(require_permission(Permission.USE_LLM_GATEWAY)),
) -> dict[str, Any]:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return error_response_parse()
    except Exception:
        return error_response_parse()
    registry = _request_registry(user)
    session_id = request.headers.get(MCP_SESSION_TAG_HEADER) or None
    response = handle_mcp_jsonrpc(body, registry, _bridge_ctx(user), session_id)
    return response if response is not None else {}
