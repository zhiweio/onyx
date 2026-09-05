"""Cache engine for system MCP calls.

One call goes through at most four steps: a Redis lookup of the digest and
handle, a Postgres lookup of the cache entry, a lock-guarded upstream call, and
a write to whichever storage tier fits the size of the answer.

Two invariants shape the code:

- **Redis only ever holds small values.** It stores the handle and digest, not
  the body, so a 10 MB answer costs the same in the hot path as a 1 KB one.
- **No DB session is held across an upstream call.** Those take up to five
  minutes; the entry is snapshotted into an `UpstreamTarget` and the session is
  released before the request goes out.
"""

import asyncio
import json
from time import perf_counter
from typing import Any

from onyx.cache.factory import get_cache_backend
from onyx.cache.interface import CACHE_TRANSIENT_ERRORS, CacheLock
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import MCPGatewayCallOutcome, MCPGatewayRefreshMode
from onyx.db.mcp_catalog import get_catalog_entry_by_slug
from onyx.db.mcp_gateway import (
    get_cache_entry,
    insert_call_log__no_commit,
    mark_cache_entry_hit__no_commit,
    upsert_cache_entry__no_commit,
)
from onyx.mcp_gateway.keys import (
    batch_items,
    build_cache_key,
    canonicalize_arguments,
    expand_nested_tool,
)
from onyx.mcp_gateway.models import CachePolicySpec, ResolvedCall, StoredResult
from onyx.mcp_gateway.policy import freshness, resolve_policy
from onyx.mcp_gateway.storage import load_result, store_result
from onyx.mcp_gateway.upstream import (
    UpstreamTarget,
    call_upstream,
    is_empty_result,
    is_error_result,
)
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import get_current_tenant_id

logger = setup_logger()

REDIS_PREFIX = "mcp_gateway:handle:"
LOCK_PREFIX = "mcp_gateway:lock:"

# How long to wait for whoever is already fetching this key. Past this we serve
# stale data or go upstream ourselves rather than failing the call.
_LOCK_WAIT_SECONDS = 60.0
_LOCK_LEASE_SECONDS = 600.0


def _redis_key(cache_key: str) -> str:
    return f"{REDIS_PREFIX}{cache_key}"


# ---------------------------------------------------------------------------
# Hot tier: handle + digest only, never the body
# ---------------------------------------------------------------------------


def _read_handle(tenant_id: str, cache_key: str) -> str | None:
    try:
        raw = get_cache_backend(tenant_id=tenant_id).get(_redis_key(cache_key))
    except CACHE_TRANSIENT_ERRORS:
        logger.debug("MCP gateway cache read failed", exc_info=True)
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    blob_id = parsed.get("blob_id") if isinstance(parsed, dict) else None
    return blob_id if isinstance(blob_id, str) else None


def _write_handle(
    tenant_id: str, cache_key: str, stored: StoredResult, ttl_seconds: int
) -> None:
    if ttl_seconds <= 0:
        return
    try:
        get_cache_backend(tenant_id=tenant_id).set(
            _redis_key(cache_key),
            json.dumps(
                {"blob_id": stored.blob_id, "size_bytes": stored.size_bytes},
                ensure_ascii=False,
            ),
            ex=ttl_seconds,
        )
    except CACHE_TRANSIENT_ERRORS:
        logger.debug("MCP gateway cache write failed", exc_info=True)


def invalidate_cache_keys(tenant_id: str, cache_keys: list[str]) -> None:
    backend = get_cache_backend(tenant_id=tenant_id)
    for key in cache_keys:
        try:
            backend.delete(_redis_key(key))
        except CACHE_TRANSIENT_ERRORS:
            logger.debug("MCP gateway cache delete failed", exc_info=True)


def enqueue_refresh(tenant_id: str, cache_key: str) -> None:
    try:
        from onyx.background.celery.tasks.mcp_gateway.tasks import (
            refresh_mcp_gateway_cache_entry,
        )
        from onyx.configs.constants import OnyxCeleryPriority

        refresh_mcp_gateway_cache_entry.apply_async(
            kwargs={"tenant_id": tenant_id, "cache_key": cache_key},
            expires=600,
            priority=OnyxCeleryPriority.MEDIUM,
        )
    except Exception:
        logger.debug("MCP gateway refresh enqueue failed", exc_info=True)


# ---------------------------------------------------------------------------
# Upstream, guarded by a lock so a cold key is fetched once
# ---------------------------------------------------------------------------


