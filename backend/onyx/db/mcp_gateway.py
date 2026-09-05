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
from onyx.db.models import MCPGatewayCacheEntry, MCPGatewayCallLog, MCPResultBlob

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


def list_cache_entries(
    db_session: Session,
    *,
    catalog_slug: str | None = None,
    limit: int = 50,
) -> list[MCPGatewayCacheEntry]:
    stmt = (
        select(MCPGatewayCacheEntry)
        .order_by(desc(MCPGatewayCacheEntry.last_accessed_at))
        .limit(limit)
    )
    if catalog_slug:
        stmt = stmt.where(MCPGatewayCacheEntry.catalog_slug == catalog_slug)
    return list(db_session.scalars(stmt).all())


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
        arguments=arguments,
        result_blob_id=result_blob_id,
        error_message=error_message,
    )
    db_session.add(row)
    db_session.flush()
    return row


def call_stats(
    db_session: Session,
    *,
    catalog_slug: str | None = None,
) -> dict[str, Any]:
    stmt = select(
        MCPGatewayCallLog.outcome,
        func.count(),
        func.sum(cast(MCPGatewayCallLog.upstream_billed, Integer)),
        func.coalesce(func.sum(MCPGatewayCallLog.response_bytes), 0),
    )
    if catalog_slug:
        stmt = stmt.where(MCPGatewayCallLog.catalog_slug == catalog_slug)
    stmt = stmt.group_by(MCPGatewayCallLog.outcome)

    by_outcome: dict[str, int] = {}
    billed = 0
    total = 0
    total_bytes = 0
    for outcome, count, billed_sum, bytes_sum in db_session.execute(stmt).all():
        key = (
            outcome.value
            if isinstance(outcome, MCPGatewayCallOutcome)
            else str(outcome)
        )
        by_outcome[key] = int(count)
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
