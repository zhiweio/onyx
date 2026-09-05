from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Integer, delete, desc, func, select, update
from sqlalchemy.orm import Session

from onyx.db.enums import (
    MCPGatewayAuthAdapter,
    MCPGatewayCallOutcome,
    MCPGatewayRefreshMode,
    MCPTransport,
)
from onyx.db.models import (
    MCPGatewayCacheEntry,
    MCPGatewayCachePolicy,
    MCPGatewayCallLog,
    MCPGatewayProvider,
    MCPServer,
)


def get_provider_by_slug(
    db_session: Session, slug: str
) -> MCPGatewayProvider | None:
    return db_session.scalar(
        select(MCPGatewayProvider).where(MCPGatewayProvider.slug == slug)
    )


def get_provider_by_id(db_session: Session, provider_id: int) -> MCPGatewayProvider:
    provider = db_session.scalar(
        select(MCPGatewayProvider).where(MCPGatewayProvider.id == provider_id)
    )
    if provider is None:
        raise ValueError(f"MCP gateway provider {provider_id} does not exist")
    return provider


def list_providers(db_session: Session, enabled_only: bool = False) -> list[MCPGatewayProvider]:
    stmt = select(MCPGatewayProvider).order_by(MCPGatewayProvider.slug)
    if enabled_only:
        stmt = stmt.where(MCPGatewayProvider.enabled.is_(True))
    return list(db_session.scalars(stmt).all())


def create_provider__no_commit(
    db_session: Session,
    *,
    slug: str,
    display_name: str,
    pack_slug: str,
    upstream_url: str,
    transport: MCPTransport,
    auth_adapter: MCPGatewayAuthAdapter,
    credentials: dict[str, Any],
    mcp_server_id: int | None = None,
    enabled: bool = True,
) -> MCPGatewayProvider:
    provider = MCPGatewayProvider(
        slug=slug,
        display_name=display_name,
        pack_slug=pack_slug,
        upstream_url=upstream_url,
        transport=transport,
        auth_adapter=auth_adapter,
        credentials=credentials,
        mcp_server_id=mcp_server_id,
        enabled=enabled,
    )
    db_session.add(provider)
    db_session.flush()
    return provider


def update_provider__no_commit(
    db_session: Session,
    provider: MCPGatewayProvider,
    *,
    display_name: str | None = None,
    upstream_url: str | None = None,
    transport: MCPTransport | None = None,
    auth_adapter: MCPGatewayAuthAdapter | None = None,
    credentials: dict[str, Any] | None = None,
    mcp_server_id: int | None = None,
    enabled: bool | None = None,
    tools_list_refreshed_at: datetime | None = None,
) -> MCPGatewayProvider:
    if display_name is not None:
        provider.display_name = display_name
    if upstream_url is not None:
        provider.upstream_url = upstream_url
    if transport is not None:
        provider.transport = transport
    if auth_adapter is not None:
        provider.auth_adapter = auth_adapter
    if credentials is not None:
        provider.credentials = credentials
    if mcp_server_id is not None:
        provider.mcp_server_id = mcp_server_id
    if enabled is not None:
        provider.enabled = enabled
    if tools_list_refreshed_at is not None:
        provider.tools_list_refreshed_at = tools_list_refreshed_at
    db_session.flush()
    return provider


def delete_provider(db_session: Session, provider: MCPGatewayProvider) -> None:
    db_session.delete(provider)
    db_session.commit()


def list_policies_for_provider(
    db_session: Session, provider_slug: str
) -> list[MCPGatewayCachePolicy]:
    return list(
        db_session.scalars(
            select(MCPGatewayCachePolicy)
            .where(MCPGatewayCachePolicy.provider_slug == provider_slug)
            .order_by(MCPGatewayCachePolicy.tool_name)
        ).all()
    )


def get_policy(
    db_session: Session, provider_slug: str, tool_name: str
) -> MCPGatewayCachePolicy | None:
    return db_session.scalar(
        select(MCPGatewayCachePolicy).where(
            MCPGatewayCachePolicy.provider_slug == provider_slug,
            MCPGatewayCachePolicy.tool_name == tool_name,
        )
    )