async def _acquire_lock_async(lock: CacheLock, timeout_s: float) -> bool:
    """Poll without blocking the event loop, so the holder can make progress."""
    deadline = perf_counter() + timeout_s
    while perf_counter() < deadline:
        if lock.acquire(blocking=False):
            return True
        await asyncio.sleep(0.05)
    return False


async def _fetch_and_store(
    *,
    tenant_id: str,
    catalog_slug: str,
    tool_name: str,
    effective_tool_name: str,
    arguments: dict[str, Any],
    cache_key: str,
    policy: CachePolicySpec,
) -> tuple[dict[str, Any], StoredResult | None]:
    """Fetch upstream and persist, letting one caller do the work per key.

    A caller that cannot get the lock does not fail: it re-checks the cache,
    serves whatever is there even if stale, and only calls upstream itself when
    there is nothing to serve. Failing the request would turn a slow upstream
    into an outage.
    """
    backend = get_cache_backend(tenant_id=tenant_id)
    lock = backend.lock(f"{LOCK_PREFIX}{cache_key}", timeout=_LOCK_LEASE_SECONDS)
    acquired = await _acquire_lock_async(lock, _LOCK_WAIT_SECONDS)

    try:
        # The holder may have finished while we waited.
        with get_session_with_current_tenant() as db_session:
            entry = get_cache_entry(db_session, cache_key)
            if entry is not None and (
                not acquired or freshness(entry, policy) == "fresh"
            ):
                stored = load_result(db_session, entry.blob_id)
                mark_cache_entry_hit__no_commit(db_session, entry)
                db_session.commit()
                if stored is not None and stored.payload is not None:
                    _write_handle(
                        tenant_id,
                        cache_key,
                        stored,
                        policy.ttl_seconds + policy.swr_seconds,
                    )
                    return stored.payload, stored

            catalog_entry = get_catalog_entry_by_slug(db_session, catalog_slug)
            if catalog_entry is None or not catalog_entry.enabled:
                raise ValueError(f"System MCP '{catalog_slug}' is not available")
            target = UpstreamTarget.from_entry(catalog_entry)

        # Session released: the call below can take minutes.
        payload = await call_upstream(target, tool_name, arguments)

        stored = _persist(
            cache_key=cache_key,
            catalog_slug=catalog_slug,
            tool_name=tool_name,
            effective_tool_name=effective_tool_name,
            arguments=arguments,
            payload=payload,
            policy=policy,
            tenant_id=tenant_id,
        )
        return payload, stored
    finally:
        if acquired:
            try:
                lock.release()
            except Exception:
                logger.debug("MCP gateway lock release failed", exc_info=True)


def _should_persist(payload: dict[str, Any], policy: CachePolicySpec) -> bool:
    if policy.refresh_mode == MCPGatewayRefreshMode.BYPASS:
        return False
    # An error is a property of this attempt, not of the arguments; caching it
    # would keep returning the failure after the upstream recovered.
    return not is_error_result(payload)


