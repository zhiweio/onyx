"""Craft tape archive batch ledger and PG-side tail reads.

Callers stay in ``onyx.db``: the lake I/O lives in
``onyx.server.features.build.tape_archive.lake`` and this module supplies
the Postgres side — high-water bookkeeping and the unarchived tail.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onyx.db.models import CraftLLMRequest, CraftTapeArchiveBatch, CraftTapeEntry


def archived_high_water(db_session: Session) -> int:
    """Greatest craft_tape_entry.id safely present in the lake (0 if none)."""
    value = db_session.scalar(
        select(func.max(CraftTapeArchiveBatch.max_source_id)).where(
            CraftTapeArchiveBatch.status == "done"
        )
    )
    return int(value or 0)


def insert_pending_batch(
    db_session: Session, *, batch_id: UUID, max_source_id: int, event_count: int
) -> None:
    db_session.add(
        CraftTapeArchiveBatch(
            batch_id=batch_id,
            max_source_id=max_source_id,
            event_count=event_count,
            status="pending",
        )
    )


def mark_batch_done(db_session: Session, *, batch_id: UUID) -> None:
    row = db_session.scalar(
        select(CraftTapeArchiveBatch).where(CraftTapeArchiveBatch.batch_id == batch_id)
    )
    if row is None:
        return
    row.status = "done"
    row.updated_at = func.now()


def unarchived_tape_rows(
    db_session: Session, *, after_id: int, limit: int
) -> list[CraftTapeEntry]:
    """Oldest-first tape rows past the high-water mark, bounded to a batch."""
    stmt = (
        select(CraftTapeEntry)
        .where(CraftTapeEntry.id > after_id)
        .order_by(CraftTapeEntry.id.asc())
        .limit(limit)
    )
    return list(db_session.scalars(stmt))


def session_turn_usage(
    db_session: Session, session_ids: list[UUID]
) -> dict[UUID, dict[int, dict[str, Any]]]:
    """Per (session, turn) token/cost sums from the LLM request ledger."""
    if not session_ids:
        return {}
    stmt = (
        select(
            CraftLLMRequest.session_id,
            CraftLLMRequest.turn_index,
            func.coalesce(func.sum(CraftLLMRequest.input_tokens), 0),
            func.coalesce(func.sum(CraftLLMRequest.output_tokens), 0),
            func.coalesce(func.sum(CraftLLMRequest.reasoning_tokens), 0),
            func.coalesce(func.sum(CraftLLMRequest.cache_read_tokens), 0),
            func.coalesce(func.sum(CraftLLMRequest.cache_write_tokens), 0),
            func.coalesce(func.sum(CraftLLMRequest.cost), 0.0),
        )
        .where(CraftLLMRequest.session_id.in_(session_ids))
        .group_by(CraftLLMRequest.session_id, CraftLLMRequest.turn_index)
    )
    folded: dict[UUID, dict[int, dict[str, Any]]] = {}
    for row in db_session.execute(stmt):
        session_id, turn_index, *sums = row
        if session_id is None or turn_index is None:
            continue
        folded.setdefault(session_id, {})[int(turn_index)] = {
            "input_tokens": int(sums[0]),
            "output_tokens": int(sums[1]),
            "reasoning_tokens": int(sums[2]),
            "cache_read_tokens": int(sums[3]),
            "cache_write_tokens": int(sums[4]),
            "cost": float(sums[5]),
        }
    return folded


def tape_tail_events(
    db_session: Session,
    session_id: UUID,
    *,
    after_id: int,
    limit: int = 500,
) -> list[CraftTapeEntry]:
    """Hot-window tail for one session: rows not yet present in the lake."""
    stmt = (
        select(CraftTapeEntry)
        .where(CraftTapeEntry.session_id == session_id, CraftTapeEntry.id > after_id)
        .order_by(CraftTapeEntry.id.asc())
        .limit(limit)
    )
    return list(db_session.scalars(stmt))