def upsert_policy__no_commit(
    db_session: Session,
    *,
    provider_slug: str,
    tool_name: str,
    refresh_mode: MCPGatewayRefreshMode,
    ttl_seconds: int,
    swr_seconds: int,
    schedule_cron: str | None,
    key_fields: list[str] | None,
    normalize: dict[str, Any] | None,
    cache_empty_ttl_seconds: int,
    max_response_bytes: int,
) -> MCPGatewayCachePolicy:
    existing = get_policy(db_session, provider_slug, tool_name)
    if existing is None:
        existing = MCPGatewayCachePolicy(
            provider_slug=provider_slug,
            tool_name=tool_name,
        )
        db_session.add(existing)
    existing.refresh_mode = refresh_mode
    existing.ttl_seconds = ttl_seconds
    existing.swr_seconds = swr_seconds
    existing.schedule_cron = schedule_cron
    existing.key_fields = key_fields
    existing.normalize = normalize
    existing.cache_empty_ttl_seconds = cache_empty_ttl_seconds
    existing.max_response_bytes = max_response_bytes
    db_session.flush()
    return existing


def delete_policy(db_session: Session, policy: MCPGatewayCachePolicy) -> None:
    db_session.delete(policy)
    db_session.commit()


def get_cache_entry(
    db_session: Session, tenant_id: str, cache_key: str
) -> MCPGatewayCacheEntry | None:
    return db_session.scalar(
        select(MCPGatewayCacheEntry).where(
            MCPGatewayCacheEntry.tenant_id == tenant_id,
            MCPGatewayCacheEntry.cache_key == cache_key,
        )
    )


def upsert_cache_entry__no_commit(
    db_session: Session,
    *,
    tenant_id: str,
    cache_key: str,
    provider_slug: str,
    tool_name: str,
    effective_tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
    is_empty: bool,
    last_refresh_status: str,
) -> MCPGatewayCacheEntry:
    now = datetime.now(timezone.utc)
    existing = get_cache_entry(db_session, tenant_id, cache_key)
    if existing is None:
        existing = MCPGatewayCacheEntry(
            tenant_id=tenant_id,
            cache_key=cache_key,
            provider_slug=provider_slug,
            tool_name=tool_name,
            effective_tool_name=effective_tool_name,
            arguments=arguments,
            result=result,
            is_empty=is_empty,
            first_fetched_at=now,
            last_fetched_at=now,
            last_accessed_at=now,
            hit_count=0,
            last_refresh_status=last_refresh_status,
        )
        db_session.add(existing)
    else:
        existing.result = result
        existing.is_empty = is_empty
        existing.last_fetched_at = now
        existing.last_accessed_at = now
        existing.last_refresh_status = last_refresh_status
        existing.arguments = arguments
        existing.effective_tool_name = effective_tool_name
    db_session.flush()
    return existing


def mark_cache_entry_hit__no_commit(
    db_session: Session, entry: MCPGatewayCacheEntry
) -> None:
    entry.hit_count = (entry.hit_count or 0) + 1
    entry.last_accessed_at = datetime.now(timezone.utc)
    db_session.flush()


def delete_cache_entries(
    db_session: Session,
    *,
    tenant_id: str,
    cache_key: str | None = None,
    provider_slug: str | None = None,
    tool_name: str | None = None,
) -> int:
    stmt = delete(MCPGatewayCacheEntry).where(
        MCPGatewayCacheEntry.tenant_id == tenant_id
    )
    if cache_key:
        stmt = stmt.where(MCPGatewayCacheEntry.cache_key == cache_key)
    if provider_slug:
        stmt = stmt.where(MCPGatewayCacheEntry.provider_slug == provider_slug)
    if tool_name:
        stmt = stmt.where(
            (MCPGatewayCacheEntry.effective_tool_name == tool_name)
            | (MCPGatewayCacheEntry.tool_name == tool_name)
        )
    result = db_session.execute(stmt)
    db_session.commit()
    return result.rowcount or 0