def _persist(
    *,
    cache_key: str,
    catalog_slug: str,
    tool_name: str,
    effective_tool_name: str,
    arguments: dict[str, Any],
    payload: dict[str, Any],
    policy: CachePolicySpec,
    tenant_id: str,
) -> StoredResult | None:
    """Write the body to its storage tier and point the cache entry at it."""
    if not _should_persist(payload, policy):
        return None

    empty = is_empty_result(payload)
    with get_session_with_current_tenant() as db_session:
        stored = store_result(
            db_session,
            payload,
            policy,
            catalog_slug=catalog_slug,
            tool_name=effective_tool_name,
        )
        if stored is None:
            db_session.rollback()
            return None
        upsert_cache_entry__no_commit(
            db_session,
            cache_key=cache_key,
            catalog_slug=catalog_slug,
            tool_name=tool_name,
            effective_tool_name=effective_tool_name,
            arguments=arguments,
            blob_id=stored.blob_id,
            is_empty=empty,
            last_refresh_status="ok",
        )
        db_session.commit()

    ttl = (
        policy.cache_empty_ttl_seconds
        if empty
        else policy.ttl_seconds + policy.swr_seconds
    )
    _write_handle(tenant_id, cache_key, stored, max(ttl, 1))
    return stored


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def invoke_tool(
    *,
    catalog_slug: str,
    tool_name: str,
    arguments: dict[str, Any],
    user_email: str | None = None,
    session_id: str | None = None,
) -> ResolvedCall:
    started = perf_counter()
    tenant_id = get_current_tenant_id()

    with get_session_with_current_tenant() as db_session:
        entry = get_catalog_entry_by_slug(db_session, catalog_slug)
        if entry is None or not entry.enabled:
            raise ValueError(f"System MCP '{catalog_slug}' is not available")
        pack, effective, policy = resolve_policy(
            pack_slug=entry.pack_slug,
            policy_overrides=entry.policy_overrides,
            tool_name=tool_name,
            arguments=arguments,
        )
        is_batch = tool_name in pack.batch_entry_tools

    if is_batch:
        return await _invoke_batch(
            catalog_slug=catalog_slug,
            tool_name=tool_name,
            arguments=arguments,
            user_email=user_email,
            session_id=session_id,
        )

    _effective, key_args = expand_nested_tool(tool_name, arguments, pack)
    cache_key = build_cache_key(
        tenant_id=tenant_id,
        provider_slug=catalog_slug,
        tool_name=tool_name,
        effective_tool_name=effective,
        canonical_args=canonicalize_arguments(key_args, policy),
    )

    if policy.refresh_mode == MCPGatewayRefreshMode.BYPASS:
        with get_session_with_current_tenant() as db_session:
            bypass_entry = get_catalog_entry_by_slug(db_session, catalog_slug)
            if bypass_entry is None:
                raise ValueError(f"System MCP '{catalog_slug}' is not available")
            target = UpstreamTarget.from_entry(bypass_entry)
        payload = await call_upstream(target, tool_name, arguments)
        return _logged(
            tenant_id=tenant_id,
            catalog_slug=catalog_slug,
            tool_name=tool_name,
            effective_tool_name=effective,
            arguments=arguments,
            cache_key=cache_key,
            policy=policy,
            outcome=MCPGatewayCallOutcome.BYPASS,
            result=payload,
            stored=None,
            upstream_billed=True,
            user_email=user_email,
            session_id=session_id,
            started=started,
        )

    cached, outcome = _read_cached(tenant_id, cache_key, policy)
    if cached is not None and cached.payload is not None:
        if outcome == MCPGatewayCallOutcome.SWR:
            enqueue_refresh(tenant_id, cache_key)
        return _logged(
            tenant_id=tenant_id,
            catalog_slug=catalog_slug,
            tool_name=tool_name,
            effective_tool_name=effective,
            arguments=arguments,
            cache_key=cache_key,
            policy=policy,
            outcome=outcome,
            result=cached.payload,
            stored=cached,
            upstream_billed=False,
            user_email=user_email,
            session_id=session_id,
            started=started,
        )

    payload, stored = await _fetch_and_store(
        tenant_id=tenant_id,
        catalog_slug=catalog_slug,
        tool_name=tool_name,
        effective_tool_name=effective,
        arguments=arguments,
        cache_key=cache_key,
        policy=policy,
    )
    return _logged(
        tenant_id=tenant_id,
        catalog_slug=catalog_slug,
        tool_name=tool_name,
        effective_tool_name=effective,
        arguments=arguments,
        cache_key=cache_key,
        policy=policy,
        outcome=MCPGatewayCallOutcome.MISS,
        result=payload,
        stored=stored,
        upstream_billed=True,
        user_email=user_email,
        session_id=session_id,
        started=started,
    )


def _read_cached(
    tenant_id: str, cache_key: str, policy: CachePolicySpec
) -> tuple[StoredResult | None, MCPGatewayCallOutcome]:
    """Look for a usable cached result, hot tier first."""
    with get_session_with_current_tenant() as db_session:
        entry = get_cache_entry(db_session, cache_key)
        if entry is None:
            return None, MCPGatewayCallOutcome.MISS

        state = freshness(entry, policy)
        if state == "expired":
            return None, MCPGatewayCallOutcome.MISS

        stored = load_result(db_session, entry.blob_id)
        if stored is None or stored.payload is None:
            # The body vanished (collected, or the object store lost it).
            # Treat as a miss so the caller refetches.
            return None, MCPGatewayCallOutcome.MISS

        mark_cache_entry_hit__no_commit(db_session, entry)
        db_session.commit()

    # Refresh the hot tier if this hit came from Postgres.
    if _read_handle(tenant_id, cache_key) is None:
        _write_handle(
            tenant_id, cache_key, stored, policy.ttl_seconds + policy.swr_seconds
        )

    outcome = (
        MCPGatewayCallOutcome.HIT if state == "fresh" else MCPGatewayCallOutcome.SWR
    )
    return stored, outcome


