"""Bind an organization MCP server to the gateway.

The catalog row is the binding, not a second product catalog. Packs always
bind. Custom URLs bind only when the admin opts in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session

from onyx.configs.app_configs import MCP_GATEWAY_PUBLIC_URL
from onyx.db.enums import (
    MCPAuthenticationPerformer,
    MCPAuthenticationType,
    MCPGatewayAuthAdapter,
    MCPServerScope,
    MCPServerStatus,
    MCPTransport,
)
from onyx.db.mcp import create_mcp_server__no_commit
from onyx.db.mcp_catalog import (
    create_catalog_entry__no_commit,
    delete_catalog_entry,
    get_catalog_entry_by_slug,
)
from onyx.db.models import MCPCatalogEntry, MCPServer, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.mcp_gateway.protocol import invalidate_tools_cache
from onyx.mcp_gateway.registry import get_pack
from onyx.mcp_gateway.service import is_gateway_enabled
from onyx.mcp_gateway.upstream import UpstreamTarget
from onyx.server.features.mcp.client import discover_mcp_tools
from onyx.server.features.mcp.models import (
    MCPFromPackRequest,
    MCPGatewayBindingRequest,
)
from onyx.server.features.mcp_catalog.slug import catalog_slug_from_input
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import get_current_tenant_id

logger = setup_logger()


def gateway_url_for_slug(slug: str) -> str:
    return f"{MCP_GATEWAY_PUBLIC_URL}/p/{slug}"


def require_gateway_enabled() -> None:
    if not is_gateway_enabled():
        raise OnyxError(
            OnyxErrorCode.FEATURE_NOT_AVAILABLE,
            "The MCP Gateway module is turned off.",
        )


def discover_and_store_bound_tools(
    db_session: Session, entry: MCPCatalogEntry, mcp_server_id: int
) -> str | None:
    """Discover tools on the upstream. Keep the binding if discovery fails."""
    from onyx.server.features.mcp.api import sync_mcp_server_tools

    target = UpstreamTarget.from_entry(entry)
    try:
        discovered = discover_mcp_tools(
            target.url,
            connection_headers=target.headers,
            transport=target.transport,
        )
    except Exception as error:
        logger.warning(
            "Could not discover tools for gateway MCP '%s': %s", entry.slug, error
        )
        return str(error)

    sync_mcp_server_tools(mcp_server_id, discovered, db_session)
    entry.tools_list_refreshed_at = datetime.now(timezone.utc)
    db_session.commit()
    return None


def _unique_slug(db_session: Session, raw: str) -> str:
    slug = catalog_slug_from_input(raw)
    if get_catalog_entry_by_slug(db_session, slug) is None:
        return slug
    raise OnyxError(
        OnyxErrorCode.DUPLICATE_RESOURCE,
        f"A gateway binding with slug '{slug}' already exists",
    )


def _reject_personal(server: MCPServer) -> None:
    if server.scope == MCPServerScope.PERSONAL:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Personal MCP servers cannot use the gateway.",
        )


def _reject_per_user(server: MCPServer) -> None:
    if server.auth_performer == MCPAuthenticationPerformer.PER_USER:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Gateway-bound servers cannot use per-user authentication.",
        )


def bind_org_server_to_gateway(
    db_session: Session,
    server: MCPServer,
    request: MCPGatewayBindingRequest,
) -> MCPCatalogEntry:
    """Attach a gateway binding to an existing organization server."""
    require_gateway_enabled()
    _reject_personal(server)
    _reject_per_user(server)
    if server.catalog_entry_id is not None:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "This MCP server is already bound to the gateway.",
        )

    pack = get_pack(request.pack_slug)
    slug = _unique_slug(db_session, request.slug or server.name)
    upstream_url = request.upstream_url or pack.default_upstream_url or server.server_url
    if not upstream_url:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "upstream_url is required")

    auth_adapter = (
        MCPGatewayAuthAdapter(request.auth_adapter)
        if request.auth_adapter
        else pack.auth_adapter
    )
    entry = create_catalog_entry__no_commit(
        db_session,
        slug=slug,
        display_name=server.name,
        description=server.description,
        upstream_url=upstream_url,
        transport=server.transport or pack.transport,
        auth_adapter=auth_adapter,
        credentials=request.credentials,
        pack_slug=pack.slug,
        policy_overrides=request.policy_overrides,
        enabled=True,
        is_public=server.is_public,
    )
    server.catalog_entry_id = entry.id
    server.server_url = gateway_url_for_slug(entry.slug)
    if server.auth_type is None:
        server.auth_type = MCPAuthenticationType.API_TOKEN
    if server.auth_performer is None:
        server.auth_performer = MCPAuthenticationPerformer.ADMIN
    server.status = MCPServerStatus.CONNECTED
    db_session.flush()
    invalidate_tools_cache(get_current_tenant_id(), entry.slug)
    return entry


def unbind_org_server_from_gateway(db_session: Session, server: MCPServer) -> None:
    """Restore the upstream URL and drop the binding row."""
    entry = server.catalog_entry
    if entry is None:
        return
    slug = entry.slug
    server.server_url = entry.upstream_url
    server.catalog_entry_id = None
    db_session.flush()
    delete_catalog_entry(db_session, entry)
    invalidate_tools_cache(get_current_tenant_id(), slug)


def create_org_server_from_pack(
    db_session: Session,
    user: User,
    request: MCPFromPackRequest,
    apply_access: Any,
) -> tuple[MCPServer, MCPCatalogEntry, str | None]:
    """Install a pack as an organization MCP that routes through the gateway."""
    require_gateway_enabled()
    pack = get_pack(request.pack_slug)
    display_name = request.name or pack.display_name
    slug = _unique_slug(db_session, request.slug or display_name)
    upstream_url = request.upstream_url or pack.default_upstream_url
    if not upstream_url:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "This pack has no default URL. Set upstream_url.",
        )

    entry = create_catalog_entry__no_commit(
        db_session,
        slug=slug,
        display_name=display_name,
        description=request.description or pack.description or None,
        upstream_url=upstream_url,
        transport=pack.transport,
        auth_adapter=pack.auth_adapter,
        credentials=request.credentials,
        pack_slug=pack.slug,
        policy_overrides=request.policy_overrides,
        enabled=True,
        is_public=request.is_public,
    )
    server = create_mcp_server__no_commit(
        owner_email=user.email,
        name=display_name,
        description=request.description or pack.description,
        server_url=gateway_url_for_slug(entry.slug),
        auth_type=MCPAuthenticationType.API_TOKEN,
        transport=entry.transport or MCPTransport.STREAMABLE_HTTP,
        auth_performer=MCPAuthenticationPerformer.ADMIN,
        db_session=db_session,
        is_public=request.is_public,
        scope=MCPServerScope.USER,
        catalog_entry_id=entry.id,
    )
    server.status = MCPServerStatus.CONNECTED
    apply_access(
        mcp_server=server,
        acting_user=user,
        is_public=request.is_public,
        user_ids=request.users,
        group_ids=request.groups,
        is_new=True,
        db_session=db_session,
    )
    db_session.commit()
    invalidate_tools_cache(get_current_tenant_id(), entry.slug)
    error = discover_and_store_bound_tools(db_session, entry, server.id)
    return server, entry, error