def list_cache_entries(
    db_session: Session,
    *,
    tenant_id: str,
    provider_slug: str | None = None,
    limit: int = 50,
) -> list[MCPGatewayCacheEntry]:
    stmt = (
        select(MCPGatewayCacheEntry)
        .where(MCPGatewayCacheEntry.tenant_id == tenant_id)
        .order_by(desc(MCPGatewayCacheEntry.last_accessed_at))
        .limit(limit)
    )
    if provider_slug:
        stmt = stmt.where(MCPGatewayCacheEntry.provider_slug == provider_slug)
    return list(db_session.scalars(stmt).all())


def list_entries_for_scheduled_refresh(
    db_session: Session,
    *,
    tenant_id: str,
    provider_slug: str,
    tool_names: list[str],
    older_than: datetime,
    limit: int = 200,
) -> list[MCPGatewayCacheEntry]:
    return list(
        db_session.scalars(
            select(MCPGatewayCacheEntry)
            .where(
                MCPGatewayCacheEntry.tenant_id == tenant_id,
                MCPGatewayCacheEntry.provider_slug == provider_slug,
                MCPGatewayCacheEntry.effective_tool_name.in_(tool_names),
                MCPGatewayCacheEntry.last_fetched_at < older_than,
            )
            .order_by(desc(MCPGatewayCacheEntry.hit_count))
            .limit(limit)
        ).all()
    )


def insert_call_log__no_commit(
    db_session: Session,
    *,
    tenant_id: str,
    provider_slug: str,
    tool_name: str,
    effective_tool_name: str,
    cache_key: str,
    outcome: MCPGatewayCallOutcome,
    upstream_billed: bool,
    latency_ms: int,
    user_email: str | None,
    session_id: str | None,
    arguments: dict[str, Any],
    result: dict[str, Any] | None,
    error_message: str | None,
) -> MCPGatewayCallLog:
    row = MCPGatewayCallLog(
        tenant_id=tenant_id,
        provider_slug=provider_slug,
        tool_name=tool_name,
        effective_tool_name=effective_tool_name,
        cache_key=cache_key,
        outcome=outcome,
        upstream_billed=upstream_billed,
        latency_ms=latency_ms,
        user_email=user_email,
        session_id=session_id,
        arguments=arguments,
        result=result,
        error_message=error_message,
    )
    db_session.add(row)
    db_session.flush()
    return row


def call_stats(
    db_session: Session,
    *,
    tenant_id: str,
    provider_slug: str | None = None,
) -> dict[str, Any]:
    stmt = select(
        MCPGatewayCallLog.outcome,
        func.count(),
        func.sum(func.cast(MCPGatewayCallLog.upstream_billed, Integer)),
    ).where(MCPGatewayCallLog.tenant_id == tenant_id)
    if provider_slug:
        stmt = stmt.where(MCPGatewayCallLog.provider_slug == provider_slug)
    stmt = stmt.group_by(MCPGatewayCallLog.outcome)
    rows = db_session.execute(stmt).all()
    by_outcome: dict[str, int] = {}
    billed = 0
    total = 0
    for outcome, count, billed_sum in rows:
        key = (
            outcome.value
            if isinstance(outcome, MCPGatewayCallOutcome)
            else str(outcome)
        )
        by_outcome[key] = int(count)
        total += int(count)
        billed += int(billed_sum or 0)
    hits = by_outcome.get("hit", 0) + by_outcome.get("swr", 0)
    return {
        "total_calls": total,
        "upstream_billed": billed,
        "cache_hits": hits,
        "hit_rate": (hits / total) if total else 0.0,
        "saved_calls": max(total - billed, 0),
        "by_outcome": by_outcome,
    }


def set_mcp_server_gateway_fields__no_commit(
    db_session: Session,
    server: MCPServer,
    *,
    via_gateway: bool,
    gateway_provider_slug: str | None,
    server_url: str | None = None,
) -> None:
    server.via_gateway = via_gateway
    server.gateway_provider_slug = gateway_provider_slug
    if server_url is not None:
        server.server_url = server_url
    db_session.flush()


def increment_hit_count(db_session: Session, entry_id: int) -> None:
    db_session.execute(
        update(MCPGatewayCacheEntry)
        .where(MCPGatewayCacheEntry.id == entry_id)
        .values(
            hit_count=MCPGatewayCacheEntry.hit_count + 1,
            last_accessed_at=datetime.now(timezone.utc),
        )
    )
