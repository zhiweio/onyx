"""Gateway cache entries, call log, and result blobs.

Cache rows live inside the tenant schema, so none of them carry a tenant
column — the schema is the boundary. Result bodies are not stored here either:
a cache entry points at an `mcp_result_blob` row, which is shared by content
hash across every caller that got the same answer.
"""

import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import Integer, cast, delete, desc, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from onyx.db.enums import MCPGatewayCallOutcome, MCPResultStorage
from onyx.db.models import (
    MCPGatewayCacheEntry,
    MCPGatewayCallLog,
    MCPGatewayCallStatsDaily,
    MCPResultBlob,
)

# ---------------------------------------------------------------------------
# Result blobs
# ---------------------------------------------------------------------------


def get_blob(db_session: Session, blob_id: str) -> MCPResultBlob | None:
    return db_session.scalar(select(MCPResultBlob).where(MCPResultBlob.id == blob_id))


def upsert_blob__no_commit(
    db_session: Session,
    *,
    blob_id: str,
    size_bytes: int,
    storage: MCPResultStorage,
    digest: dict[str, Any],
    inline_payload: dict[str, Any] | None,
    file_id: str | None,
    provider_slug: str | None,
    tool_name: str | None,
) -> MCPResultBlob:
    """Insert a blob, or bump the reference count if this body already exists.

    The primary key is the content hash, so two callers fetching the same
    answer converge on one row. `ON CONFLICT` rather than read-then-write keeps
    that true under concurrency.
    """
    now = datetime.datetime.now(timezone.utc)
    stmt = (
        pg_insert(MCPResultBlob)
        .values(
            id=blob_id,
            size_bytes=size_bytes,
            storage=storage,
            digest=digest,
            inline_payload=inline_payload,
            file_id=file_id,
            provider_slug=provider_slug,
            tool_name=tool_name,
            ref_count=1,
            created_at=now,
            last_accessed_at=now,
        )
        .on_conflict_do_update(
            index_elements=[MCPResultBlob.id],
            set_={
                "ref_count": MCPResultBlob.ref_count + 1,
                "last_accessed_at": now,
            },
        )
        .returning(MCPResultBlob)
    )
    row = db_session.scalars(stmt).one()
    db_session.flush()
    return row


def touch_blob__no_commit(db_session: Session, blob_id: str) -> None:
    """Push back a blob's collection deadline without loading it."""
    db_session.execute(
        update(MCPResultBlob)
        .where(MCPResultBlob.id == blob_id)
        .values(last_accessed_at=datetime.datetime.now(timezone.utc))
    )


def list_expired_blobs(
    db_session: Session, *, older_than: datetime.datetime, limit: int = 500
) -> list[MCPResultBlob]:
    return list(
        db_session.scalars(
            select(MCPResultBlob)
            .where(MCPResultBlob.last_accessed_at < older_than)
            .order_by(MCPResultBlob.last_accessed_at)
            .limit(limit)
        ).all()
    )


def delete_blobs(db_session: Session, blob_ids: list[str]) -> int:
    if not blob_ids:
        return 0
    result = db_session.execute(
        delete(MCPResultBlob).where(MCPResultBlob.id.in_(blob_ids))
    )
    db_session.commit()
    return result.rowcount or 0  # ty: ignore[unresolved-attribute]


def blob_storage_summary(db_session: Session) -> dict[str, Any]:
    """Row count and total bytes per storage tier, for the admin ops view."""
    rows = db_session.execute(
        select(
            MCPResultBlob.storage,
            func.count(),
            func.coalesce(func.sum(MCPResultBlob.size_bytes), 0),
        ).group_by(MCPResultBlob.storage)
    ).all()
    by_tier: dict[str, dict[str, int]] = {}
    total_bytes = 0
    total_count = 0
    for storage, count, size in rows:
        key = storage.value if isinstance(storage, MCPResultStorage) else str(storage)
        by_tier[key] = {"count": int(count), "bytes": int(size or 0)}
        total_count += int(count)
        total_bytes += int(size or 0)
    return {
        "total_count": total_count,
        "total_bytes": total_bytes,
        "by_storage": by_tier,
    }


# ---------------------------------------------------------------------------
# Cache entries
# ---------------------------------------------------------------------------


