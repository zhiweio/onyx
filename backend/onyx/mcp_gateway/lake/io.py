"""Append and scan MCP Iceberg tables."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import pyarrow as pa
from pyiceberg.expressions import And, EqualTo, GreaterThanOrEqual, In, LessThan
from pyiceberg.table import Table

from onyx.configs.app_configs import MCP_ICEBERG_SCHEMA_VERSION
from onyx.mcp_gateway.lake.catalog import (
    ensure_mcp_iceberg_tables,
    get_catalog,
    table_ident,
)
from onyx.mcp_gateway.upstream import is_empty_result, is_error_result
from shared_configs.contextvars import get_current_tenant_id

LAKE_SCHEMA_VERSION = MCP_ICEBERG_SCHEMA_VERSION


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def blob_prefix_for(blob_id: str) -> str:
    return blob_id[:2] if len(blob_id) >= 2 else blob_id


def _table(name: str) -> Table:
    ensure_mcp_iceberg_tables()
    table = get_catalog().load_table(table_ident(name))
    table.refresh()
    return table


def _append(name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    table = _table(name)
    arrow = pa.Table.from_pylist(rows, schema=table.schema().as_arrow())
    table.append(arrow)


def _tenant() -> str:
    return get_current_tenant_id()


@dataclass(frozen=True)
class ResultRecord:
    blob_id: str
    catalog_slug: str
    effective_tool_name: str
    payload: dict[str, Any]
    digest: dict[str, Any]
    size_bytes: int
    is_empty: bool
    is_error: bool
    created_at: datetime


@dataclass(frozen=True)
class CallRecord:
    call_id: str
    parent_call_id: str | None
    request_id: str
    catalog_slug: str
    pack_slug: str
    tool_name: str
    effective_tool_name: str
    cache_key: str
    result_blob_id: str | None
    outcome: str
    is_error: bool
    error_class: str | None
    error_message: str | None
    upstream_billed: bool
    latency_ms: int
    response_bytes: int
    user_id: str | None
    user_email: str | None
    session_id: str | None
    arguments: dict[str, Any]
    arguments_digest: str
    refresh_mode: str
    ttl_seconds: int
    created_at: datetime


@dataclass(frozen=True)
class CacheEventRecord:
    event_id: str
    cache_key: str
    blob_id: str | None
    call_id: str | None
    action: str
    catalog_slug: str
    created_at: datetime


@dataclass(frozen=True)
class SeriesPoint:
    day: str
    key: str
    value: float


def result_exists(
    blob_id: str,
    *,
    tenant_id: str | None = None,
    catalog_slug: str | None = None,
) -> bool:
    tenant = tenant_id or _tenant()
    table = _table("fact_results")
    parts = [EqualTo("tenant_id", tenant), EqualTo("blob_id", blob_id)]
    if catalog_slug:
        parts.append(EqualTo("catalog_slug", catalog_slug))
        parts.append(EqualTo("blob_prefix", blob_prefix_for(blob_id)))
    scan = table.scan(row_filter=And(*parts) if len(parts) > 1 else parts[0])
    return scan.to_arrow().num_rows > 0


def append_result(
    *,
    blob_id: str,
    catalog_slug: str,
    effective_tool_name: str,
    payload: dict[str, Any],
    digest: dict[str, Any],
    size_bytes: int,
    tenant_id: str | None = None,
    created_at: datetime | None = None,
) -> ResultRecord:
    tenant = tenant_id or _tenant()
    stamp = created_at or _now()
    if result_exists(blob_id, tenant_id=tenant, catalog_slug=catalog_slug):
        loaded = get_result(blob_id, tenant_id=tenant, catalog_slug=catalog_slug)
        if loaded is not None:
            return loaded
    record = ResultRecord(
        blob_id=blob_id,
        catalog_slug=catalog_slug,
        effective_tool_name=effective_tool_name,
        payload=payload,
        digest=digest,
        size_bytes=size_bytes,
        is_empty=is_empty_result(payload),
        is_error=is_error_result(payload),
        created_at=stamp,
    )
    _append(
        "fact_results",
        [
            {
                "tenant_id": tenant,
                "blob_id": blob_id,
                "catalog_slug": catalog_slug,
                "blob_prefix": blob_prefix_for(blob_id),
                "effective_tool_name": effective_tool_name,
                "payload": _json(payload),
                "digest": _json(digest),
                "size_bytes": size_bytes,
                "is_empty": record.is_empty,
                "is_error": record.is_error,
                "schema_version": LAKE_SCHEMA_VERSION,
                "created_at": stamp,
                "recorded_at": _now(),
            }
        ],
    )
    return record


def get_result(
    blob_id: str,
    *,
    tenant_id: str | None = None,
    catalog_slug: str | None = None,
) -> ResultRecord | None:
    tenant = tenant_id or _tenant()
    table = _table("fact_results")
    parts = [
        EqualTo("tenant_id", tenant),
        EqualTo("blob_id", blob_id),
        EqualTo("blob_prefix", blob_prefix_for(blob_id)),
    ]
    if catalog_slug:
        parts.append(EqualTo("catalog_slug", catalog_slug))
    scan = table.scan(row_filter=And(*parts))
    arrow = scan.to_arrow()
    if arrow.num_rows == 0:
        # Retry without prune keys when a pointer is older than the
        # partition layout, or a prior wipe removed only some files.
        scan = table.scan(
            row_filter=And(EqualTo("tenant_id", tenant), EqualTo("blob_id", blob_id))
        )
        arrow = scan.to_arrow()
    if arrow.num_rows == 0:
        return None
    row = arrow.slice(0, 1).to_pylist()[0]
    created = row["created_at"]
    if isinstance(created, datetime) and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return ResultRecord(
        blob_id=row["blob_id"],
        catalog_slug=row["catalog_slug"],
        effective_tool_name=row["effective_tool_name"],
        payload=_parse_json(row["payload"], {}),
        digest=_parse_json(row["digest"], {}),
        size_bytes=int(row["size_bytes"]),
        is_empty=bool(row["is_empty"]),
        is_error=bool(row["is_error"]),
        created_at=created,
    )


def append_call(
    *,
    call_id: str,
    request_id: str,
    catalog_slug: str,
    pack_slug: str,
    tool_name: str,
    effective_tool_name: str,
    cache_key: str,
    outcome: str,
    upstream_billed: bool,
    latency_ms: int,
    response_bytes: int,
    arguments: dict[str, Any],
    arguments_digest: str,
    refresh_mode: str,
    ttl_seconds: int,
    parent_call_id: str | None = None,
    result_blob_id: str | None = None,
    is_error: bool = False,
    error_class: str | None = None,
    error_message: str | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    session_id: str | None = None,
    tenant_id: str | None = None,
    created_at: datetime | None = None,
) -> CallRecord:
    stamp = created_at or _now()
    record = CallRecord(
        call_id=call_id,
        parent_call_id=parent_call_id,
        request_id=request_id,
        catalog_slug=catalog_slug,
        pack_slug=pack_slug,
        tool_name=tool_name,
        effective_tool_name=effective_tool_name,
        cache_key=cache_key,
        result_blob_id=result_blob_id,
        outcome=outcome,
        is_error=is_error,
        error_class=error_class,
        error_message=error_message,
        upstream_billed=upstream_billed,
        latency_ms=latency_ms,
        response_bytes=response_bytes,
        user_id=user_id,
        user_email=user_email,
        session_id=session_id,
        arguments=arguments,
        arguments_digest=arguments_digest,
        refresh_mode=refresh_mode,
        ttl_seconds=ttl_seconds,
        created_at=stamp,
    )
    _append(
        "fact_calls",
        [
            {
                "tenant_id": tenant_id or _tenant(),
                "call_id": call_id,
                "parent_call_id": parent_call_id,
                "request_id": request_id,
                "catalog_slug": catalog_slug,
                "pack_slug": pack_slug,
                "tool_name": tool_name,
                "effective_tool_name": effective_tool_name,
                "cache_key": cache_key,
                "result_blob_id": result_blob_id,
                "outcome": outcome,
                "is_error": is_error,
                "error_class": error_class,
                "error_message": error_message,
                "upstream_billed": upstream_billed,
                "latency_ms": latency_ms,
                "response_bytes": response_bytes,
                "user_id": user_id,
                "user_email": user_email,
                "session_id": session_id,
                "arguments": _json(arguments),
                "arguments_digest": arguments_digest,
                "refresh_mode": refresh_mode,
                "ttl_seconds": ttl_seconds,
                "schema_version": LAKE_SCHEMA_VERSION,
                "created_at": stamp,
                "recorded_at": _now(),
            }
        ],
    )
    return record


def append_cache_event(
    *,
    cache_key: str,
    action: str,
    catalog_slug: str,
    blob_id: str | None = None,
    call_id: str | None = None,
    tenant_id: str | None = None,
) -> CacheEventRecord:
    stamp = _now()
    event_id = str(uuid.uuid4())
    _append(
        "fact_cache_events",
        [
            {
                "tenant_id": tenant_id or _tenant(),
                "event_id": event_id,
                "cache_key": cache_key,
                "blob_id": blob_id,
                "call_id": call_id,
                "action": action,
                "catalog_slug": catalog_slug,
                "schema_version": LAKE_SCHEMA_VERSION,
                "created_at": stamp,
                "recorded_at": stamp,
            }
        ],
    )
    return CacheEventRecord(
        event_id=event_id,
        cache_key=cache_key,
        blob_id=blob_id,
        call_id=call_id,
        action=action,
        catalog_slug=catalog_slug,
        created_at=stamp,
    )


def _call_from_row(row: dict[str, Any]) -> CallRecord:
    created = row["created_at"]
    if isinstance(created, datetime) and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return CallRecord(
        call_id=row["call_id"],
        parent_call_id=row.get("parent_call_id"),
        request_id=row["request_id"],
        catalog_slug=row["catalog_slug"],
        pack_slug=row["pack_slug"],
        tool_name=row["tool_name"],
        effective_tool_name=row["effective_tool_name"],
        cache_key=row["cache_key"],
        result_blob_id=row.get("result_blob_id"),
        outcome=row["outcome"],
        is_error=bool(row["is_error"]),
        error_class=row.get("error_class"),
        error_message=row.get("error_message"),
        upstream_billed=bool(row["upstream_billed"]),
        latency_ms=int(row["latency_ms"]),
        response_bytes=int(row["response_bytes"]),
        user_id=row.get("user_id"),
        user_email=row.get("user_email"),
        session_id=row.get("session_id"),
        arguments=_parse_json(row.get("arguments"), {}),
        arguments_digest=row.get("arguments_digest") or "",
        refresh_mode=row.get("refresh_mode") or "",
        ttl_seconds=int(row.get("ttl_seconds") or 0),
        created_at=created,
    )


def list_calls(
    *,
    from_time: datetime,
    to_time: datetime,
    catalog_slug: str | None = None,
    tool_name: str | None = None,
    outcome: str | None = None,
    user_email: str | None = None,
    session_id: str | None = None,
    cache_key: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant_id: str | None = None,
) -> tuple[list[CallRecord], int]:
    tenant = tenant_id or _tenant()
    table = _table("fact_calls")
    parts: list[Any] = [
        EqualTo("tenant_id", tenant),
        GreaterThanOrEqual("created_at", from_time),
        LessThan("created_at", to_time),
    ]
    if catalog_slug:
        parts.append(EqualTo("catalog_slug", catalog_slug))
    if tool_name:
        parts.append(EqualTo("effective_tool_name", tool_name))
    if outcome:
        parts.append(EqualTo("outcome", outcome))
    if user_email:
        parts.append(EqualTo("user_email", user_email))
    if session_id:
        parts.append(EqualTo("session_id", session_id))
    if cache_key:
        parts.append(EqualTo("cache_key", cache_key))
    scan = table.scan(row_filter=And(*parts))
    rows = [_call_from_row(row) for row in scan.to_arrow().to_pylist()]
    if q:
        needle = q.lower()
        rows = [
            row
            for row in rows
            if needle in row.effective_tool_name.lower()
            or needle in row.tool_name.lower()
            or needle in row.catalog_slug.lower()
            or needle in (row.arguments_digest or "").lower()
        ]
    rows.sort(key=lambda row: (row.created_at, row.call_id), reverse=True)
    total = len(rows)
    return rows[offset : offset + limit], total


def get_call(call_id: str, *, tenant_id: str | None = None) -> CallRecord | None:
    tenant = tenant_id or _tenant()
    table = _table("fact_calls")
    scan = table.scan(
        row_filter=And(EqualTo("tenant_id", tenant), EqualTo("call_id", call_id))
    )
    arrow = scan.to_arrow()
    if arrow.num_rows == 0:
        return None
    return _call_from_row(arrow.slice(0, 1).to_pylist()[0])


def stats_windowed(
    *,
    from_time: datetime,
    to_time: datetime,
    catalog_slug: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    rows, _ = list_calls(
        from_time=from_time,
        to_time=to_time,
        catalog_slug=catalog_slug,
        limit=1_000_000,
        offset=0,
        tenant_id=tenant_id,
    )
    by_outcome: dict[str, int] = {}
    billed = 0
    total_bytes = 0
    servers: dict[str, int] = {}
    tools: dict[str, int] = {}
    for row in rows:
        by_outcome[row.outcome] = by_outcome.get(row.outcome, 0) + 1
        if row.upstream_billed:
            billed += 1
        total_bytes += row.response_bytes
        servers[row.catalog_slug] = servers.get(row.catalog_slug, 0) + 1
        tools[row.effective_tool_name] = tools.get(row.effective_tool_name, 0) + 1
    total = len(rows)
    hits = by_outcome.get("hit", 0) + by_outcome.get("swr", 0)
    return {
        "total_calls": total,
        "upstream_billed": billed,
        "cache_hits": hits,
        "hit_rate": (hits / total) if total else 0.0,
        "saved_calls": hits,
        "total_response_bytes": total_bytes,
        "by_outcome": by_outcome,
        "top_servers": [
            {"slug": slug, "count": count}
            for slug, count in sorted(
                servers.items(), key=lambda item: item[1], reverse=True
            )[:10]
        ],
        "top_tools": [
            {"tool": name, "count": count}
            for name, count in sorted(
                tools.items(), key=lambda item: item[1], reverse=True
            )[:10]
        ],
    }


def stats_series(
    *,
    from_time: datetime,
    to_time: datetime,
    catalog_slug: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    rows, _ = list_calls(
        from_time=from_time,
        to_time=to_time,
        catalog_slug=catalog_slug,
        limit=1_000_000,
        offset=0,
        tenant_id=tenant_id,
    )
    by_day_outcome: dict[tuple[str, str], int] = {}
    by_day_latency: dict[str, list[int]] = {}
    by_day_billed: dict[str, dict[str, int]] = {}
    by_day_bytes: dict[tuple[str, str], int] = {}
    for row in rows:
        day = row.created_at.date().isoformat()
        by_day_outcome[(day, row.outcome)] = (
            by_day_outcome.get((day, row.outcome), 0) + 1
        )
        by_day_latency.setdefault(day, []).append(row.latency_ms)
        billed_row = by_day_billed.setdefault(day, {"billed": 0, "saved": 0})
        if row.upstream_billed:
            billed_row["billed"] += 1
        else:
            billed_row["saved"] += 1
        by_day_bytes[(day, row.catalog_slug)] = (
            by_day_bytes.get((day, row.catalog_slug), 0) + row.response_bytes
        )

    days = sorted({day for day, _ in by_day_outcome} | set(by_day_latency))
    outcomes = ("hit", "miss", "swr", "bypass", "error", "refresh")
    calls_by_outcome = []
    latency = []
    billed_vs_saved = []
    for day in days:
        point: dict[str, Any] = {"day": day}
        for outcome in outcomes:
            point[outcome] = by_day_outcome.get((day, outcome), 0)
        calls_by_outcome.append(point)
        samples = sorted(by_day_latency.get(day, []))
        p50 = samples[len(samples) // 2] if samples else 0
        p95 = samples[max(int(len(samples) * 0.95) - 1, 0)] if samples else 0
        latency.append({"day": day, "p50": p50, "p95": p95})
        pair = by_day_billed.get(day, {"billed": 0, "saved": 0})
        billed_vs_saved.append({"day": day, **pair})

    bytes_by_server: dict[str, int] = {}
    for (_day, slug), size in by_day_bytes.items():
        bytes_by_server[slug] = bytes_by_server.get(slug, 0) + size
    bytes_bars = [
        {"server": slug, "bytes": size}
        for slug, size in sorted(
            bytes_by_server.items(), key=lambda item: item[1], reverse=True
        )[:10]
    ]
    return {
        "calls_by_outcome": calls_by_outcome,
        "latency": latency,
        "billed_vs_saved": billed_vs_saved,
        "bytes_by_server": bytes_bars,
    }


def snapshot_catalog(
    *,
    catalog_slug: str,
    pack_slug: str,
    display_name: str,
    upstream_url: str,
    enabled: bool,
    tenant_id: str | None = None,
) -> None:
    host = urlparse(upstream_url).hostname or ""
    stamp = _now()
    _append(
        "dim_catalog",
        [
            {
                "tenant_id": tenant_id or _tenant(),
                "catalog_sk": str(uuid.uuid4()),
                "catalog_slug": catalog_slug,
                "pack_slug": pack_slug,
                "display_name": display_name,
                "upstream_host": host,
                "enabled": enabled,
                "is_current": True,
                "valid_from": stamp,
                "valid_to": None,
                "schema_version": LAKE_SCHEMA_VERSION,
                "recorded_at": stamp,
            }
        ],
    )


def snapshot_tool(
    *,
    catalog_slug: str,
    tool_name: str,
    enabled: bool,
    tenant_id: str | None = None,
) -> None:
    stamp = _now()
    _append(
        "dim_tool",
        [
            {
                "tenant_id": tenant_id or _tenant(),
                "tool_sk": str(uuid.uuid4()),
                "catalog_slug": catalog_slug,
                "tool_name": tool_name,
                "enabled": enabled,
                "is_current": True,
                "valid_from": stamp,
                "valid_to": None,
                "schema_version": LAKE_SCHEMA_VERSION,
                "recorded_at": stamp,
            }
        ],
    )


def clear_tenant_lake(
    *,
    tenant_id: str | None = None,
    cache: bool = True,
    calls: bool = True,
) -> None:
    tenant = tenant_id or _tenant()
    names: list[str] = []
    if calls:
        names.extend(["fact_calls", "agg_stats_daily"])
    if cache:
        names.extend(["fact_results", "fact_cache_events"])
    if cache and calls:
        names.extend(["dim_catalog", "dim_tool"])
    filt = EqualTo("tenant_id", tenant)
    for name in names:
        _table(name).delete(filt)


def expire_calls_before(cutoff: datetime, *, tenant_id: str | None = None) -> int:
    tenant = tenant_id or _tenant()
    table = _table("fact_calls")
    filt = And(EqualTo("tenant_id", tenant), LessThan("created_at", cutoff))
    count = table.scan(row_filter=filt).to_arrow().num_rows
    if count:
        table.delete(filt)
    return count


def delete_results(blob_ids: list[str], *, tenant_id: str | None = None) -> int:
    if not blob_ids:
        return 0
    tenant = tenant_id or _tenant()
    table = _table("fact_results")
    filt = And(EqualTo("tenant_id", tenant), In("blob_id", blob_ids))
    count = table.scan(row_filter=filt).to_arrow().num_rows
    if count:
        table.delete(filt)
    return count


def delete_catalog_calls(catalog_slug: str, *, tenant_id: str | None = None) -> None:
    tenant = tenant_id or _tenant()
    table = _table("fact_calls")
    table.delete(
        And(EqualTo("tenant_id", tenant), EqualTo("catalog_slug", catalog_slug))
    )


def rollup_daily_stats(*, day: date, tenant_id: str | None = None) -> int:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    rows, _ = list_calls(
        from_time=start,
        to_time=end,
        limit=1_000_000,
        offset=0,
        tenant_id=tenant_id,
    )
    buckets: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        key = (row.catalog_slug, row.outcome)
        bucket = buckets.setdefault(
            key,
            {
                "call_count": 0,
                "billed_count": 0,
                "response_bytes": 0,
                "latency_ms_sum": 0,
            },
        )
        bucket["call_count"] += 1
        if row.upstream_billed:
            bucket["billed_count"] += 1
        bucket["response_bytes"] += row.response_bytes
        bucket["latency_ms_sum"] += row.latency_ms
    stamp = _now()
    tenant = tenant_id or _tenant()
    payload = [
        {
            "tenant_id": tenant,
            "catalog_slug": slug,
            "day": day.isoformat(),
            "outcome": outcome,
            "call_count": values["call_count"],
            "billed_count": values["billed_count"],
            "response_bytes": values["response_bytes"],
            "latency_ms_sum": values["latency_ms_sum"],
            "schema_version": LAKE_SCHEMA_VERSION,
            "recorded_at": stamp,
        }
        for (slug, outcome), values in buckets.items()
    ]
    if payload:
        table = _table("agg_stats_daily")
        table.delete(
            And(
                EqualTo("tenant_id", tenant),
                EqualTo("day", day.isoformat()),
            )
        )
        _append("agg_stats_daily", payload)
    return len(payload)
