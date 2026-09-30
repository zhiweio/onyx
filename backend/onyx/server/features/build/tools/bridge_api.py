"""Agent-facing bridge: REST + MCP endpoints for the platform tool catalog.

The sandbox reaches these through the egress proxy, which injects the
per-sandbox craft PAT (see ``sandbox_proxy/resolvers/onyx_pat.py``); the
standard permission dependency resolves that PAT to the owning user, so
tool calls execute with the user's permissions.
"""

from __future__ import annotations

from typing import Any

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
    prefix="/build/agent-tools",
    dependencies=[
        Depends(_require_onyx_craft_enabled_bridge),
        Depends(require_permission(Permission.BASIC_ACCESS)),
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
    """Per-request registry with user-scoped service bindings.

    rag_search runs with the requesting user's ACL; a sandbox's craft PAT
    resolves to its owning user, so retrieval sees exactly that user's
    documents.
    """
    from onyx.server.features.build.tools.service_bindings import (
        make_user_scoped_search_fn,
    )

    return PlatformToolRegistry.build(
        ToolBindings(search_fn=make_user_scoped_search_fn(user))
    )


def _bridge_ctx(user: User) -> ToolContext:
    return ToolContext(user_id=str(user.id), tenant_id=None)


@router.get("/definitions")
def tool_definitions(user: User = Depends(require_permission(Permission.BASIC_ACCESS))) -> dict[str, Any]:
    registry = get_platform_tool_registry()
    return {"tools": registry.definitions()}


@router.post("/call")
def call_tool(
    request: ToolCallRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
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
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
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