def get_cache_entry(db_session: Session, cache_key: str) -> MCPGatewayCacheEntry | None:
    return db_session.scalar(
        select(MCPGatewayCacheEntry).where(MCPGatewayCacheEntry.cache_key == cache_key)
    )


def upsert_cache_entry__no_commit(
    db_session: Session,
    *,
    cache_key: str,
    catalog_slug: str,
    tool_name: str,
    effective_tool_name: str,
    arguments: dict[str, Any],
    blob_id: str,
    is_empty: bool,
    last_refresh_status: str,
    result_created_at: datetime.datetime | None = None,
    blob_prefix: str | None = None,
) -> MCPGatewayCacheEntry:
    now = datetime.datetime.now(timezone.utc)
    existing = get_cache_entry(db_session, cache_key)
    if existing is None:
        existing = MCPGatewayCacheEntry(
            cache_key=cache_key,
            catalog_slug=catalog_slug,
            tool_name=tool_name,
            effective_tool_name=effective_tool_name,
            arguments=arguments,
            blob_id=blob_id,
            is_empty=is_empty,
            first_fetched_at=now,
            last_fetched_at=now,
            last_accessed_at=now,
            hit_count=0,
            last_refresh_status=last_refresh_status,
            result_created_at=result_created_at or now,
            blob_prefix=blob_prefix or blob_id[:2],
        )
        db_session.add(existing)
    else:
        existing.blob_id = blob_id
        existing.is_empty = is_empty
        existing.last_fetched_at = now
        existing.last_accessed_at = now
        existing.last_refresh_status = last_refresh_status
        existing.arguments = arguments
        existing.effective_tool_name = effective_tool_name
        if result_created_at is not None:
            existing.result_created_at = result_created_at
        if blob_prefix is not None:
            existing.blob_prefix = blob_prefix
    db_session.flush()
    return existing


def mark_cache_entry_hit__no_commit(
    db_session: Session, entry: MCPGatewayCacheEntry
) -> None:
    entry.hit_count = (entry.hit_count or 0) + 1
    entry.last_accessed_at = datetime.datetime.now(timezone.utc)
    db_session.flush()


def delete_cache_entries(
    db_session: Session,
    *,
    cache_key: str | None = None,
    catalog_slug: str | None = None,
    tool_name: str | None = None,
) -> int:
    stmt = delete(MCPGatewayCacheEntry)
    if cache_key:
        stmt = stmt.where(MCPGatewayCacheEntry.cache_key == cache_key)
    if catalog_slug:
        stmt = stmt.where(MCPGatewayCacheEntry.catalog_slug == catalog_slug)
    if tool_name:
        stmt = stmt.where(
            (MCPGatewayCacheEntry.effective_tool_name == tool_name)
            | (MCPGatewayCacheEntry.tool_name == tool_name)
        )
    result = db_session.execute(stmt)
    db_session.commit()
    return result.rowcount or 0  # ty: ignore[unresolved-attribute]


def _arguments_digest(arguments: dict[str, Any], *, limit: int = 120) -> str:
    text = str(arguments)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def list_cache_entries(
    db_session: Session,
    *,
    catalog_slug: str | None = None,
    tool_name: str | None = None,
    q: str | None = None,
    sort: str = "last_accessed",
    limit: int = 50,
    offset: int = 0,
    cursor_accessed_at: datetime.datetime | None = None,
    cursor_id: int | None = None,
) -> list[MCPGatewayCacheEntry]:
    stmt = select(MCPGatewayCacheEntry)
    if catalog_slug:
        stmt = stmt.where(MCPGatewayCacheEntry.catalog_slug == catalog_slug)
    if tool_name:
        stmt = stmt.where(
            (MCPGatewayCacheEntry.effective_tool_name == tool_name)
            | (MCPGatewayCacheEntry.tool_name == tool_name)
        )
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            MCPGatewayCacheEntry.effective_tool_name.ilike(pattern)
            | MCPGatewayCacheEntry.tool_name.ilike(pattern)
            | MCPGatewayCacheEntry.catalog_slug.ilike(pattern)
        )
    if sort == "hits":
        stmt = stmt.order_by(
            desc(MCPGatewayCacheEntry.hit_count),
            desc(MCPGatewayCacheEntry.id),
        )
    elif sort == "size":
        stmt = stmt.outerjoin(MCPResultBlob).order_by(
            desc(MCPResultBlob.size_bytes),
            desc(MCPGatewayCacheEntry.id),
        )
    else:
        stmt = stmt.order_by(
            desc(MCPGatewayCacheEntry.last_accessed_at),
            desc(MCPGatewayCacheEntry.id),
        )
        if offset <= 0 and cursor_accessed_at is not None and cursor_id is not None:
            stmt = stmt.where(
                (MCPGatewayCacheEntry.last_accessed_at < cursor_accessed_at)
                | (
                    (MCPGatewayCacheEntry.last_accessed_at == cursor_accessed_at)
                    & (MCPGatewayCacheEntry.id < cursor_id)
                )
            )
    stmt = stmt.offset(max(offset, 0)).limit(min(max(limit, 1), 100))
    return list(db_session.scalars(stmt).all())


