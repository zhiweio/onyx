"""System MCP catalog: admin install/grant, ops view, and the user settings surface.

Three routers, three audiences:

- `admin_router` (`/admin/mcp-catalog`) — install a system MCP, hold its shared
  credentials, grant it to groups. Gated on MANAGE_SYSTEM_MCP.
- `ops_router` (`/admin/mcp-gateway`) — cache hit rate, stored bytes, and
  invalidation. Same gate, separate surface so the two do not blur together.
- `user_router` (`/mcp-catalog`) — what a user has been granted, and their own
  on/off switch.

Every route refuses to do anything when the gateway module is off. That is what
makes this a removable brick rather than a permanent fixture.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.configs.app_configs import MCP_GATEWAY_PUBLIC_URL
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import (
    MCPAuthenticationPerformer,
    MCPAuthenticationType,
    MCPServerScope,
    MCPServerStatus,
    Permission,
)
from onyx.db.mcp import (
    create_mcp_server__no_commit,
    delete_mcp_server,
    get_all_mcp_tools_for_server,
)
from onyx.db.mcp_catalog import (
    accessible_system_server_ids,
    create_catalog_entry__no_commit,
    delete_catalog_entry,
    get_catalog_entry_by_id,
    get_catalog_entry_by_slug,
    get_catalog_entry_group_ids,
    get_enabled_system_server_ids,
    list_catalog_entries,
    list_catalog_entries_for_user,
    set_catalog_entry_groups__no_commit,
    set_system_server_enabled,
    update_catalog_entry__no_commit,
)
from onyx.db.mcp_gateway import (
    blob_storage_summary,
    call_stats,
    delete_cache_entries,
    list_cache_entries,
)
from onyx.db.models import MCPCatalogEntry, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.mcp_gateway.engine import enqueue_refresh, invalidate_cache_keys
from onyx.mcp_gateway.policy import effective_policies
from onyx.mcp_gateway.protocol import invalidate_tools_cache
from onyx.mcp_gateway.registry import get_pack, list_packs
from onyx.mcp_gateway.service import is_gateway_enabled
from onyx.mcp_gateway.upstream import UpstreamTarget
from onyx.server.features.mcp.api import sync_mcp_server_tools
from onyx.server.features.mcp.client import discover_mcp_tools
from onyx.server.features.mcp_catalog.models import (
    CacheEntryResponse,
    CatalogEntryCreateRequest,
    CatalogEntryResponse,
    CatalogEntryUpdateRequest,
    InvalidateRequest,
    PackSummary,
    PolicyResponse,
    RefreshRequest,
    SetEnablementRequest,
    StatsResponse,
    SystemMCPServerResponse,
)
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import get_current_tenant_id

logger = setup_logger()

admin_router = APIRouter(prefix="/admin/mcp-catalog")
ops_router = APIRouter(prefix="/admin/mcp-gateway")
user_router = APIRouter(prefix="/mcp-catalog")

_MANAGE = require_permission(Permission.MANAGE_SYSTEM_MCP)
_BASIC = require_permission(Permission.BASIC_ACCESS)


def _require_module_enabled() -> None:
    if not is_gateway_enabled():
        raise OnyxError(
            OnyxErrorCode.FEATURE_NOT_AVAILABLE,
            "The MCP Gateway module is turned off.",
        )


def gateway_url_for_slug(slug: str) -> str:
    return f"{MCP_GATEWAY_PUBLIC_URL}/p/{slug}"


def _discover_and_store_tools(
    db_session: Session, entry: MCPCatalogEntry, mcp_server_id: int
) -> str | None:
    """Fetch the upstream's tool list and store it against the system server.

    Discovery goes straight to the upstream with the admin's credentials rather
    than through the gateway: the gateway may not have loaded a just-created
    entry yet, and a direct call surfaces a bad URL or key as a real error the
    admin can act on.

    Returns an error message on failure. The caller keeps the entry either way —
    an admin who mistyped a key should be able to fix it and retry, not have to
    reinstall.
    """
    target = UpstreamTarget.from_entry(entry)
    try:
        discovered = discover_mcp_tools(
            target.url,
            connection_headers=target.headers,
            transport=target.transport,
        )
    except Exception as error:
        logger.warning(
            "Could not discover tools for system MCP '%s': %s", entry.slug, error
        )
        return str(error)

    sync_mcp_server_tools(mcp_server_id, discovered, db_session)
    entry.tools_list_refreshed_at = datetime.now(timezone.utc)
    db_session.commit()
    return None


def _entry_response(
    entry: MCPCatalogEntry,
    db_session: Session,
    discovery_error: str | None = None,
) -> CatalogEntryResponse:
    server = entry.mcp_server
    tool_count = (
        len(get_all_mcp_tools_for_server(server.id, db_session)) if server else 0
    )
    return CatalogEntryResponse(
        discovery_error=discovery_error,
        id=entry.id,
        slug=entry.slug,
        display_name=entry.display_name,
        description=entry.description,
        pack_slug=entry.pack_slug,
        upstream_url=entry.upstream_url,
        transport=entry.transport,
        auth_adapter=entry.auth_adapter,
        enabled=entry.enabled,
        is_public=entry.is_public,
        origin=entry.origin,
        group_ids=get_catalog_entry_group_ids(db_session, entry.id),
        mcp_server_id=server.id if server else None,
        gateway_url=gateway_url_for_slug(entry.slug),
        tool_count=tool_count,
        tools_list_refreshed_at=entry.tools_list_refreshed_at,
        created_at=entry.created_at,
        has_credentials=entry.credentials is not None,
    )


# ---------------------------------------------------------------------------
# Admin: catalog
# ---------------------------------------------------------------------------


@admin_router.get("/packs")
def list_provider_packs(_: User = Depends(_MANAGE)) -> list[PackSummary]:
    return [
        PackSummary(
            slug=pack.slug,
            display_name=pack.display_name,
            description=pack.description,
            default_upstream_url=pack.default_upstream_url,
            transport=pack.transport,
            auth_adapter=pack.auth_adapter,
        )
        for pack in list_packs()
    ]


@admin_router.get("/entries")
def list_entries(
    db_session: Session = Depends(get_session),
    _: User = Depends(_MANAGE),
) -> list[CatalogEntryResponse]:
    return [
        _entry_response(entry, db_session) for entry in list_catalog_entries(db_session)
    ]


@admin_router.post("/entries")
def create_entry(
    request: CatalogEntryCreateRequest,
    db_session: Session = Depends(get_session),
    user: User = Depends(_MANAGE),
) -> CatalogEntryResponse:
    _require_module_enabled()
    if get_catalog_entry_by_slug(db_session, request.slug) is not None:
        raise OnyxError(
            OnyxErrorCode.DUPLICATE_RESOURCE,
            f"A system MCP with slug '{request.slug}' already exists",
        )

    pack = get_pack(request.pack_slug)
    # Fall back to the slug, not the pack name: every generic entry sharing the
    # name "Generic HTTP MCP" would be unusable in a list.
    display_name = request.display_name or request.slug
    entry = create_catalog_entry__no_commit(
        db_session,
        slug=request.slug,
        display_name=display_name,
        description=request.description or pack.description or None,
        upstream_url=request.upstream_url or pack.default_upstream_url,
        transport=request.transport or pack.transport,
        auth_adapter=request.auth_adapter or pack.auth_adapter,
        credentials=request.credentials,
        pack_slug=pack.slug,
        policy_overrides=request.policy_overrides,
        enabled=request.enabled,
        is_public=request.is_public,
    )

    # The catalog entry is admin-facing; this is the row the chat tool loop
    # actually calls. It points at the gateway, never at the upstream, so the
    # shared credentials stay on the entry.
    server = create_mcp_server__no_commit(
        owner_email=user.email,
        name=display_name,
        description=request.description or f"System MCP: {display_name}",
        server_url=gateway_url_for_slug(entry.slug),
        auth_type=MCPAuthenticationType.API_TOKEN,
        transport=entry.transport,
        auth_performer=MCPAuthenticationPerformer.ADMIN,
        db_session=db_session,
        is_public=False,
        scope=MCPServerScope.SYSTEM,
        catalog_entry_id=entry.id,
    )
    server.status = MCPServerStatus.CONNECTED

    set_catalog_entry_groups__no_commit(db_session, entry.id, request.group_ids)
    db_session.commit()
    invalidate_tools_cache(get_current_tenant_id(), entry.slug)

    # Without this the entry exists but has no tools, so the server is installed
    # and useless. Do it inline so the admin sees the outcome immediately.
    error = _discover_and_store_tools(db_session, entry, server.id)
    return _entry_response(entry, db_session, discovery_error=error)


@admin_router.patch("/entries/{entry_id}")
def update_entry(
    entry_id: int,
    request: CatalogEntryUpdateRequest,
    db_session: Session = Depends(get_session),
    _: User = Depends(_MANAGE),
) -> CatalogEntryResponse:
    _require_module_enabled()
    entry = get_catalog_entry_by_id(db_session, entry_id)

    update_catalog_entry__no_commit(
        db_session,
        entry,
        display_name=request.display_name,
        description=request.description,
        upstream_url=request.upstream_url,
        transport=request.transport,
        auth_adapter=request.auth_adapter,
        credentials=request.credentials,
        pack_slug=request.pack_slug,
        policy_overrides=request.policy_overrides,
        enabled=request.enabled,
        is_public=request.is_public,
    )
    if request.group_ids is not None:
        set_catalog_entry_groups__no_commit(db_session, entry.id, request.group_ids)

    server = entry.mcp_server
    if server is not None:
        if request.display_name is not None:
            server.name = request.display_name
        if request.transport is not None:
            server.transport = request.transport

    db_session.commit()
    invalidate_tools_cache(get_current_tenant_id(), entry.slug)

    # A changed URL or key means a different tool list; re-read it rather than
    # leave the old one attached.
    error: str | None = None
    if server is not None and (
        request.upstream_url is not None
        or request.credentials is not None
        or request.transport is not None
        or request.auth_adapter is not None
    ):
        error = _discover_and_store_tools(db_session, entry, server.id)
    return _entry_response(entry, db_session, discovery_error=error)


@admin_router.post("/entries/{entry_id}/refresh-tools")
def refresh_entry_tools(
    entry_id: int,
    db_session: Session = Depends(get_session),
    _: User = Depends(_MANAGE),
) -> CatalogEntryResponse:
    """Re-read the upstream's tool list, for instance after fixing a key."""
    _require_module_enabled()
    entry = get_catalog_entry_by_id(db_session, entry_id)
    if entry.mcp_server is None:
        raise OnyxError(
            OnyxErrorCode.NOT_FOUND, "This system MCP has no server to refresh"
        )
    invalidate_tools_cache(get_current_tenant_id(), entry.slug)
    error = _discover_and_store_tools(db_session, entry, entry.mcp_server.id)
    return _entry_response(entry, db_session, discovery_error=error)


