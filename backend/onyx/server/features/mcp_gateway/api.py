from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.configs.app_configs import (
    MCP_GATEWAY_INTERNAL_TOKEN,
    MCP_GATEWAY_PUBLIC_URL,
)
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import (
    MCPAuthenticationPerformer,
    MCPAuthenticationType,
    MCPGatewayRefreshMode,
    MCPServerStatus,
    MCPTransport,
    Permission,
)
from onyx.db.mcp import create_connection_config, create_mcp_server__no_commit
from onyx.db.mcp_gateway import (
    call_stats,
    create_provider__no_commit,
    delete_cache_entries,
    delete_policy,
    delete_provider,
    get_policy,
    get_provider_by_id,
    get_provider_by_slug,
    list_cache_entries,
    list_providers,
    update_provider__no_commit,
    upsert_policy__no_commit,
)
from onyx.db.models import User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.mcp_gateway.engine import enqueue_refresh, invalidate_redis_keys
from onyx.mcp_gateway.packs import list_packs
from onyx.mcp_gateway.policy import merged_pack_and_db_policies
from onyx.mcp_gateway.protocol import invalidate_tools_cache
from onyx.server.features.mcp.models import MCPConnectionData
from onyx.server.features.mcp_gateway.models import (
    CacheEntryResponse,
    InvalidateRequest,
    PackSummary,
    PolicyResponse,
    PolicyUpsertRequest,
    ProviderCreateRequest,
    ProviderResponse,
    ProviderUpdateRequest,
    RefreshRequest,
    StatsResponse,
)
from shared_configs.contextvars import get_current_tenant_id

admin_router = APIRouter(prefix="/admin/mcp-gateway")


def gateway_url_for_slug(slug: str) -> str:
    return f"{MCP_GATEWAY_PUBLIC_URL}/p/{slug}"


def _provider_response(provider: Any) -> ProviderResponse:
    return ProviderResponse(
        id=provider.id,
        slug=provider.slug,
        display_name=provider.display_name,
        pack_slug=provider.pack_slug,
        upstream_url=provider.upstream_url,
        transport=provider.transport,
        auth_adapter=provider.auth_adapter,
        enabled=provider.enabled,
        mcp_server_id=provider.mcp_server_id,
        gateway_url=gateway_url_for_slug(provider.slug),
        tools_list_refreshed_at=provider.tools_list_refreshed_at,
        created_at=provider.created_at,
    )