def count_cache_entries(
    db_session: Session,
    *,
    catalog_slug: str | None = None,
    tool_name: str | None = None,
    q: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(MCPGatewayCacheEntry)
    if catalog_slug:
        stmt = stmt.where(MCPGatewayCacheEntry.catalog_slug == catalog_slug)
    if tool_name:
        stmt = stmt.where(
            (MCPGatewayCacheEntry.effective_tool_name == tool_name)
            | (MCPGatewayCacheEntry.tool_name == tool_name)
        )
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            MCPGatewayCacheEntry.effective_tool_name.ilike(pattern)
            | MCPGatewayCacheEntry.tool_name.ilike(pattern)
            | MCPGatewayCacheEntry.catalog_slug.ilike(pattern)
        )
    return int(db_session.scalar(stmt) or 0)


def list_entries_for_scheduled_refresh(
    db_session: Session,
    *,
    catalog_slug: str,
    tool_names: list[str],
    older_than: datetime.datetime,
    limit: int = 200,
) -> list[MCPGatewayCacheEntry]:
    """Most-used stale entries first, so a bounded refresh budget buys the most."""
    return list(
        db_session.scalars(
            select(MCPGatewayCacheEntry)
            .where(
                MCPGatewayCacheEntry.catalog_slug == catalog_slug,
                MCPGatewayCacheEntry.effective_tool_name.in_(tool_names),
                MCPGatewayCacheEntry.last_fetched_at < older_than,
            )
            .order_by(desc(MCPGatewayCacheEntry.hit_count))
            .limit(limit)
        ).all()
    )


# ---------------------------------------------------------------------------
# Call log
# ---------------------------------------------------------------------------


