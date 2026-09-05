import asyncio
import json
from time import perf_counter
from typing import Any

from onyx.cache.factory import get_cache_backend
from onyx.cache.interface import CACHE_TRANSIENT_ERRORS, CacheLock
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import MCPGatewayCallOutcome, MCPGatewayRefreshMode
from onyx.db.mcp_gateway import (
    get_cache_entry,
    get_provider_by_slug,
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
from onyx.mcp_gateway.models import CachePolicySpec, ResolvedCall
from onyx.mcp_gateway.policy import freshness, resolve_policy
from onyx.mcp_gateway.upstream import call_upstream, is_empty_result, is_error_result
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import get_current_tenant_id

logger = setup_logger()

REDIS_PREFIX = "mcp_gateway:result:"
LOCK_PREFIX = "mcp_gateway:lock:"


def _redis_key(cache_key: str) -> str:
    return f"{REDIS_PREFIX}{cache_key}"


def _result_size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _read_redis(tenant_id: str, cache_key: str) -> dict[str, Any] | None:
    try:
        raw = get_cache_backend(tenant_id=tenant_id).get(_redis_key(cache_key))
    except CACHE_TRANSIENT_ERRORS:
        logger.debug("MCP gateway Redis read failed", exc_info=True)
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _write_redis(
    tenant_id: str, cache_key: str, payload: dict[str, Any], ttl_seconds: int
) -> None:
    if ttl_seconds <= 0:
        return
    try:
        get_cache_backend(tenant_id=tenant_id).set(
            _redis_key(cache_key),
            json.dumps(payload, ensure_ascii=False),
            ex=ttl_seconds,
        )
    except CACHE_TRANSIENT_ERRORS:
        logger.debug("MCP gateway Redis write failed", exc_info=True)


def _delete_redis(tenant_id: str, cache_key: str) -> None:
    try:
        get_cache_backend(tenant_id=tenant_id).delete(_redis_key(cache_key))
    except CACHE_TRANSIENT_ERRORS:
        logger.debug("MCP gateway Redis delete failed", exc_info=True)


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


def _should_store(payload: dict[str, Any], policy: CachePolicySpec) -> bool:
    if policy.refresh_mode == MCPGatewayRefreshMode.BYPASS:
        return False
    if is_error_result(payload):
        return False
    if _result_size(payload) > policy.max_response_bytes:
        return False
    return True


def _store(
    *,
    tenant_id: str,
    cache_key: str,
    provider_slug: str,
    tool_name: str,
    effective_tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
    policy: CachePolicySpec,
) -> None:
    empty = is_empty_result(result)
    ttl = policy.cache_empty_ttl_seconds if empty else policy.ttl_seconds + policy.swr_seconds
    with get_session_with_current_tenant() as db_session:
        upsert_cache_entry__no_commit(
            db_session,
            tenant_id=tenant_id,
            cache_key=cache_key,
            provider_slug=provider_slug,
            tool_name=tool_name,
            effective_tool_name=effective_tool_name,
            arguments=arguments,
            result=result,
            is_empty=empty,
            last_refresh_status="ok",
        )
        db_session.commit()
    if _should_store(result, policy):
        _write_redis(tenant_id, cache_key, result, max(ttl, 1))


async def _acquire_lock_async(lock: CacheLock, timeout_s: float = 60) -> bool:
    """Poll Redis without blocking the event loop so a holder can finish."""
    deadline = perf_counter() + timeout_s
    while perf_counter() < deadline:
        if lock.acquire(blocking=False):
            return True
        await asyncio.sleep(0.05)
    return False


async def _upstream_locked(
    *,
    tenant_id: str,
    provider_slug: str,
    tool_name: str,
    arguments: dict[str, Any],
    cache_key: str,
    effective_tool_name: str,
    policy: CachePolicySpec,
) -> dict[str, Any]:
    backend = get_cache_backend(tenant_id=tenant_id)
    lock = backend.lock(f"{LOCK_PREFIX}{cache_key}", timeout=120)
    acquired = await _acquire_lock_async(lock)
    try:
        cached = _read_redis(tenant_id, cache_key)
        if cached is not None:
            return cached
        with get_session_with_current_tenant() as db_session:
            provider = get_provider_by_slug(db_session, provider_slug)
            if provider is None or not provider.enabled:
                raise ValueError(f"Gateway provider '{provider_slug}' is not available")
            entry = get_cache_entry(db_session, tenant_id, cache_key)
            if entry is not None and (
                freshness(entry, policy) == "fresh" or not acquired
            ):
                mark_cache_entry_hit__no_commit(db_session, entry)
                db_session.commit()
                _write_redis(
                    tenant_id,
                    cache_key,
                    entry.result,
                    policy.ttl_seconds + policy.swr_seconds,
                )
                return entry.result
            if not acquired:
                raise ValueError("Could not acquire MCP gateway cache lock")
            result = await call_upstream(provider, tool_name, arguments)
        if _should_store(result, policy):
            _store(
                tenant_id=tenant_id,
                cache_key=cache_key,
                provider_slug=provider_slug,
                tool_name=tool_name,
                effective_tool_name=effective_tool_name,
                arguments=arguments,
                result=result,
                policy=policy,
            )
        return result
    finally:
        if acquired:
            lock.release()


async def invoke_tool(
    *,
    provider_slug: str,
    tool_name: str,
    arguments: dict[str, Any],
    user_email: str | None = None,
    session_id: str | None = None,
) -> ResolvedCall:
    started = perf_counter()
    tenant_id = get_current_tenant_id()
    with get_session_with_current_tenant() as db_session:
        provider = get_provider_by_slug(db_session, provider_slug)
        if provider is None or not provider.enabled:
            raise ValueError(f"Gateway provider '{provider_slug}' is not available")
        pack_slug = provider.pack_slug
        pack, effective, policy = resolve_policy(
            db_session,
            provider_slug=provider_slug,
            pack_slug=pack_slug,
            tool_name=tool_name,
            arguments=arguments,
        )
        if tool_name in pack.batch_entry_tools:
            return await _invoke_batch(
                provider_slug=provider_slug,
                tool_name=tool_name,
                arguments=arguments,
                user_email=user_email,
                session_id=session_id,
            )
        _effective, key_args = expand_nested_tool(tool_name, arguments, pack)
        canonical = canonicalize_arguments(key_args, policy)
        cache_key = build_cache_key(
            tenant_id=tenant_id,
            provider_slug=provider_slug,
            tool_name=tool_name,
            effective_tool_name=effective,
            canonical_args=canonical,
        )

    if policy.refresh_mode == MCPGatewayRefreshMode.BYPASS:
        result = await _call_and_log(
            tenant_id=tenant_id,
            provider_slug=provider_slug,
            tool_name=tool_name,
            effective_tool_name=effective,
            arguments=arguments,
            cache_key=cache_key,
            policy=policy,
            outcome=MCPGatewayCallOutcome.BYPASS,
            user_email=user_email,
            session_id=session_id,
            started=started,
        )
        return result

    redis_hit = _read_redis(tenant_id, cache_key)
    with get_session_with_current_tenant() as db_session:
        entry = get_cache_entry(db_session, tenant_id, cache_key)
        state = freshness(entry, policy) if entry is not None else "expired"
        cached_payload = redis_hit if redis_hit is not None else (
            entry.result if entry is not None else None
        )
        if entry is not None and state == "fresh" and cached_payload is not None:
            mark_cache_entry_hit__no_commit(db_session, entry)
            db_session.commit()
            if redis_hit is None:
                _write_redis(
                    tenant_id,
                    cache_key,
                    cached_payload,
                    policy.ttl_seconds + policy.swr_seconds,
                )
            return _logged(
                tenant_id=tenant_id,
                provider_slug=provider_slug,
                tool_name=tool_name,
                effective_tool_name=effective,
                arguments=arguments,
                cache_key=cache_key,
                policy=policy,
                outcome=MCPGatewayCallOutcome.HIT,
                result=cached_payload,
                upstream_billed=False,
                user_email=user_email,
                session_id=session_id,
                started=started,
            )
        if entry is not None and state == "stale" and cached_payload is not None:
            mark_cache_entry_hit__no_commit(db_session, entry)
            db_session.commit()
            enqueue_refresh(tenant_id, cache_key)
            return _logged(
                tenant_id=tenant_id,
                provider_slug=provider_slug,
                tool_name=tool_name,
                effective_tool_name=effective,
                arguments=arguments,
                cache_key=cache_key,
                policy=policy,
                outcome=MCPGatewayCallOutcome.SWR,
                result=cached_payload,
                upstream_billed=False,
                user_email=user_email,
                session_id=session_id,
                started=started,
            )

    payload = await _upstream_locked(
        tenant_id=tenant_id,
        provider_slug=provider_slug,
        tool_name=tool_name,
        arguments=arguments,
        cache_key=cache_key,
        effective_tool_name=effective,
        policy=policy,
    )
    return _logged(
        tenant_id=tenant_id,
        provider_slug=provider_slug,
        tool_name=tool_name,
        effective_tool_name=effective,
        arguments=arguments,
        cache_key=cache_key,
        policy=policy,
        outcome=MCPGatewayCallOutcome.MISS,
        result=payload,
        upstream_billed=True,
        user_email=user_email,
        session_id=session_id,
        started=started,
    )


async def refresh_entry(tenant_id: str, cache_key: str) -> None:
    with get_session_with_current_tenant() as db_session:
        entry = get_cache_entry(db_session, tenant_id, cache_key)
        if entry is None:
            return
        provider = get_provider_by_slug(db_session, entry.provider_slug)
        if provider is None or not provider.enabled:
            return
        _pack, _effective, policy = resolve_policy(
            db_session,
            provider_slug=entry.provider_slug,
            pack_slug=provider.pack_slug,
            tool_name=entry.tool_name,
            arguments=entry.arguments,
        )
    payload = await _upstream_locked(
        tenant_id=tenant_id,
        provider_slug=entry.provider_slug,
        tool_name=entry.tool_name,
        arguments=entry.arguments,
        cache_key=cache_key,
        effective_tool_name=entry.effective_tool_name,
        policy=policy,
    )
    _store(
        tenant_id=tenant_id,
        cache_key=cache_key,
        provider_slug=entry.provider_slug,
        tool_name=entry.tool_name,
        effective_tool_name=entry.effective_tool_name,
        arguments=entry.arguments,
        result=payload,
        policy=policy,
    )


async def _invoke_batch(
    *,
    provider_slug: str,
    tool_name: str,
    arguments: dict[str, Any],
    user_email: str | None,
    session_id: str | None,
) -> ResolvedCall:
    started = perf_counter()
    tenant_id = get_current_tenant_id()
    items = batch_items(arguments)
    assembled: list[dict[str, Any]] = []
    billed = False
    for item in items:
        inner_name = str(item.get("name") or item.get("tool") or "")
        inner_args = item.get("arguments") or item.get("args") or {}
        if not inner_name or not isinstance(inner_args, dict):
            assembled.append({"isError": True, "content": []})
            continue
        resolved = await invoke_tool(
            provider_slug=provider_slug,
            tool_name="call_tool",
            arguments={"name": inner_name, "arguments": inner_args},
            user_email=user_email,
            session_id=session_id,
        )
        assembled.append(resolved.result)
        billed = billed or resolved.upstream_billed
    result = {"content": [], "structuredContent": {"results": assembled}, "isError": False}
    return _logged(
        tenant_id=tenant_id,
        provider_slug=provider_slug,
        tool_name=tool_name,
        effective_tool_name=tool_name,
        arguments=arguments,
        cache_key="batch",
        policy=CachePolicySpec(),
        outcome=MCPGatewayCallOutcome.MISS if billed else MCPGatewayCallOutcome.HIT,
        result=result,
        upstream_billed=billed,
        user_email=user_email,
        session_id=session_id,
        started=started,
    )


async def _call_and_log(
    *,
    tenant_id: str,
    provider_slug: str,
    tool_name: str,
    effective_tool_name: str,
    arguments: dict[str, Any],
    cache_key: str,
    policy: CachePolicySpec,
    outcome: MCPGatewayCallOutcome,
    user_email: str | None,
    session_id: str | None,
    started: float,
) -> ResolvedCall:
    with get_session_with_current_tenant() as db_session:
        provider = get_provider_by_slug(db_session, provider_slug)
        if provider is None:
            raise ValueError(f"Gateway provider '{provider_slug}' is not available")
        payload = await call_upstream(provider, tool_name, arguments)
    return _logged(
        tenant_id=tenant_id,
        provider_slug=provider_slug,
        tool_name=tool_name,
        effective_tool_name=effective_tool_name,
        arguments=arguments,
        cache_key=cache_key,
        policy=policy,
        outcome=outcome,
        result=payload,
        upstream_billed=True,
        user_email=user_email,
        session_id=session_id,
        started=started,
    )


def _logged(
    *,
    tenant_id: str,
    provider_slug: str,
    tool_name: str,
    effective_tool_name: str,
    arguments: dict[str, Any],
    cache_key: str,
    policy: CachePolicySpec,
    outcome: MCPGatewayCallOutcome,
    result: dict[str, Any],
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
        error_message=error_message,
    )


def invalidate_redis_keys(tenant_id: str, cache_keys: list[str]) -> None:
    for key in cache_keys:
        _delete_redis(tenant_id, key)
