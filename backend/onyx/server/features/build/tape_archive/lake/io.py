"""Append and scan the craft tape archive Iceberg tables."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
from pyiceberg.expressions import (
    And,
    EqualTo,
    GreaterThan,
    GreaterThanOrEqual,
    In,
    LessThan,
)
from pyiceberg.table import Table

from onyx.configs.app_configs import CRAFT_TAPE_ICEBERG_SCHEMA_VERSION
from onyx.server.features.build.tape_archive.lake.catalog import (
    ensure_craft_tape_iceberg_tables,
    get_catalog,
    table_ident,
)
from shared_configs.contextvars import get_current_tenant_id

LAKE_SCHEMA_VERSION = CRAFT_TAPE_ICEBERG_SCHEMA_VERSION

# Hard cap on readEvent neighbor context, dsh readEvent-style.
MAX_EVENT_WINDOW = 50

# Read-side page guard for one session's events.
MAX_EVENTS_PAGE = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _table(name: str) -> Table:
    ensure_craft_tape_iceberg_tables()
    table = get_catalog().load_table(table_ident(name))
    table.refresh()
    return table


def _append(name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    table = _table(name)
    arrow = pa.Table.from_pylist(rows, schema=table.schema().as_arrow())
    table.append(arrow)


def _tenant(tenant_id: str | None) -> str:
    return tenant_id or get_current_tenant_id()


@dataclass(frozen=True)
class TapeEventRecord:
    """One archived tape event; ``source_id`` is the craft_tape_entry row id."""

    session_id: str
    turn_index: int | None
    source_id: int
    kind: str
    subtype: str
    runtime: str
    payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class TurnRecord:
    """One archived turn summary (projection materialized at archive time)."""

    session_id: str
    turn_index: int
    runtime: str
    user_id: str | None
    origin: str | None
    started_at: datetime | None
    ended_at: datetime | None
    event_count: int
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    cost: float | None
    turn_end_reason: str | None
    error_detail: str | None
    model: str | None


@dataclass(frozen=True)
class SessionAggregate:
    """Per-session rollup folded from fact_turns for list views."""

    session_id: str
    turns: int
    events: int
    input_tokens: int
    output_tokens: int
    cost: float
    last_activity: datetime | None
    last_reason: str | None
    runtimes: tuple[str, ...]


def append_tape_events(
    records: list[TapeEventRecord],
    *,
    batch_id: str,
    source: str = "craft",
    tenant_id: str | None = None,
) -> None:
    """Append one atomic batch of tape events (single snapshot commit)."""
    tenant = _tenant(tenant_id)
    stamp = _now()
    _append(
        "fact_tape_events",
        [
            {
                "tenant_id": tenant,
                "session_id": record.session_id,
                "turn_index": record.turn_index,
                "source_id": record.source_id,
                "kind": record.kind,
                "subtype": record.subtype,
                "runtime": record.runtime,
                "source": source,
                "payload": json.dumps(record.payload, ensure_ascii=False, default=str),
                "batch_id": batch_id,
                "schema_version": LAKE_SCHEMA_VERSION,
                "created_at": record.created_at,
                "recorded_at": stamp,
            }
            for record in records
        ],
    )


def append_turns(
    records: list[TurnRecord],
    *,
    batch_id: str,
    tenant_id: str | None = None,
) -> None:
    tenant = _tenant(tenant_id)
    stamp = _now()
    _append(
        "fact_turns",
        [
            {
                "tenant_id": tenant,
                "session_id": record.session_id,
                "turn_index": record.turn_index,
                "runtime": record.runtime,
                "user_id": record.user_id,
                "origin": record.origin,
                "started_at": record.started_at,
                "ended_at": record.ended_at,
                "event_count": record.event_count,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "reasoning_tokens": record.reasoning_tokens,
                "cache_read_tokens": record.cache_read_tokens,
                "cache_write_tokens": record.cache_write_tokens,
                "cost": record.cost,
                "turn_end_reason": record.turn_end_reason,
                "error_detail": record.error_detail,
                "model": record.model,
                "batch_id": batch_id,
                "schema_version": LAKE_SCHEMA_VERSION,
                "recorded_at": stamp,
            }
            for record in records
        ],
    )


def _event_from_row(row: dict[str, Any]) -> TapeEventRecord:
    return TapeEventRecord(
        session_id=row["session_id"],
        turn_index=row.get("turn_index"),
        source_id=int(row["source_id"]),
        kind=row["kind"],
        subtype=row["subtype"],
        runtime=row["runtime"],
        payload=_parse_json(row.get("payload"), {}),
        created_at=row["created_at"],
    )


def _turn_from_row(row: dict[str, Any]) -> TurnRecord:
    return TurnRecord(
        session_id=row["session_id"],
        turn_index=int(row["turn_index"]),
        runtime=row["runtime"],
        user_id=row.get("user_id"),
        origin=row.get("origin"),
        started_at=row.get("started_at"),
        ended_at=row.get("ended_at"),
        event_count=int(row.get("event_count") or 0),
        input_tokens=row.get("input_tokens"),
        output_tokens=row.get("output_tokens"),
        reasoning_tokens=row.get("reasoning_tokens"),
        cache_read_tokens=row.get("cache_read_tokens"),
        cache_write_tokens=row.get("cache_write_tokens"),
        cost=row.get("cost"),
        turn_end_reason=row.get("turn_end_reason"),
        error_detail=row.get("error_detail"),
        model=row.get("model"),
    )


def load_events(
    session_id: str,
    *,
    after_source_id: int | None = None,
    turn_index: int | None = None,
    limit: int = 200,
    tenant_id: str | None = None,
) -> list[TapeEventRecord]:
    """One session's archived events, ascending by source_id.

    ``after_source_id`` is the cursor (excludes it). The rare duplicate a
    batch retry can produce collapses here: rows key by source_id.
    """
    tenant = _tenant(tenant_id)
    parts: list[Any] = [
        EqualTo("tenant_id", tenant),
        EqualTo("session_id", session_id),
    ]
    if after_source_id is not None:
        parts.append(GreaterThan("source_id", after_source_id))
    if turn_index is not None:
        parts.append(EqualTo("turn_index", turn_index))
    scan = _table("fact_tape_events").scan(row_filter=And(*parts))
    rows = scan.to_arrow().to_pylist()
    by_source: dict[int, TapeEventRecord] = {}
    for row in rows:
        record = _event_from_row(row)
        by_source[record.source_id] = record
    ordered = [by_source[key] for key in sorted(by_source)]
    return ordered[: max(1, min(limit, MAX_EVENTS_PAGE))]


def load_turns(
    session_id: str,
    *,
    tenant_id: str | None = None,
) -> list[TurnRecord]:
    """One session's archived turns, ascending by turn_index."""
    tenant = _tenant(tenant_id)
    scan = _table("fact_turns").scan(
        row_filter=And(EqualTo("tenant_id", tenant), EqualTo("session_id", session_id))
    )
    rows = scan.to_arrow().to_pylist()
    by_turn: dict[int, TurnRecord] = {}
    for row in rows:
        record = _turn_from_row(row)
        existing = by_turn.get(record.turn_index)
        # A batch retry can append a turn twice; keep the settled copy.
        if existing is None or (
            existing.turn_end_reason is None and record.turn_end_reason is not None
        ):
            by_turn[record.turn_index] = record
    return [by_turn[key] for key in sorted(by_turn)]