@admin_router.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: int,
    db_session: Session = Depends(get_session),
    _: User = Depends(_MANAGE),
) -> None:
    entry = get_catalog_entry_by_id(db_session, entry_id)
    slug = entry.slug
    # Delete the server first so its tools and any per-user enablement go with
    # it; the entry's cascade would orphan the tool rows otherwise.
    if entry.mcp_server is not None:
        delete_mcp_server(entry.mcp_server.id, db_session)
    delete_catalog_entry(db_session, entry)
    invalidate_tools_cache(get_current_tenant_id(), slug)


@admin_router.get("/entries/{entry_id}/policies")
def list_entry_policies(
    entry_id: int,
    db_session: Session = Depends(get_session),
    _: User = Depends(_MANAGE),
) -> list[PolicyResponse]:
    entry = get_catalog_entry_by_id(db_session, entry_id)
    return [
        PolicyResponse(
            label=label,
            refresh_mode=spec.refresh_mode,
            ttl_seconds=spec.ttl_seconds,
            swr_seconds=spec.swr_seconds,
            schedule_cron=spec.schedule_cron,
            key_fields=spec.key_fields,
            cache_empty_ttl_seconds=spec.cache_empty_ttl_seconds,
            inline_threshold_bytes=spec.inline_threshold_bytes,
            max_response_bytes=spec.max_response_bytes,
            digest_max_bytes=spec.digest_max_bytes,
            is_override=is_override,
        )
        for label, spec, is_override in effective_policies(
            entry.pack_slug, entry.policy_overrides
        )
    ]


