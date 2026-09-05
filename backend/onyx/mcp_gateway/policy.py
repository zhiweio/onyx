from datetime import datetime, timedelta, timezone
from typing import Any

from croniter import croniter
from sqlalchemy.orm import Session

from onyx.db.enums import MCPGatewayRefreshMode
from onyx.db.mcp_gateway import get_policy, list_policies_for_provider
from onyx.db.models import MCPGatewayCacheEntry, MCPGatewayCachePolicy
from onyx.mcp_gateway.keys import expand_nested_tool
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs import get_pack, policy_for_tool


def spec_from_row(row: MCPGatewayCachePolicy) -> CachePolicySpec:
    return CachePolicySpec(
        refresh_mode=row.refresh_mode,
        ttl_seconds=row.ttl_seconds,
        swr_seconds=row.swr_seconds,
        schedule_cron=row.schedule_cron,
        key_fields=row.key_fields,
        normalize=row.normalize,
        cache_empty_ttl_seconds=row.cache_empty_ttl_seconds,
        max_response_bytes=row.max_response_bytes,
    )


def resolve_policy(
    db_session: Session,
    *,
    provider_slug: str,
    pack_slug: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[ProviderPack, str, CachePolicySpec]:
    pack = get_pack(pack_slug)
    effective, _ = expand_nested_tool(tool_name, arguments, pack)
    exact = get_policy(db_session, provider_slug, effective)
    if exact is not None:
        return pack, effective, spec_from_row(exact)
    wildcard = get_policy(db_session, provider_slug, "*")
    if wildcard is not None:
        return pack, effective, spec_from_row(wildcard)
    return pack, effective, policy_for_tool(pack, effective)


def merged_pack_and_db_policies(
    db_session: Session, provider_slug: str, pack_slug: str
) -> list[tuple[str, CachePolicySpec, bool]]:
    """Return (tool_name, spec, is_db_override) including pack defaults."""
    pack = get_pack(pack_slug)
    db_rows = {row.tool_name: row for row in list_policies_for_provider(db_session, provider_slug)}
    out: list[tuple[str, CachePolicySpec, bool]] = []
    if "*" in db_rows:
        out.append(("*", spec_from_row(db_rows["*"]), True))
    else:
        out.append(("*", pack.default_policy, False))
    seen = {"*"}
    for spec in pack.tool_policies:
        label = spec.tool_globs[0] if spec.tool_globs else "*"
        if label in seen:
            continue
        if label in db_rows:
            out.append((label, spec_from_row(db_rows[label]), True))
        else:
            out.append((label, spec, False))
        seen.add(label)
    for name, row in db_rows.items():
        if name not in seen:
            out.append((name, spec_from_row(row), True))
    return out


def _cron_due(schedule_cron: str, last_fetched: datetime, now: datetime) -> bool:
    iterator = croniter(schedule_cron, last_fetched)
    nxt = iterator.get_next(datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=timezone.utc)
    return nxt <= now


def freshness(
    entry: MCPGatewayCacheEntry,
    policy: CachePolicySpec,
    now: datetime | None = None,
) -> str:
    """Return fresh | stale | expired."""
    if policy.refresh_mode == MCPGatewayRefreshMode.BYPASS:
        return "expired"
    if policy.refresh_mode == MCPGatewayRefreshMode.NEVER:
        return "fresh"
    clock = now or datetime.now(timezone.utc)
    last = entry.last_fetched_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = clock - last
    ttl = timedelta(seconds=policy.cache_empty_ttl_seconds if entry.is_empty else policy.ttl_seconds)
    swr = timedelta(seconds=policy.swr_seconds)
    cron_due = False
    if policy.schedule_cron and policy.refresh_mode in (
        MCPGatewayRefreshMode.SCHEDULE,
        MCPGatewayRefreshMode.TTL_AND_SCHEDULE,
    ):
        cron_due = _cron_due(policy.schedule_cron, last, clock)

    if policy.refresh_mode == MCPGatewayRefreshMode.SCHEDULE:
        return "expired" if cron_due else "fresh"

    if age <= ttl and not cron_due:
        return "fresh"
    if policy.refresh_mode in (
        MCPGatewayRefreshMode.SWR,
        MCPGatewayRefreshMode.TTL_AND_SCHEDULE,
    ) and age <= ttl + swr:
        return "stale"
    return "expired"
