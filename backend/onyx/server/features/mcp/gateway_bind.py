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
from onyx.db.mcp import (
    create_connection_config,
    create_mcp_server__no_commit,
    update_connection_config__no_commit,
)
from onyx.db.mcp_catalog import (
    create_catalog_entry__no_commit,
    delete_catalog_entry__no_commit,
    get_catalog_entry_by_slug,
    update_catalog_entry__no_commit,
)
from onyx.db.models import MCPCatalogEntry, MCPServer, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.mcp_gateway.auth_adapters import entry_credentials
from onyx.mcp_gateway.protocol import invalidate_tools_cache
from onyx.mcp_gateway.registry import get_pack
from onyx.mcp_gateway.service import is_gateway_enabled
from onyx.mcp_gateway.upstream import UpstreamTarget
from onyx.server.features.mcp.client import discover_mcp_tools
from onyx.server.features.mcp.credentials import extract_connection_data
from onyx.server.features.mcp.models import (
    MCPConnectionData,
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


def credentials_from_admin_config(server: MCPServer) -> dict[str, Any]:
    """Copy usable header/token values from the admin connection config."""
    config = server.admin_connection_config
    if config is None:
        return {}
    data = extract_connection_data(config, apply_mask=False)
    headers = dict(data.get("headers") or {})
    creds: dict[str, Any] = {}
    extra: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            auth = str(value)
            if auth.lower().startswith("bearer "):
                creds["api_key"] = auth[7:].strip()
            else:
                creds["authorization"] = auth
        else:
            extra[str(key)] = str(value)
    api_token = data.get("api_token")
    if api_token and "api_key" not in creds:
        creds["api_key"] = str(api_token)
    if extra:
        creds["extra_headers"] = extra
    return creds


def catalog_credentials_to_connection_data(
    creds: dict[str, Any],
    existing: MCPConnectionData | None = None,
) -> MCPConnectionData:
    """Turn catalog credential keys into an admin connection-config payload."""
    headers: dict[str, str] = {}
    extra = creds.get("extra_headers")
    if isinstance(extra, dict):
        headers.update({str(key): str(value) for key, value in extra.items()})
    api_token: str | None = None
    api_key = creds.get("api_key")
    authorization = creds.get("authorization")
    if isinstance(api_key, str) and api_key:
        api_token = api_key
        headers.setdefault("Authorization", f"Bearer {api_key}")
    elif isinstance(authorization, str) and authorization:
        headers.setdefault("Authorization", authorization)
        if authorization.startswith("Bearer "):
            api_token = authorization[7:].strip()
        else:
            api_token = authorization

    merged: MCPConnectionData = MCPConnectionData(headers=headers)
    if existing is not None:
        header_template = existing.get("header_template")
        if header_template is not None:
            merged["header_template"] = header_template
        header_substitutions = existing.get("header_substitutions")
        if header_substitutions is not None:
            merged["header_substitutions"] = header_substitutions
        required_fields = existing.get("required_fields")
        if required_fields is not None:
            merged["required_fields"] = required_fields
        client_info = existing.get("client_info")
        if client_info is not None:
            merged["client_info"] = client_info
        tokens = existing.get("tokens")
        if tokens is not None:
            merged["tokens"] = tokens
        metadata = existing.get("metadata")
        if metadata is not None:
            merged["metadata"] = metadata
        token_expires_at = existing.get("token_expires_at")
        if token_expires_at is not None:
            merged["token_expires_at"] = token_expires_at
        if not api_token:
            existing_token = existing.get("api_token")
            if existing_token:
                api_token = existing_token
                merged["headers"] = headers or dict(existing.get("headers") or {})
    if api_token:
        merged["api_token"] = api_token
    return merged


def _write_catalog_credentials_to_admin(
    db_session: Session, server: MCPServer, creds: dict[str, Any]
) -> None:
    if not creds:
        return
    existing = (
        extract_connection_data(server.admin_connection_config, apply_mask=False)
        if server.admin_connection_config is not None
        else None
    )
    config_data = catalog_credentials_to_connection_data(creds, existing)
    if server.admin_connection_config_id is not None:
        update_connection_config__no_commit(
            server.admin_connection_config_id, db_session, config_data
        )
        return
    new_config = create_connection_config(
        config_data, db_session, mcp_server_id=server.id
    )
    server.admin_connection_config_id = new_config.id


def _mark_server_bound(server: MCPServer, entry: MCPCatalogEntry) -> None:
    server.catalog_entry_id = entry.id
    server.server_url = gateway_url_for_slug(entry.slug)
    if server.auth_type is None:
        server.auth_type = MCPAuthenticationType.API_TOKEN
    if server.auth_performer is None:
        server.auth_performer = MCPAuthenticationPerformer.ADMIN
    if server.transport is None:
        server.transport = entry.transport
    server.status = MCPServerStatus.CONNECTED


def _resolve_auth_adapter(
    request: MCPGatewayBindingRequest, pack_adapter: MCPGatewayAuthAdapter
) -> MCPGatewayAuthAdapter:
    if request.auth_adapter:
        return MCPGatewayAuthAdapter(request.auth_adapter)
    return pack_adapter


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
    upstream_url = (
        request.upstream_url or pack.default_upstream_url or server.server_url
    )
    if not upstream_url:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "upstream_url is required")

    credentials = request.credentials or credentials_from_admin_config(server)
    entry = create_catalog_entry__no_commit(
        db_session,
        slug=slug,
        display_name=server.name,
        description=server.description,
        upstream_url=upstream_url,
        transport=server.transport or pack.transport,
        auth_adapter=_resolve_auth_adapter(request, pack.auth_adapter),
        credentials=credentials,
        pack_slug=pack.slug,
        policy_overrides=request.policy_overrides,
        enabled=True,
        is_public=server.is_public,
    )
    _mark_server_bound(server, entry)
    db_session.flush()
    invalidate_tools_cache(get_current_tenant_id(), entry.slug)
    return entry