def read_event_window(
    session_id: str,
    source_id: int,
    *,
    before: int = 20,
    after: int = 20,
    tenant_id: str | None = None,
) -> tuple[TapeEventRecord | None, list[TapeEventRecord]]:
    """One event plus its raw log neighbors, dsh session-query readEvent-style.

    Returns ``(target, window_events)`` where ``window_events`` includes the
    target and neighbors in source_id order. ``target`` is None when absent.
    """
    before = max(0, min(before, MAX_EVENT_WINDOW))
    after = max(0, min(after, MAX_EVENT_WINDOW))
    events = load_events(session_id, limit=MAX_EVENTS_PAGE, tenant_id=tenant_id)
    target_index = next(
        (i for i, event in enumerate(events) if event.source_id == source_id),
        None,
    )
    if target_index is None:
        return None, []
    lo = max(0, target_index - before)
    hi = min(len(events), target_index + after + 1)
    return events[target_index], events[lo:hi]


def session_aggregates(
    *,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    session_ids: list[str] | None = None,
    tenant_id: str | None = None,
) -> dict[str, SessionAggregate]:
    """Fold fact_turns into per-session rollups for list views.

    ``from_time``/``to_time`` bound by turn start; ``session_ids`` narrows
    to a caller's page when provided.
    """
    tenant = _tenant(tenant_id)
    parts: list[Any] = [EqualTo("tenant_id", tenant)]
    if from_time is not None:
        parts.append(GreaterThanOrEqual("started_at", from_time))
    if to_time is not None:
        parts.append(LessThan("started_at", to_time))
    if session_ids:
        parts.append(In("session_id", session_ids))
    row_filter = And(*parts) if len(parts) > 1 else parts[0]
    scan = _table("fact_turns").scan(row_filter=row_filter)
    rows = scan.to_arrow().to_pylist()

    folded: dict[str, dict[str, Any]] = {}
    for row in rows:
        record = _turn_from_row(row)
        bucket = folded.setdefault(
            record.session_id,
            {
                "turns": 0,
                "events": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "last_activity": None,
                "last_reason": None,
                "runtimes": set(),
            },
        )
        bucket["turns"] += 1
        bucket["events"] += record.event_count
        bucket["input_tokens"] += record.input_tokens or 0
        bucket["output_tokens"] += record.output_tokens or 0
        bucket["cost"] += record.cost or 0.0
        bucket["runtimes"].add(record.runtime)
        activity = record.ended_at or record.started_at
        if activity is not None and (
            bucket["last_activity"] is None or activity > bucket["last_activity"]
        ):
            bucket["last_activity"] = activity
            bucket["last_reason"] = record.turn_end_reason
    return {
        session_id: SessionAggregate(
            session_id=session_id,
            turns=data["turns"],
            events=data["events"],
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            cost=data["cost"],
            last_activity=data["last_activity"],
            last_reason=data["last_reason"],
            runtimes=tuple(sorted(data["runtimes"])),
        )
        for session_id, data in folded.items()
    }


