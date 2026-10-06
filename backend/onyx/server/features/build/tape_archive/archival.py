"""High-water-mark archival: craft tape rows from Postgres into the lake.

One pass reads unarchived ``craft_tape_entry`` rows past the done-batch
high-water mark, groups them into turns, and appends — in one atomic
snapshot per batch — to ``fact_tape_events`` plus a materialized
``fact_turns`` projection per closed turn.

Two invariants keep the lake faithful (dsh fact-ledger discipline):

1. **Only closed turns archive.** ``fact_turns`` rows are append-once, so
   a turn archives only once its ``turn/end`` context event exists (turns
   recorded before lifecycle events existed never had a ``turn/start``
   and count as closed). A turn whose runner died stays open on tape;
   readers classify open turns as interrupted.
2. **The watermark advances only over a contiguous archived prefix.**
   When a still-open turn blocks the middle of a batch, the pass stops
   there: everything at or below the watermark is provably in the lake,
   and the open turn's rows wait in the hot window for a later pass.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.craft_tape_archive import (
    archived_high_water,
    insert_pending_batch,
    mark_batch_done,
    session_turn_usage,
    unarchived_tape_rows,
)
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.models import BuildSession, CraftTapeEntry
from onyx.server.features.build.sandbox.tape_recorder import TURN_END_INTERRUPTED
from onyx.server.features.build.tape_archive.lake import io as lake_io
from onyx.server.features.build.tape_archive.lake.io import (
    TapeEventRecord,
    TurnRecord,
)
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import get_current_tenant_id

logger = setup_logger()

# Rows per batch: one Iceberg snapshot commit per batch.
ARCHIVE_BATCH_SIZE = 5000

# Safety valve for the pass loop.
_MAX_PASSES_PER_RUN = 20


@dataclass(frozen=True)
class _TurnGroup:
    session_id: Any
    turn_index: int | None
    rows: list[CraftTapeEntry]


def _group_into_turns(rows: list[CraftTapeEntry]) -> list[_TurnGroup]:
    groups: dict[tuple[Any, int | None], list[CraftTapeEntry]] = {}
    order: list[tuple[Any, int | None]] = []
    for row in rows:
        key = (row.session_id, row.turn_index)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    return [
        _TurnGroup(session_id=key[0], turn_index=key[1], rows=groups[key])
        for key in order
    ]


def _group_is_closed(group: _TurnGroup) -> bool:
    """A group archives when its turn ended, or predates lifecycle events."""
    has_start = False
    for row in group.rows:
        if row.kind != "context_event":
            continue
        if row.subtype == "turn/end":
            return True
        if row.subtype == "turn/start":
            has_start = True
    return not has_start


def _turn_record(
    group: _TurnGroup,
    *,
    session: BuildSession | None,
    usage: dict[str, Any] | None,
    runtime: str,
) -> TurnRecord:
    start_payload: dict[str, Any] = {}
    end_payload: dict[str, Any] = {}
    started_at = None
    ended_at = None
    for row in group.rows:
        if row.kind == "context_event" and row.subtype == "turn/start":
            start_payload = dict(row.payload or {})
            started_at = row.created_at
        elif row.kind == "context_event" and row.subtype == "turn/end":
            end_payload = dict(row.payload or {})
            ended_at = row.created_at
    timestamps = [row.created_at for row in group.rows]
    request_env = dict(start_payload.get("request_env") or {})
    usage = usage or {}
    return TurnRecord(
        session_id=str(group.session_id),
        turn_index=group.turn_index if group.turn_index is not None else -1,
        runtime=runtime,
        user_id=str(session.user_id)
        if session is not None and session.user_id
        else None,
        origin=(
            session.origin.value
            if session is not None and session.origin is not None
            else None
        ),
        started_at=started_at or (min(timestamps) if timestamps else None),
        ended_at=ended_at or (max(timestamps) if timestamps else None),
        event_count=len(group.rows),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        reasoning_tokens=usage.get("reasoning_tokens"),
        cache_read_tokens=usage.get("cache_read_tokens"),
        cache_write_tokens=usage.get("cache_write_tokens"),
        cost=usage.get("cost"),
        turn_end_reason=end_payload.get("reason") or TURN_END_INTERRUPTED,
        error_detail=end_payload.get("detail"),
        model=request_env.get("model")
        or (session.agent_model if session is not None else None),
    )


def _event_records(rows: list[CraftTapeEntry]) -> list[TapeEventRecord]:
    return [
        TapeEventRecord(
            session_id=str(row.session_id),
            turn_index=row.turn_index,
            source_id=row.id,
            kind=row.kind,
            subtype=row.subtype,
            runtime=row.runtime,
            payload=dict(row.payload or {}),
            created_at=row.created_at,
        )
        for row in rows
    ]


def _archive_one_batch(db_session: Session, *, after_id: int, limit: int) -> int:
    """Archive one contiguous prefix of closed turns; returns rows archived."""
    rows = unarchived_tape_rows(db_session, after_id=after_id, limit=limit)
    if not rows:
        return 0

    groups = _group_into_turns(rows)
    # Cut at the first open turn: the watermark may only cross rows that
    # actually archived, and an open turn's rows must wait below it.
    archivable: list[_TurnGroup] = []
    for group in groups:
        if not _group_is_closed(group):
            break
        archivable.append(group)
    if not archivable:
        return 0

    archived_rows = [row for group in archivable for row in group.rows]
    max_source_id = archived_rows[-1].id

    session_ids = list({group.session_id for group in archivable})
    sessions_by_id = {
        session.id: session
        for session in db_session.scalars(
            select(BuildSession).where(BuildSession.id.in_(session_ids))
        )
    }
    usage_by_turn = session_turn_usage(db_session, session_ids)

    turn_records = []
    for group in archivable:
        session = sessions_by_id.get(group.session_id)
        runtimes = [row.runtime for row in group.rows if row.runtime]
        turn_records.append(
            _turn_record(
                group,
                session=session,
                usage=usage_by_turn.get(group.session_id, {}).get(
                    group.turn_index if group.turn_index is not None else -1
                ),
                runtime=runtimes[-1] if runtimes else "unknown",
            )
        )

    batch_id = uuid.uuid4()
    insert_pending_batch(
        db_session,
        batch_id=batch_id,
        max_source_id=max_source_id,
        event_count=len(archived_rows),
    )
    db_session.commit()

    lake_io.append_tape_events(
        _event_records(archived_rows),
        batch_id=str(batch_id),
        tenant_id=get_current_tenant_id(),
    )
    lake_io.append_turns(
        turn_records,
        batch_id=str(batch_id),
        tenant_id=get_current_tenant_id(),
    )

    mark_batch_done(db_session, batch_id=batch_id)
    db_session.commit()
    return len(archived_rows)


def run_archive_pass(*, batch_size: int = ARCHIVE_BATCH_SIZE) -> int:
    """Archive every closable batch; returns total rows moved to the lake."""
    total = 0
    with get_session_with_current_tenant() as db_session:
        for _ in range(_MAX_PASSES_PER_RUN):
            moved = _archive_one_batch(
                db_session, after_id=archived_high_water(db_session), limit=batch_size
            )
            total += moved
            if moved < batch_size:
                break
    if total:
        logger.info("Craft tape archive moved %s rows into the lake", total)
    return total