async def refresh_entry(tenant_id: str, cache_key: str) -> None:
    """Background refresh of one cache entry."""
    with get_session_with_current_tenant() as db_session:
        entry = get_cache_entry(db_session, cache_key)
        if entry is None:
            return
        catalog_entry = get_catalog_entry_by_slug(db_session, entry.catalog_slug)
        if catalog_entry is None or not catalog_entry.enabled:
            return
        _pack, _effective, policy = resolve_policy(
            pack_slug=catalog_entry.pack_slug,
            policy_overrides=catalog_entry.policy_overrides,
            tool_name=entry.tool_name,
            arguments=entry.arguments,
        )
        target = UpstreamTarget.from_entry(catalog_entry)
        snapshot = (
            entry.catalog_slug,
            entry.tool_name,
            entry.effective_tool_name,
            dict(entry.arguments),
        )

    catalog_slug, tool_name, effective_tool_name, arguments = snapshot
    payload = await call_upstream(target, tool_name, arguments)
    _persist(
        cache_key=cache_key,
        catalog_slug=catalog_slug,
        tool_name=tool_name,
        effective_tool_name=effective_tool_name,
        arguments=arguments,
        payload=payload,
        policy=policy,
        tenant_id=tenant_id,
    )


async def _invoke_batch(
    *,
    catalog_slug: str,
    tool_name: str,
    arguments: dict[str, Any],
    user_email: str | None,
    session_id: str | None,
) -> ResolvedCall:
    """Split a batch entry tool into per-item calls so each item caches alone.

    Batching is an upstream transport detail; caching the batch as a unit would
    miss whenever the set of items differed by one.
    """
    started = perf_counter()
    tenant_id = get_current_tenant_id()

    assembled: list[dict[str, Any]] = []
    billed = False
    for item in batch_items(arguments):
        inner_name = str(item.get("name") or item.get("tool") or "")
        inner_args = item.get("arguments") or item.get("args") or {}
        if not inner_name or not isinstance(inner_args, dict):
            assembled.append({"isError": True, "content": []})
            continue
        resolved = await invoke_tool(
            catalog_slug=catalog_slug,
            tool_name="call_tool",
            arguments={"name": inner_name, "arguments": inner_args},
            user_email=user_email,
            session_id=session_id,
        )
        assembled.append(resolved.result)
        billed = billed or resolved.upstream_billed

    result = {
        "content": [],
        "structuredContent": {"results": assembled},
        "isError": False,
    }
    return _logged(
        tenant_id=tenant_id,
        catalog_slug=catalog_slug,
        tool_name=tool_name,
        effective_tool_name=tool_name,
        arguments=arguments,
        cache_key="batch",
        policy=CachePolicySpec(),
        outcome=(MCPGatewayCallOutcome.MISS if billed else MCPGatewayCallOutcome.HIT),
        result=result,
        stored=None,
        upstream_billed=billed,
        user_email=user_email,
        session_id=session_id,
        started=started,
    )


def _logged(
    *,
    tenant_id: str,  # noqa: ARG001 — kept for call-site symmetry with cache ops
    catalog_slug: str,
    tool_name: str,
    effective_tool_name: str,
    arguments: dict[str, Any],
    cache_key: str,
    policy: CachePolicySpec,
    outcome: MCPGatewayCallOutcome,
    result: dict[str, Any],
    stored: StoredResult | None,
    upstream_billed: bool,
    user_email: str | None,
    session_id: str | None,
    started: float,
    error_message: str | None = None,
) -> ResolvedCall:
    latency_ms = int((perf_counter() - started) * 1000)
    try:
        with get_session_with_current_tenant() as db_session:
            insert_call_log__no_commit(
                db_session,
                catalog_slug=catalog_slug,
                tool_name=tool_name,
                effective_tool_name=effective_tool_name,
                cache_key=cache_key,
                outcome=outcome,
                upstream_billed=upstream_billed,
                latency_ms=latency_ms,
                response_bytes=stored.size_bytes if stored else 0,
                user_email=user_email,
                session_id=session_id,
                arguments=arguments,
                result_blob_id=stored.blob_id if stored else None,
                error_message=error_message,
            )
            db_session.commit()
    except Exception:
        logger.exception("Failed to write MCP gateway call log")

    return ResolvedCall(
        tool_name=tool_name,
        effective_tool_name=effective_tool_name,
        arguments=arguments,
        cache_key=cache_key,
        policy=policy,
        outcome=outcome,
        result=result,
        upstream_billed=upstream_billed,
        latency_ms=latency_ms,
        stored=stored,
        error_message=error_message,
    )
