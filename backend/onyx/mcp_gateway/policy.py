"""Resolving the cache policy for one tool call.

Two layers, most specific wins:

1. The catalog entry's `policy_overrides`, keyed by exact tool name, by glob,
   or by ``"*"`` for the entry default.
2. The provider pack's per-tool policy, else the pack default.

Overrides are overlaid on the pack policy rather than replacing it, so an admin
who only wants to change a TTL does not have to restate everything else.
"""

import datetime
from datetime import timedelta, timezone
from fnmatch import fnmatch
from typing import Any, Protocol

from croniter import croniter

from onyx.db.enums import MCPGatewayRefreshMode
from onyx.mcp_gateway.keys import expand_nested_tool
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack, policy_from_mapping
from onyx.mcp_gateway.registry import get_pack, policy_for_tool

DEFAULT_POLICY_KEY = "*"


def _override_for_tool(
    overrides: dict[str, Any] | None, effective_tool_name: str
) -> dict[str, Any] | None:
    """Exact key first, then the first matching glob, then the entry default."""
    if not overrides:
        return None

    exact = overrides.get(effective_tool_name)
    if isinstance(exact, dict):
        return exact

    lowered = effective_tool_name.lower()
    for key, value in overrides.items():
        if key == DEFAULT_POLICY_KEY or not isinstance(value, dict):
            continue
        if fnmatch(effective_tool_name, key) or fnmatch(lowered, key.lower()):
            return value

    fallback = overrides.get(DEFAULT_POLICY_KEY)
    return fallback if isinstance(fallback, dict) else None


def resolve_policy(
    *,
    pack_slug: str,
    policy_overrides: dict[str, Any] | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[ProviderPack, str, CachePolicySpec]:
    """Return the pack, the unwrapped tool name, and the policy to apply."""
    pack = get_pack(pack_slug)
    effective, _ = expand_nested_tool(tool_name, arguments, pack)
    base = policy_for_tool(pack, effective)
    override = _override_for_tool(policy_overrides, effective)
    if override is not None:
        return pack, effective, policy_from_mapping(override, base)
    return pack, effective, base


def effective_policies(
    pack_slug: str, policy_overrides: dict[str, Any] | None
) -> list[tuple[str, CachePolicySpec, bool]]:
    """Every policy that applies to an entry, for the admin UI.

    Returns (label, spec, is_override). The label is either a tool name, a
    glob, or ``"*"`` for the default.
    """
    pack = get_pack(pack_slug)
    overrides = policy_overrides or {}
    rows: list[tuple[str, CachePolicySpec, bool]] = []

    default_override = overrides.get(DEFAULT_POLICY_KEY)
    if isinstance(default_override, dict):
        rows.append(
            (
                DEFAULT_POLICY_KEY,
                policy_from_mapping(default_override, pack.default_policy),
                True,
            )
        )
    else:
        rows.append((DEFAULT_POLICY_KEY, pack.default_policy, False))

    seen = {DEFAULT_POLICY_KEY}
    for spec in pack.tool_policies:
        label = spec.tool_globs[0] if spec.tool_globs else DEFAULT_POLICY_KEY
        if label in seen:
            continue
        seen.add(label)
        override = overrides.get(label)
        if isinstance(override, dict):
            rows.append((label, policy_from_mapping(override, spec), True))
        else:
            rows.append((label, spec, False))

    for label, override in overrides.items():
        if label in seen or not isinstance(override, dict):
            continue
        seen.add(label)
        rows.append((label, policy_from_mapping(override, pack.default_policy), True))

    return rows


def _cron_due(
    schedule_cron: str, last_fetched: datetime.datetime, now: datetime.datetime
) -> bool:
    iterator = croniter(schedule_cron, last_fetched)
    nxt = iterator.get_next(datetime.datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=timezone.utc)
    return nxt <= now


class AgedEntry(Protocol):
    """The only two things freshness depends on.

    Narrower than the ORM row so the rule can be reasoned about — and tested —
    without a database.
    """

    last_fetched_at: datetime.datetime
    is_empty: bool


def freshness(
    entry: AgedEntry,
    policy: CachePolicySpec,
    now: datetime.datetime | None = None,
) -> str:
    """Return fresh | stale | expired."""
    if policy.refresh_mode == MCPGatewayRefreshMode.BYPASS:
        return "expired"
    if policy.refresh_mode == MCPGatewayRefreshMode.NEVER:
        return "fresh"

    clock = now or datetime.datetime.now(timezone.utc)
    last = entry.last_fetched_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = clock - last
    ttl = timedelta(
        seconds=(
            policy.cache_empty_ttl_seconds if entry.is_empty else policy.ttl_seconds
        )
    )
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
    if (
        policy.refresh_mode
        in (MCPGatewayRefreshMode.SWR, MCPGatewayRefreshMode.TTL_AND_SCHEDULE)
        and age <= ttl + swr
    ):
        return "stale"
    return "expired"