@admin_router.get("/packs")
def list_provider_packs(
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> list[PackSummary]:
    return [
        PackSummary(
            slug=pack.slug,
            display_name=pack.display_name,
            default_upstream_url=pack.default_upstream_url,
            transport=pack.transport,
            auth_adapter=pack.auth_adapter,
        )
        for pack in list_packs()
    ]


@admin_router.get("/providers")
def list_gateway_providers(
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> list[ProviderResponse]:
    return [_provider_response(item) for item in list_providers(db_session)]


@admin_router.post("/providers")
def create_gateway_provider(
    request: ProviderCreateRequest,
    db_session: Session = Depends(get_session),
    user: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> ProviderResponse:
    existing = get_provider_by_slug(db_session, request.slug)
    if existing is not None:
        raise OnyxError(
            OnyxErrorCode.DUPLICATE_RESOURCE, f"Provider slug '{request.slug}' exists"
        )
    from onyx.mcp_gateway.packs import get_pack

    pack = get_pack(request.pack_slug)
    display_name = request.display_name or pack.display_name
    transport = request.transport or pack.transport
    auth_adapter = request.auth_adapter or pack.auth_adapter
    provider = create_provider__no_commit(
        db_session,
        slug=request.slug,
        display_name=display_name,
        pack_slug=request.pack_slug,
        upstream_url=request.upstream_url,
        transport=transport,
        auth_adapter=auth_adapter,
        credentials=request.credentials,
        enabled=request.enabled,
    )
    if request.attach_mcp_server:
        token = MCP_GATEWAY_INTERNAL_TOKEN
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        config = create_connection_config(
            MCPConnectionData(headers=headers, api_token=token),
            db_session,
            user_email="",
        )
        server = create_mcp_server__no_commit(
            owner_email=user.email,
            name=display_name,
            description=f"Gateway proxy for {display_name}",
            server_url=gateway_url_for_slug(request.slug),
            auth_type=MCPAuthenticationType.API_TOKEN,
            transport=MCPTransport.STREAMABLE_HTTP,
            auth_performer=MCPAuthenticationPerformer.ADMIN,
            db_session=db_session,
            admin_connection_config_id=config.id,
            via_gateway=True,
            gateway_provider_slug=request.slug,
        )
        server.status = MCPServerStatus.CONNECTED
        config.mcp_server_id = server.id
        provider.mcp_server_id = server.id
    db_session.commit()
    invalidate_tools_cache(request.slug)
    return _provider_response(provider)


@admin_router.patch("/providers/{provider_id}")
def update_gateway_provider(
    provider_id: int,
    request: ProviderUpdateRequest,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> ProviderResponse:
    provider = get_provider_by_id(db_session, provider_id)
    update_provider__no_commit(
        db_session,
        provider,
        display_name=request.display_name,
        upstream_url=request.upstream_url,
        transport=request.transport,
        auth_adapter=request.auth_adapter,
        credentials=request.credentials,
        enabled=request.enabled,
    )
    db_session.commit()
    invalidate_tools_cache(provider.slug)
    return _provider_response(provider)


@admin_router.delete("/providers/{provider_id}")
def delete_gateway_provider(
    provider_id: int,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> None:
    provider = get_provider_by_id(db_session, provider_id)
    slug = provider.slug
    delete_provider(db_session, provider)
    invalidate_tools_cache(slug)


@admin_router.get("/providers/{slug}/policies")
def list_gateway_policies(
    slug: str,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> list[PolicyResponse]:
    provider = get_provider_by_slug(db_session, slug)
    if provider is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"Provider '{slug}' not found")
    rows = merged_pack_and_db_policies(db_session, slug, provider.pack_slug)
    return [
        PolicyResponse(
            tool_name=name,
            refresh_mode=spec.refresh_mode,
            ttl_seconds=spec.ttl_seconds,
            swr_seconds=spec.swr_seconds,
            schedule_cron=spec.schedule_cron,
            key_fields=spec.key_fields,
            normalize=spec.normalize,
            cache_empty_ttl_seconds=spec.cache_empty_ttl_seconds,
            max_response_bytes=spec.max_response_bytes,
            is_db_override=is_override,
        )
        for name, spec, is_override in rows
    ]


@admin_router.put("/providers/{slug}/policies")
def upsert_gateway_policy(
    slug: str,
    request: PolicyUpsertRequest,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> PolicyResponse:
    if get_provider_by_slug(db_session, slug) is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"Provider '{slug}' not found")
    if request.refresh_mode == MCPGatewayRefreshMode.SCHEDULE and not request.schedule_cron:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "schedule_cron is required")
    row = upsert_policy__no_commit(
        db_session,
        provider_slug=slug,
        tool_name=request.tool_name,
        refresh_mode=request.refresh_mode,
        ttl_seconds=request.ttl_seconds,
        swr_seconds=request.swr_seconds,
        schedule_cron=request.schedule_cron,
        key_fields=request.key_fields,
        normalize=request.normalize,
        cache_empty_ttl_seconds=request.cache_empty_ttl_seconds,
        max_response_bytes=request.max_response_bytes,
    )
    db_session.commit()
    return PolicyResponse(
        tool_name=row.tool_name,
        refresh_mode=row.refresh_mode,
        ttl_seconds=row.ttl_seconds,
        swr_seconds=row.swr_seconds,
        schedule_cron=row.schedule_cron,
        key_fields=row.key_fields,
        normalize=row.normalize,
        cache_empty_ttl_seconds=row.cache_empty_ttl_seconds,
        max_response_bytes=row.max_response_bytes,
        is_db_override=True,
    )


@admin_router.delete("/providers/{slug}/policies/{tool_name}")
def reset_gateway_policy(
    slug: str,
    tool_name: str,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> None:
    policy = get_policy(db_session, slug, tool_name)
    if policy is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Policy override not found")
    delete_policy(db_session, policy)


@admin_router.get("/cache")
def list_gateway_cache(
    provider_slug: str | None = None,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> list[CacheEntryResponse]:
    tenant_id = get_current_tenant_id()
    entries = list_cache_entries(
        db_session, tenant_id=tenant_id, provider_slug=provider_slug
    )
    return [
        CacheEntryResponse(
            cache_key=item.cache_key,
            provider_slug=item.provider_slug,
            tool_name=item.tool_name,
            effective_tool_name=item.effective_tool_name,
            hit_count=item.hit_count,
            last_fetched_at=item.last_fetched_at,
            last_accessed_at=item.last_accessed_at,
            last_refresh_status=item.last_refresh_status,
        )
        for item in entries
    ]


@admin_router.post("/cache/invalidate")
def invalidate_gateway_cache(
    request: InvalidateRequest,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> dict[str, int]:
    tenant_id = get_current_tenant_id()
    keys: list[str] = []
    if request.cache_key:
        keys.append(request.cache_key)
    deleted = delete_cache_entries(
        db_session,
        tenant_id=tenant_id,
        cache_key=request.cache_key,
        provider_slug=request.provider_slug,
        tool_name=request.tool_name,
    )
    invalidate_redis_keys(tenant_id, keys)
    return {"deleted": deleted}


@admin_router.post("/cache/refresh")
def refresh_gateway_cache(
    request: RefreshRequest,
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> None:
    enqueue_refresh(get_current_tenant_id(), request.cache_key)


@admin_router.get("/stats")
def gateway_stats(
    provider_slug: str | None = None,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.MANAGE_ACTIONS)),
) -> StatsResponse:
    payload = call_stats(
        db_session, tenant_id=get_current_tenant_id(), provider_slug=provider_slug
    )
    return StatsResponse(**payload)