def insert_call_log__no_commit(
    db_session: Session,
    *,
    catalog_slug: str,
    tool_name: str,
    effective_tool_name: str,
    cache_key: str,
    outcome: MCPGatewayCallOutcome,
    upstream_billed: bool,
    latency_ms: int,
    response_bytes: int,
    user_email: str | None,
    session_id: str | None,
    arguments: dict[str, Any],
    result_blob_id: str | None,
    error_message: str | None,
) -> MCPGatewayCallLog:
    row = MCPGatewayCallLog(
        catalog_slug=catalog_slug,
        tool_name=tool_name,
        effective_tool_name=effective_tool_name,
        cache_key=cache_key,
        outcome=outcome,
        upstream_billed=upstream_billed,
        latency_ms=latency_ms,
        response_bytes=response_bytes,
        user_email=user_email,
        session_id=session_id,
        arguments={},
        arguments_digest=_arguments_digest(arguments),
        result_blob_id=result_blob_id,
        error_message=error_message,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _stats_from_rows(rows: list[Any]) -> dict[str, Any]:
    by_outcome: dict[str, int] = {}
    billed = 0
    total = 0
    total_bytes = 0
    for outcome, count, billed_sum, bytes_sum in rows:
        key = (
            outcome.value
            if isinstance(outcome, MCPGatewayCallOutcome)
            else str(outcome)
        )
        by_outcome[key] = by_outcome.get(key, 0) + int(count)
        total += int(count)
        billed += int(billed_sum or 0)
        total_bytes += int(bytes_sum or 0)
    hits = by_outcome.get("hit", 0) + by_outcome.get("swr", 0)
    return {
        "total_calls": total,
        "upstream_billed": billed,
        "cache_hits": hits,
        "hit_rate": (hits / total) if total else 0.0,
        "saved_calls": max(total - billed, 0),
        "total_response_bytes": total_bytes,
        "by_outcome": by_outcome,
    }


def call_stats(
    db_session: Session,
    *,
    catalog_slug: str | None = None,
    from_time: datetime.datetime | None = None,
    to_time: datetime.datetime | None = None,
) -> dict[str, Any]:
    stmt = select(
        MCPGatewayCallLog.outcome,
        func.count(),
        func.sum(cast(MCPGatewayCallLog.upstream_billed, Integer)),
        func.coalesce(func.sum(MCPGatewayCallLog.response_bytes), 0),
    )
    if catalog_slug:
        stmt = stmt.where(MCPGatewayCallLog.catalog_slug == catalog_slug)
    if from_time is not None:
        stmt = stmt.where(MCPGatewayCallLog.created_at >= from_time)
    if to_time is not None:
        stmt = stmt.where(MCPGatewayCallLog.created_at < to_time)
    stmt = stmt.group_by(MCPGatewayCallLog.outcome)
    return _stats_from_rows(list(db_session.execute(stmt).all()))


def call_stats_from_daily(
    db_session: Session,
    *,
    from_day: datetime.date,
    to_day: datetime.date,
    catalog_slug: str | None = None,
) -> dict[str, Any]:
    stmt = select(
        MCPGatewayCallStatsDaily.outcome,
        func.coalesce(func.sum(MCPGatewayCallStatsDaily.call_count), 0),
        func.coalesce(func.sum(MCPGatewayCallStatsDaily.billed_count), 0),
        func.coalesce(func.sum(MCPGatewayCallStatsDaily.response_bytes), 0),
    ).where(
        MCPGatewayCallStatsDaily.day >= from_day,
        MCPGatewayCallStatsDaily.day <= to_day,
    )
    if catalog_slug:
        stmt = stmt.where(MCPGatewayCallStatsDaily.catalog_slug == catalog_slug)
    stmt = stmt.group_by(MCPGatewayCallStatsDaily.outcome)
    return _stats_from_rows(list(db_session.execute(stmt).all()))


def call_stats_windowed(
    db_session: Session,
    *,
    from_time: datetime.datetime,
    to_time: datetime.datetime,
    catalog_slug: str | None = None,
) -> dict[str, Any]:
    """Prefer daily rollups for closed days; scan the raw log for today."""
    from_day = from_time.date()
    to_day = to_time.date()
    today = datetime.datetime.now(datetime.timezone.utc).date()
    closed_end = min(to_day, today - datetime.timedelta(days=1))
    merged = _stats_from_rows([])
    if from_day <= closed_end:
        merged = call_stats_from_daily(
            db_session,
            from_day=from_day,
            to_day=closed_end,
            catalog_slug=catalog_slug,
        )
    if to_day >= today:
        today_start = datetime.datetime.combine(
            today, datetime.time.min, tzinfo=datetime.timezone.utc
        )
        raw_from = max(from_time, today_start)
        today_stats = call_stats(
            db_session,
            catalog_slug=catalog_slug,
            from_time=raw_from,
            to_time=to_time,
        )
        merged = _merge_stats(merged, today_stats)
    return merged


def _merge_stats(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    by_outcome: dict[str, int] = dict(left.get("by_outcome") or {})
    for key, value in (right.get("by_outcome") or {}).items():
        by_outcome[key] = by_outcome.get(key, 0) + int(value)
    total = int(left.get("total_calls") or 0) + int(right.get("total_calls") or 0)
    billed = int(left.get("upstream_billed") or 0) + int(
        right.get("upstream_billed") or 0
    )
    bytes_sum = int(left.get("total_response_bytes") or 0) + int(
        right.get("total_response_bytes") or 0
    )
    hits = by_outcome.get("hit", 0) + by_outcome.get("swr", 0)
    return {
        "total_calls": total,
        "upstream_billed": billed,
        "cache_hits": hits,
        "hit_rate": (hits / total) if total else 0.0,
        "saved_calls": max(total - billed, 0),
        "total_response_bytes": bytes_sum,
        "by_outcome": by_outcome,
    }


def _call_log_filters(
    stmt: Any,
    *,
    from_time: datetime.datetime,
    to_time: datetime.datetime,
    catalog_slug: str | None,
    tool_name: str | None,
    outcome: MCPGatewayCallOutcome | None,
    user_email: str | None,
    session_id: str | None,
    cache_key: str | None,
    q: str | None,
) -> Any:
    stmt = stmt.where(
        MCPGatewayCallLog.created_at >= from_time,
        MCPGatewayCallLog.created_at < to_time,
    )
    if catalog_slug:
        stmt = stmt.where(MCPGatewayCallLog.catalog_slug == catalog_slug)
    if tool_name:
        stmt = stmt.where(MCPGatewayCallLog.effective_tool_name == tool_name)
    if outcome is not None:
        stmt = stmt.where(MCPGatewayCallLog.outcome == outcome)
    if user_email:
        stmt = stmt.where(MCPGatewayCallLog.user_email == user_email)
    if session_id:
        stmt = stmt.where(MCPGatewayCallLog.session_id == session_id)
    if cache_key:
        stmt = stmt.where(MCPGatewayCallLog.cache_key == cache_key)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            MCPGatewayCallLog.effective_tool_name.ilike(pattern)
            | MCPGatewayCallLog.tool_name.ilike(pattern)
            | MCPGatewayCallLog.catalog_slug.ilike(pattern)
            | MCPGatewayCallLog.user_email.ilike(pattern)
            | MCPGatewayCallLog.arguments_digest.ilike(pattern)
        )
    return stmt


def list_call_logs(
    db_session: Session,
    *,
    from_time: datetime.datetime,
    to_time: datetime.datetime,
    catalog_slug: str | None = None,
    tool_name: str | None = None,
    outcome: MCPGatewayCallOutcome | None = None,
    user_email: str | None = None,
    session_id: str | None = None,
    cache_key: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    cursor_created_at: datetime.datetime | None = None,
    cursor_id: int | None = None,
) -> list[MCPGatewayCallLog]:
    stmt = _call_log_filters(
        select(MCPGatewayCallLog),
        from_time=from_time,
        to_time=to_time,
        catalog_slug=catalog_slug,
        tool_name=tool_name,
        outcome=outcome,
        user_email=user_email,
        session_id=session_id,
        cache_key=cache_key,
        q=q,
    )
    if offset <= 0 and cursor_created_at is not None and cursor_id is not None:
        stmt = stmt.where(
            (MCPGatewayCallLog.created_at < cursor_created_at)
            | (
                (MCPGatewayCallLog.created_at == cursor_created_at)
                & (MCPGatewayCallLog.id < cursor_id)
            )
        )
    stmt = (
        stmt.order_by(desc(MCPGatewayCallLog.created_at), desc(MCPGatewayCallLog.id))
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 100))
    )
    return list(db_session.scalars(stmt).all())