def update_org_server_gateway_binding(
    db_session: Session,
    server: MCPServer,
    request: MCPGatewayBindingRequest,
) -> MCPCatalogEntry:
    """Update an existing binding. Keep the slug and gateway URL."""
    require_gateway_enabled()
    _reject_personal(server)
    _reject_per_user(server)
    entry = server.catalog_entry
    if entry is None:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "This MCP server is not bound to the gateway.",
        )

    pack = get_pack(request.pack_slug or entry.pack_slug)
    pack_changed = request.pack_slug is not None and pack.slug != entry.pack_slug
    policy_overrides = request.policy_overrides
    if policy_overrides is None and pack_changed:
        entry.policy_overrides = None

    update_catalog_entry__no_commit(
        db_session,
        entry,
        display_name=server.name,
        description=server.description,
        upstream_url=request.upstream_url,
        auth_adapter=(
            _resolve_auth_adapter(request, pack.auth_adapter)
            if pack_changed or request.auth_adapter
            else None
        ),
        credentials=request.credentials or None,
        pack_slug=pack.slug if pack_changed else None,
        policy_overrides=policy_overrides,
        is_public=server.is_public,
    )
    invalidate_tools_cache(get_current_tenant_id(), entry.slug)
    return entry


def upsert_org_server_gateway_binding(
    db_session: Session,
    server: MCPServer,
    request: MCPGatewayBindingRequest,
) -> MCPCatalogEntry:
    """Bind a direct server, or update an already-bound one."""
    if server.catalog_entry_id is None:
        return bind_org_server_to_gateway(db_session, server, request)
    return update_org_server_gateway_binding(db_session, server, request)


def rediscover_direct_tools(db_session: Session, server: MCPServer) -> str | None:
    """Rediscover tools on the upstream after an unbind. Keep the server if it fails."""
    from onyx.server.features.mcp.api import sync_mcp_server_tools

    data = extract_connection_data(server.admin_connection_config, apply_mask=False)
    headers = dict(data.get("headers") or {})
    transport = server.transport or MCPTransport.STREAMABLE_HTTP
    try:
        discovered = discover_mcp_tools(
            server.server_url,
            connection_headers=headers,
            transport=transport,
        )
    except Exception as error:
        logger.warning(
            "Could not rediscover tools for unbound MCP '%s': %s",
            server.name,
            error,
        )
        return str(error)

    sync_mcp_server_tools(server.id, discovered, db_session)
    return None


def unbind_org_server_from_gateway(db_session: Session, server: MCPServer) -> None:
    """Restore the upstream URL, copy catalog credentials back, and drop the binding."""
    entry = server.catalog_entry
    if entry is None:
        return
    slug = entry.slug
    creds = entry_credentials(entry)
    _write_catalog_credentials_to_admin(db_session, server, creds)
    if server.transport is None:
        server.transport = entry.transport
    server.server_url = entry.upstream_url
    server.catalog_entry_id = None
    db_session.flush()
    delete_catalog_entry__no_commit(db_session, entry)
    db_session.expire(server, ["catalog_entry"])
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