# ---------------------------------------------------------------------------
# Admin: gateway operations
# ---------------------------------------------------------------------------


@ops_router.get("/cache")
def list_gateway_cache(
    catalog_slug: str | None = None,
    db_session: Session = Depends(get_session),
    _: User = Depends(_MANAGE),
) -> list[CacheEntryResponse]:
    return [
        CacheEntryResponse(
            cache_key=item.cache_key,
            catalog_slug=item.catalog_slug,
            tool_name=item.tool_name,
            effective_tool_name=item.effective_tool_name,
            hit_count=item.hit_count,
            size_bytes=item.blob.size_bytes if item.blob else 0,
            storage=item.blob.storage.value if item.blob else "unknown",
            last_fetched_at=item.last_fetched_at,
            last_accessed_at=item.last_accessed_at,
            last_refresh_status=item.last_refresh_status,
        )
        for item in list_cache_entries(db_session, catalog_slug=catalog_slug)
    ]


@ops_router.post("/cache/invalidate")
def invalidate_gateway_cache(
    request: InvalidateRequest,
    db_session: Session = Depends(get_session),
    _: User = Depends(_MANAGE),
) -> dict[str, int]:
    # Collect the keys before deleting the rows, otherwise a slug- or
    # tool-wide invalidation leaves the hot tier serving what the durable tier
    # no longer has.
    doomed = [
        entry.cache_key
        for entry in list_cache_entries(
            db_session, catalog_slug=request.catalog_slug, limit=10_000
        )
        if request.cache_key is None or entry.cache_key == request.cache_key
    ]
    deleted = delete_cache_entries(
        db_session,
        cache_key=request.cache_key,
        catalog_slug=request.catalog_slug,
        tool_name=request.tool_name,
    )
    invalidate_cache_keys(get_current_tenant_id(), doomed)
    return {"deleted": deleted}