def count_call_logs(
    db_session: Session,
    *,
    from_time: datetime.datetime,
    to_time: datetime.datetime,
    catalog_slug: str | None = None,
    tool_name: str | None = None,
    outcome: MCPGatewayCallOutcome | None = None,
    user_email: str | None = None,
    session_id: str | None = None,
    cache_key: str | None = None,
    q: str | None = None,
) -> int:
    stmt = _call_log_filters(
        select(func.count()).select_from(MCPGatewayCallLog),
        from_time=from_time,
        to_time=to_time,
        catalog_slug=catalog_slug,
        tool_name=tool_name,
        outcome=outcome,
        user_email=user_email,
        session_id=session_id,
        cache_key=cache_key,
        q=q,
    )
    return int(db_session.scalar(stmt) or 0)


def get_call_log(db_session: Session, call_id: int) -> MCPGatewayCallLog | None:
    return db_session.scalar(
        select(MCPGatewayCallLog).where(MCPGatewayCallLog.id == call_id)
    )


def top_call_slugs(
    db_session: Session,
    *,
    from_time: datetime.datetime,
    to_time: datetime.datetime,
    limit: int = 10,
) -> list[tuple[str, int]]:
    rows = db_session.execute(
        select(MCPGatewayCallLog.catalog_slug, func.count())
        .where(
            MCPGatewayCallLog.created_at >= from_time,
            MCPGatewayCallLog.created_at < to_time,
        )
        .group_by(MCPGatewayCallLog.catalog_slug)
        .order_by(desc(func.count()))
        .limit(limit)
    ).all()
    return [(str(slug), int(count)) for slug, count in rows]