def stats_windowed(
    *,
    from_time: datetime,
    to_time: datetime,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    tenant = _tenant(tenant_id)
    scan = _table("fact_turns").scan(
        row_filter=And(
            EqualTo("tenant_id", tenant),
            GreaterThanOrEqual("started_at", from_time),
            LessThan("started_at", to_time),
        )
    )
    rows = scan.to_arrow().to_pylist()
    sessions: set[str] = set()
    by_reason: dict[str, int] = {}
    by_runtime: dict[str, int] = {}
    events = 0
    input_tokens = 0
    output_tokens = 0
    cost = 0.0
    for row in rows:
        record = _turn_from_row(row)
        sessions.add(record.session_id)
        reason = record.turn_end_reason or "unknown"
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_runtime[record.runtime] = by_runtime.get(record.runtime, 0) + 1
        events += record.event_count
        input_tokens += record.input_tokens or 0
        output_tokens += record.output_tokens or 0
        cost += record.cost or 0.0
    return {
        "sessions": len(sessions),
        "turns": len(rows),
        "events": events,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
        "by_reason": by_reason,
        "by_runtime": by_runtime,
    }


def stats_series(
    *,
    from_time: datetime,
    to_time: datetime,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    """Per-day turn/session/event series over fact_turns."""
    tenant = _tenant(tenant_id)
    scan = _table("fact_turns").scan(
        row_filter=And(
            EqualTo("tenant_id", tenant),
            GreaterThanOrEqual("started_at", from_time),
            LessThan("started_at", to_time),
        )
    )
    rows = scan.to_arrow().to_pylist()
    days: dict[str, dict[str, Any]] = {}
    for row in rows:
        record = _turn_from_row(row)
        anchor = record.started_at or record.ended_at
        if anchor is None:
            continue
        day = anchor.astimezone(timezone.utc).date().isoformat()
        bucket = days.setdefault(day, {"sessions": set(), "turns": 0, "events": 0})
        bucket["sessions"].add(record.session_id)
        bucket["turns"] += 1
        bucket["events"] += record.event_count
    return [
        {
            "day": day,
            "sessions": len(data["sessions"]),
            "turns": data["turns"],
            "events": data["events"],
        }
        for day, data in sorted(days.items())
    ]


def expire_before(cutoff: datetime, *, tenant_id: str | None = None) -> int:
    """Drop archived data older than the cutoff; returns expired turn rows."""
    tenant = _tenant(tenant_id)
    turns = _table("fact_turns")
    turn_filt = And(EqualTo("tenant_id", tenant), LessThan("started_at", cutoff))
    count = turns.scan(row_filter=turn_filt).to_arrow().num_rows
    if count:
        turns.delete(turn_filt)
        events = _table("fact_tape_events")
        events.delete(And(EqualTo("tenant_id", tenant), LessThan("created_at", cutoff)))
    return count


def clear_tenant_tape(*, tenant_id: str | None = None) -> None:
    tenant = _tenant(tenant_id)
    filt = EqualTo("tenant_id", tenant)
    for name in ("fact_tape_events", "fact_turns"):
        _table(name).delete(filt)
