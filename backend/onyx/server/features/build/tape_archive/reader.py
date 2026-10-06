"""Merged tape reads: the Iceberg archive plus the Postgres hot tail.

One session's events live in two tiers once archiving is enabled: the lake
holds everything at or below the done-batch high-water mark, Postgres holds
the tail above it. This module merges both into a single ascending stream
keyed by ``source_id`` (the ``craft_tape_entry`` id), so callers — the admin
API, the user API, and the replay translator — always see a whole turn no
matter which tier holds it. With archiving disabled the lake leg is skipped
and the stream is pure Postgres.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.configs.app_configs import CRAFT_TAPE_ARCHIVE_ENABLED
from onyx.db.craft_tape_archive import archived_high_water, tape_tail_events


def merged_tape_events(
    db_session: Session,
    session_id: UUID,
    *,
    after_source_id: int | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Ascending tape events for one session, merged across both tiers.

    ``after_source_id`` is an exclusive cursor over ``source_id``. Rows key
    by source_id, so the rare duplicate a batch retry can leave in the lake
    collapses to its newest copy.
    """
    from onyx.server.features.build.tape_archive.lake import io as lake_io

    high_water = archived_high_water(db_session) if CRAFT_TAPE_ARCHIVE_ENABLED else 0
    merged: dict[int, dict[str, Any]] = {}
    if CRAFT_TAPE_ARCHIVE_ENABLED and high_water > 0:
        for record in lake_io.load_events(
            str(session_id), after_source_id=after_source_id, limit=limit
        ):
            merged[record.source_id] = {
                "source_id": record.source_id,
                "turn_index": record.turn_index,
                "kind": record.kind,
                "subtype": record.subtype,
                "runtime": record.runtime,
                "payload": record.payload,
                "created_at": record.created_at,
            }
    tail_after = max(high_water, after_source_id or 0)
    for row in tape_tail_events(
        db_session, session_id, after_id=tail_after, limit=limit
    ):
        merged[row.id] = {
            "source_id": row.id,
            "turn_index": row.turn_index,
            "kind": row.kind,
            "subtype": row.subtype,
            "runtime": row.runtime,
            "payload": dict(row.payload or {}),
            "created_at": row.created_at,
        }
    return [merged[key] for key in sorted(merged)][:limit]