def top_call_tools(
    db_session: Session,
    *,
    from_time: datetime.datetime,
    to_time: datetime.datetime,
    catalog_slug: str | None = None,
    limit: int = 10,
) -> list[tuple[str, int]]:
    stmt = (
        select(MCPGatewayCallLog.effective_tool_name, func.count())
        .where(
            MCPGatewayCallLog.created_at >= from_time,
            MCPGatewayCallLog.created_at < to_time,
        )
        .group_by(MCPGatewayCallLog.effective_tool_name)
        .order_by(desc(func.count()))
        .limit(limit)
    )
    if catalog_slug:
        stmt = stmt.where(MCPGatewayCallLog.catalog_slug == catalog_slug)
    return [(str(name), int(count)) for name, count in db_session.execute(stmt).all()]


def upsert_daily_call_stats(db_session: Session, *, day: datetime.date) -> int:
    """Roll one UTC day from the raw log into the daily table."""
    day_start = datetime.datetime.combine(
        day, datetime.time.min, tzinfo=datetime.timezone.utc
    )
    day_end = day_start + datetime.timedelta(days=1)
    rows = db_session.execute(
        select(
            MCPGatewayCallLog.catalog_slug,
            MCPGatewayCallLog.outcome,
            func.count(),
            func.sum(cast(MCPGatewayCallLog.upstream_billed, Integer)),
            func.coalesce(func.sum(MCPGatewayCallLog.response_bytes), 0),
            func.coalesce(func.sum(MCPGatewayCallLog.latency_ms), 0),
        )
        .where(
            MCPGatewayCallLog.created_at >= day_start,
            MCPGatewayCallLog.created_at < day_end,
        )
        .group_by(MCPGatewayCallLog.catalog_slug, MCPGatewayCallLog.outcome)
    ).all()
    written = 0
    for slug, outcome, count, billed, bytes_sum, latency_sum in rows:
        stmt = (
            pg_insert(MCPGatewayCallStatsDaily)
            .values(
                catalog_slug=slug,
                day=day,
                outcome=outcome,
                call_count=int(count),
                billed_count=int(billed or 0),
                response_bytes=int(bytes_sum or 0),
                latency_ms_sum=int(latency_sum or 0),
            )
            .on_conflict_do_update(
                constraint="uq_mcp_gateway_call_stats_daily_slug_day_outcome",
                set_={
                    "call_count": int(count),
                    "billed_count": int(billed or 0),
                    "response_bytes": int(bytes_sum or 0),
                    "latency_ms_sum": int(latency_sum or 0),
                },
            )
        )
        db_session.execute(stmt)
        written += 1
    db_session.commit()
    return written


def prune_call_logs(
    db_session: Session, *, older_than: datetime.datetime, limit: int = 5000
) -> int:
    ids = list(
        db_session.scalars(
            select(MCPGatewayCallLog.id)
            .where(MCPGatewayCallLog.created_at < older_than)
            .order_by(MCPGatewayCallLog.created_at)
            .limit(limit)
        ).all()
    )
    if not ids:
        return 0
    result = db_session.execute(
        delete(MCPGatewayCallLog).where(MCPGatewayCallLog.id.in_(ids))
    )
    db_session.commit()
    return result.rowcount or 0  # ty: ignore[unresolved-attribute]


def clear_gateway_history(
    db_session: Session,
    *,
    cache: bool = True,
    calls: bool = True,
) -> dict[str, int]:
    """Wipe current-state cache/pointers and leftover Postgres logs."""
    deleted_cache = 0
    deleted_logs = 0
    deleted_stats = 0
    deleted_blobs = 0
    if cache:
        deleted_cache = db_session.execute(delete(MCPGatewayCacheEntry)).rowcount or 0
        deleted_blobs = db_session.execute(delete(MCPResultBlob)).rowcount or 0
    if calls:
        deleted_logs = db_session.execute(delete(MCPGatewayCallLog)).rowcount or 0
        deleted_stats = (
            db_session.execute(delete(MCPGatewayCallStatsDaily)).rowcount or 0
        )
    db_session.commit()
    return {
        "cache_entries": int(deleted_cache),
        "call_logs": int(deleted_logs),
        "stats_rows": int(deleted_stats),
        "result_pointers": int(deleted_blobs),
    }