@ops_router.post("/cache/refresh")
def refresh_gateway_cache(
    request: RefreshRequest,
    _: User = Depends(_MANAGE),
) -> None:
    _require_module_enabled()
    enqueue_refresh(get_current_tenant_id(), request.cache_key)


@ops_router.get("/stats")
def gateway_stats(
    catalog_slug: str | None = None,
    db_session: Session = Depends(get_session),
    _: User = Depends(_MANAGE),
) -> StatsResponse:
    calls = call_stats(db_session, catalog_slug=catalog_slug)
    blobs = blob_storage_summary(db_session)
    return StatsResponse(
        **calls,
        blob_total_count=blobs["total_count"],
        blob_total_bytes=blobs["total_bytes"],
        blob_by_storage=blobs["by_storage"],
    )


# ---------------------------------------------------------------------------
# User: what I was granted, and my own switch
# ---------------------------------------------------------------------------


@user_router.get("/servers")
def list_system_servers_for_user(
    db_session: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> list[SystemMCPServerResponse]:
    """System MCP servers this user may turn on. Empty when the module is off."""
    if not is_gateway_enabled():
        return []

    enabled_ids = get_enabled_system_server_ids(db_session, user.id)
    responses: list[SystemMCPServerResponse] = []
    for entry in list_catalog_entries_for_user(db_session, user):
        server = entry.mcp_server
        if server is None:
            continue
        responses.append(
            SystemMCPServerResponse(
                mcp_server_id=server.id,
                catalog_slug=entry.slug,
                display_name=entry.display_name,
                description=entry.description,
                enabled_for_user=server.id in enabled_ids,
                tool_count=len(get_all_mcp_tools_for_server(server.id, db_session)),
            )
        )
    return responses


@user_router.put("/servers/{mcp_server_id}/enabled")
def set_system_server_enablement(
    mcp_server_id: int,
    request: SetEnablementRequest,
    db_session: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> SetEnablementRequest:
    _require_module_enabled()
    if mcp_server_id not in accessible_system_server_ids(db_session, user):
        raise OnyxError(
            OnyxErrorCode.NOT_FOUND, "That system MCP server is not available to you"
        )
    set_system_server_enabled(db_session, user.id, mcp_server_id, request.enabled)
    return request
